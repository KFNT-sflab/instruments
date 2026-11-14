# -*- coding: utf-8 -*-
"""
Created on Mon Nov  2 2026

Python wrapper for the LibreVNA, controlled through the SCPI server of the
LibreVNA-GUI (plain TCP socket, default port 19542).

The LibreVNA itself is a USB device; all communication goes through the
LibreVNA-GUI, which acts as the SCPI server. This module can start the GUI
in headless mode (``--no-gui``) and then talks to it over a socket.

Usage follows the other instrument modules (``self.dev.write/query``,
methods that set a value when given an argument and query it otherwise):

    from LibreVNA import LibreVNA

    vna = LibreVNA(start_server=True, gui_path=r"C:\\software\\LibreVNA-GUI\\LibreVNA-GUI.exe")
    vna.setup_sweep(start=1e9, stop=2e9, points=501, ifbw=1e3, power=-10)
    f, s11 = vna.sweep('S11')
    vna.close()

Reference: Documentation/UserManual/ProgrammingGuide.pdf (SCPI command list).
"""

import os
import re
import json
import time
import shutil
import socket
import subprocess
import numpy as np

try:
    from tqdm import tqdm
except ImportError:  # progress bars are optional
    tqdm = None

try:  # inside the instruments package
    from .Instrument import Instrument
except ImportError:  # stand-alone use
    class Instrument:
        """Minimal stand-in for instruments.Instrument when used stand-alone."""
        def idn(self):
            return self.dev.query('*IDN?')

        def clear(self):
            self.dev.clear()

        def configure(self, conf):
            for attr in conf:
                setattr(self.dev, attr, conf[attr])

        def lock(self, timeout=5000):
            self.locked = True

        def unlock(self):
            self.locked = False

        def close(self):
            self.dev.close()


DEFAULT_PORT = 19542


def _parse_address(address):
    """Accept 'host:port', 'host', ('host', port) or a VISA-like
    'TCPIP::host::port::SOCKET' string and return (host, port)."""
    if isinstance(address, (tuple, list)):
        return address[0], int(address[1])
    m = re.match(r'TCPIP\d*::([^:]+)::(\d+)::SOCKET', address, re.IGNORECASE)
    if m:
        return m.group(1), int(m.group(2))
    if ':' in address:
        host, port = address.rsplit(':', 1)
        return host, int(port)
    return address, DEFAULT_PORT


def _to_bool(resp):
    return resp.strip().upper() in ('TRUE', '1', 'ON')


def _fmt_bool(value):
    return 'TRUE' if value else 'FALSE'


class SCPIError(RuntimeError):
    pass


class LibreVNASocket:
    """
    Very small newline-terminated SCPI-over-TCP transport. It mimics the
    parts of the pyvisa resource API used by the instrument classes
    (write, read, query, clear, close, timeout in ms).
    """

    def __init__(self, host='localhost', port=DEFAULT_PORT, timeout=5000,
                 connect_timeout=5.0):
        self.host = host
        self.port = port
        self._buf = b''
        self.sock = socket.create_connection((host, port), timeout=connect_timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.timeout = timeout

    @property
    def timeout(self):
        """Read timeout in milliseconds (same convention as pyvisa)."""
        return self._timeout

    @timeout.setter
    def timeout(self, value_ms):
        self._timeout = value_ms
        self.sock.settimeout(None if value_ms is None else value_ms / 1000)

    def write(self, msg):
        self.sock.sendall(msg.encode('ascii') + b'\n')

    def read(self, timeout=None):
        """Read one line (without the terminating newline).
        `timeout` in seconds overrides the default for this call."""
        old = self.sock.gettimeout()
        if timeout is not None:
            self.sock.settimeout(timeout)
        try:
            while b'\n' not in self._buf:
                try:
                    chunk = self.sock.recv(65536)
                except socket.timeout:
                    raise TimeoutError(f"Timeout waiting for response from LibreVNA-GUI "
                                       f"at {self.host}:{self.port}") from None
                if not chunk:
                    raise ConnectionError("LibreVNA-GUI closed the connection "
                                          "(only one SCPI client is allowed at a time).")
                self._buf += chunk
            line, self._buf = self._buf.split(b'\n', 1)
            return line.decode('ascii', errors='replace').rstrip('\r')
        finally:
            self.sock.settimeout(old)

    def read_lines(self, idle_timeout=0.5):
        """Read lines until nothing arrives for `idle_timeout` s
        (for the few multi-line responses, e.g. *LST?)."""
        lines = []
        while True:
            try:
                lines.append(self.read(timeout=idle_timeout))
            except TimeoutError:
                return lines

    def query(self, msg, timeout=None):
        self.clear()
        self.write(msg)
        return self.read(timeout=timeout)

    def clear(self):
        """Discard any unread data in the input buffer."""
        self._buf = b''
        old = self.sock.gettimeout()
        self.sock.settimeout(0)
        try:
            while True:
                chunk = self.sock.recv(65536)
                if not chunk:
                    break
        except (BlockingIOError, socket.timeout, OSError):
            pass
        finally:
            self.sock.settimeout(old)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class LibreVNA(Instrument):
    """
    LibreVNA vector network analyzer (via the LibreVNA-GUI SCPI server).

    Parameters
    ----------
    rm : pyvisa ResourceManager or None
        Ignored (accepted for signature compatibility with the other
        instruments; communication uses a plain socket).
    address : str
        'host:port', 'host' or 'TCPIP::host::port::SOCKET'. Default localhost:19542.
    start_server : bool
        Start the LibreVNA-GUI (headless) before connecting. If a server is
        already listening on the port, it is reused.
    gui_path : str
        Path to LibreVNA-GUI(.exe). If None, the LIBREVNA_GUI environment
        variable and then the PATH are searched.
    no_gui : bool
        Start the GUI with --no-gui (headless). Set False to see the window.
    connect_device : bool or str
        Connect to a LibreVNA after opening (True = first found, or a serial number).
    check_errors : bool
        After every write, query *ESR? and raise SCPIError on command/execution errors.
    timeout : int
        Default read timeout in ms.
    """

    CAL_MEAS_TYPES = ('OPEN', 'SHORT', 'LOAD', 'THROUGH', 'ISOLATION',
                      'SLIDINGLOAD', 'REFLECT', 'LINE')
    KIT_STANDARD_TYPES = ('Open', 'Short', 'Load', 'Reflect', 'Through', 'Line')
    DEEMB_TYPES = ('PORT_EXTENSION', '2XTHRU', 'MATCHING_NETWORK', 'IMPEDANCE_RENORMALIZATION')

    def __init__(self, rm=None, address='localhost:19542', start_server=False,
                 gui_path=None, no_gui=True, server_startup_timeout=30,
                 connect_device=True, check_errors=True, timeout=5000):
        self.rm = rm
        self.address = address
        self.access_mode = 'socket'
        self.locked = False
        self.host, self.port = _parse_address(address)
        self.check_errors = check_errors
        self.server_process = None

        if start_server and not self._port_open():
            self.start_server(gui_path, no_gui=no_gui, timeout=server_startup_timeout)

        try:
            self.dev = LibreVNASocket(self.host, self.port, timeout=timeout)
        except OSError as e:
            raise ConnectionError(
                f"Cannot connect to LibreVNA-GUI at {self.host}:{self.port}. Make sure it "
                "is running with the SCPI server enabled, or use start_server=True.") from e

        print(self.idn())
        self.clear()
        if connect_device:
            self.connect(None if connect_device is True else connect_device)

    # ------------------------------------------------------------------
    # Server (LibreVNA-GUI) handling
    # ------------------------------------------------------------------
    def _port_open(self):
        try:
            with socket.create_connection((self.host, self.port), timeout=0.5):
                return True
        except OSError:
            return False

    @staticmethod
    def find_gui(gui_path=None):
        candidates = [gui_path, os.environ.get('LIBREVNA_GUI'),
                     shutil.which('LibreVNA-GUI'), shutil.which('LibreVNA-GUI.exe')]
        for c in candidates:
            if c and os.path.isfile(c):
                return c
        raise FileNotFoundError("LibreVNA-GUI executable not found. Pass gui_path= or set "
                                "the LIBREVNA_GUI environment variable.")

    def start_server(self, gui_path=None, no_gui=True, timeout=30):
        """Start LibreVNA-GUI with the SCPI server on self.port and wait until it listens.

        Note: connecting to the first found device on startup is a GUI preference
        (Startup.ConnectToFirstDevice); we connect explicitly anyway."""
        if self.host not in ('localhost', '127.0.0.1', '::1'):
            raise RuntimeError("The server can only be started on the local machine.")
        
        exe = self.find_gui(gui_path)
        args = [exe, '--port', str(self.port)]
        
        if no_gui:
            # Pass as separate list elements so subprocess parses them correctly
            args.extend(['-platform', 'offscreen'])
            
        # Handle platform-specific process group creation
        if os.name == 'nt':
            self.server_process = subprocess.Popen(
                args, 
                cwd=os.path.dirname(exe),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            self.server_process = subprocess.Popen(
                args, 
                cwd=os.path.dirname(exe),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            
        t0 = time.time()
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.server_process.poll() is not None:
                raise RuntimeError(f"LibreVNA-GUI exited with code {self.server_process.returncode}")
            if self._port_open():
                time.sleep(0.5)  # give the GUI a moment to finish initialising
                return
            time.sleep(0.25)
        self.stop_server()
        raise TimeoutError("LibreVNA-GUI did not open the SCPI port in time.")

    def stop_server(self):
        """Terminate the LibreVNA-GUI process if it was started by this object."""
        if self.server_process is not None and self.server_process.poll() is None:
            self.server_process.terminate()
            try:
                self.server_process.wait(5)
            except subprocess.TimeoutExpired:
                self.server_process.kill()
        self.server_process = None

    def close(self, stop_server=True):
        """Close the socket (and stop the GUI if we started it)."""
        try:
            self.halt()
            self.dev.close()
        finally:
            if stop_server:
                self.stop_server()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # ------------------------------------------------------------------
    # Low level
    # ------------------------------------------------------------------
    def write(self, cmd, check=None):
        """Send an event (no response). Checks *ESR? afterwards if enabled."""
        self.dev.write(cmd)
        if check or (check is None and self.check_errors):
            self.check_status(cmd)

    def query(self, cmd, timeout=None):
        """Send a query and return the response line (timeout in s)."""
        resp = self.dev.query(cmd, timeout=timeout)
        if resp == 'ERROR':
            self.status()  # clear the error bits
            raise SCPIError(f"Query '{cmd}' returned ERROR")
        return resp

    def query_float(self, cmd):
        return float(self.query(cmd))

    def query_int(self, cmd):
        return int(float(self.query(cmd)))

    def query_bool(self, cmd):
        return _to_bool(self.query(cmd))

    def _setget(self, cmd, value=None, conv=float, fmt='{}'):
        """value given -> write 'cmd value', else query 'cmd?' and convert."""
        if value is None:
            resp = self.query(cmd + '?')
            return _to_bool(resp) if conv is bool else conv(resp)
        if conv is bool:
            self.write(f"{cmd} {_fmt_bool(value)}")
        else:
            self.write(f"{cmd} {fmt.format(value)}")

    def status(self):
        """Event status register (reading it clears it)."""
        return int(self.dev.query('*ESR?'))

    def check_status(self, cmd=''):
        esr = self.status()
        if esr & 0x20:
            raise SCPIError(f"Command error: '{cmd}'")
        if esr & 0x10:
            raise SCPIError(f"Execution error: '{cmd}'")
        if esr & 0x08:
            raise SCPIError(f"Device error: '{cmd}'")
        if esr & 0x04:
            raise SCPIError(f"Query error: '{cmd}'")
        return esr

    def clear(self):
        """Flush the input buffer and clear the status register."""
        self.dev.clear()
        self.status()

    def reset(self):
        """*RST: reset the GUI and the connected device to the default state."""
        self.write('*RST')

    def opc(self, timeout=60):
        """Block until all pending operations are complete."""
        return self.query('*OPC?', timeout=timeout)

    def list_commands(self):
        """All SCPI commands known to the GUI (*LST?)."""
        self.dev.clear()
        self.dev.write('*LST?')
        return [l for l in self.dev.read_lines() if l]

    # ------------------------------------------------------------------
    # Device commands
    # ------------------------------------------------------------------
    def connect(self, serial=None):
        """Connect the GUI to a LibreVNA (first found if serial is None)."""
        self.write(':DEV:CONN' + (f' {serial}' if serial else ''))
        dev = self.connected_device()
        if dev is None:
            raise ConnectionError("LibreVNA-GUI is not connected to any device.")
        return dev

    def disconnect(self):
        self.write(':DEV:DISC')

    def connected_device(self):
        """Serial number of the connected device or None."""
        resp = self.query(':DEV:CONN?')
        return None if resp == 'Not connected' else resp

    def list_devices(self):
        resp = self.query(':DEV:LIST?')
        return [s for s in resp.split(',') if s]

    def mode(self, mode=None):
        """'VNA', 'GEN' or 'SA'."""
        return self._setget(':DEV:MODE', mode, conv=str)

    def preference(self, name, value=None):
        """Read or set a GUI preferences entry (e.g. 'Startup.ConnectToFirstDevice')."""
        if value is None:
            return self.query(f':DEV:PREF? {name}')
        if isinstance(value, bool):
            value = 'true' if value else 'false'
        self.write(f':DEV:PREF {name} {value}')

    def apply_preferences(self):
        self.write(':DEV:APPLYPREF')

    def save_setup(self, filename):
        """Save the GUI setup (path on the machine running the GUI)."""
        self.write(f':DEV:SETUP:SAVE {filename}')

    def load_setup(self, filename):
        if not _to_bool(self.query(f':DEV:SETUP:LOAD? {filename}')):
            raise SCPIError(f"Failed to load setup '{filename}'")

    def ref_out(self, freq_MHz=None):
        """Reference output: 0 (off), 10 or 100 MHz."""
        return self._setget(':DEV:REF:OUT', freq_MHz, conv=int, fmt='{:d}')

    def ref_in(self, mode=None):
        """Reference input: 'INT', 'EXT' or 'AUTO' (query returns INT or EXT)."""
        return self._setget(':DEV:REF:IN', mode, conv=str)

    def device_status(self):
        return {'unlocked': self.query_bool(':DEV:STA:UNLO?'),
                'adc_overload': self.query_bool(':DEV:STA:ADCOVER?'),
                'unlevel': self.query_bool(':DEV:STA:UNLEV?')}

    def device_info(self):
        info = {'fw_revision': self.query(':DEV:INF:FWREV?'),
                'hw_revision': self.query(':DEV:INF:HWREV?')}
        try:
            info['temperatures'] = self.query(':DEV:INF:TEMP?')
        except SCPIError:
            pass
        return info

    def limits(self):
        q = lambda c: self.query_float(f':DEV:INF:LIM:{c}?')
        return {'min_frequency': q('MINF'), 'max_frequency': q('MAXF'),
                'min_ifbw': q('MINIFBW'), 'max_ifbw': q('MAXIFBW'),
                'max_points': int(q('MAXP')),
                'min_power': q('MINPOW'), 'max_power': q('MAXPOW'),
                'min_rbw': q('MINRBW'), 'max_rbw': q('MAXRBW'),
                'max_harmonic_frequency': q('MAXHARM')}

    # ------------------------------------------------------------------
    # VNA: sweep settings
    # ------------------------------------------------------------------
    def sweep_mode(self, kind=None):
        """'FREQUENCY' or 'POWER'."""
        return self._setget(':VNA:SWEEP', kind, conv=str)

    def sweep_spacing(self, kind=None):
        """'LIN' or 'LOG'."""
        return self._setget(':VNA:SWEEPTYPE', kind, conv=str)

    def start(self, freq=None):
        return self._setget(':VNA:FREQ:START', freq, fmt='{:.0f}')

    def stop(self, freq=None):
        return self._setget(':VNA:FREQ:STOP', freq, fmt='{:.0f}')

    def center(self, freq=None):
        return self._setget(':VNA:FREQ:CENT', freq, fmt='{:.0f}')

    def span(self, freq=None):
        return self._setget(':VNA:FREQ:SPAN', freq, fmt='{:.0f}')

    def full_span(self):
        self.write(':VNA:FREQ:FULL')

    def zero_span(self):
        self.write(':VNA:FREQ:ZERO')

    def power_start(self, dBm=None):
        return self._setget(':VNA:POW:START', dBm, fmt='{:.2f}')

    def power_stop(self, dBm=None):
        return self._setget(':VNA:POW:STOP', dBm, fmt='{:.2f}')

    def power(self, dBm=None):
        """Stimulus level in dBm (frequency sweeps)."""
        return self._setget(':VNA:STIM:LVL', dBm, fmt='{:.2f}')

    def stim_frequency(self, freq=None):
        """Stimulus frequency in Hz (power sweeps)."""
        return self._setget(':VNA:STIM:FREQ', freq, fmt='{:.0f}')

    def ifbw(self, bw=None):
        return self._setget(':VNA:ACQ:IFBW', bw, fmt='{:.0f}')

    def dwell_time(self, t=None):
        return self._setget(':VNA:ACQ:DWELL', t, fmt='{:g}')

    def points(self, n=None):
        return self._setget(':VNA:ACQ:POINTS', n, conv=int, fmt='{:d}')

    def averages(self, n=None):
        return self._setget(':VNA:ACQ:AVG', n, conv=int, fmt='{:d}')

    def averaging_level(self):
        """Number of sweeps acquired so far by the averaging."""
        return self.query_int(':VNA:ACQ:AVGLEV?')

    def single(self, state=None):
        """True: single sweep, False: continuous."""
        return self._setget(':VNA:ACQ:SINGLE', state, conv=bool)

    def run(self):
        self.write(':VNA:ACQ:RUN')

    def halt(self):
        """Stop the acquisition (:VNA:ACQ:STOP)."""
        self.write(':VNA:ACQ:STOP')

    def running(self):
        return self.query_bool(':VNA:ACQ:RUN?')

    def finished(self):
        """True when the averaging has reached the configured number of sweeps."""
        return self.query_bool(':VNA:ACQ:FIN?')

    def limit_status(self):
        return self.query(':VNA:ACQ:LIM?')

    def current_frequency(self):
        return self.query_float(':VNA:ACQ:FREQ?')

    def current_power(self):
        return self.query_float(':VNA:ACQ:POW?')

    def current_time(self):
        return self.query_float(':VNA:ACQ:TIME?')

    def setup_sweep(self, start=None, stop=None, points=None, ifbw=None, power=None,
                    averages=None, center=None, span=None, log=None):
        """Switch to VNA frequency-sweep mode and set the given parameters (Hz, dBm)."""
        self.mode('VNA')
        self.sweep_mode('FREQUENCY')
        if log is not None:
            self.sweep_spacing('LOG' if log else 'LIN')
        if start is not None:
            self.start(start)
        if stop is not None:
            self.stop(stop)
        if center is not None:
            self.center(center)
        if span is not None:
            self.span(span)
        if points is not None:
            self.points(points)
        if ifbw is not None:
            self.ifbw(ifbw)
        if power is not None:
            self.power(power)
        if averages is not None:
            self.averages(averages)

    @staticmethod
    def _sweep_index(x, start, stop, points, log=False):
        """Point index of the stimulus value x in a sweep start..stop."""
        if points <= 1 or stop == start:
            return 0
        if log and start > 0 and x > 0:
            frac = np.log(x / start) / np.log(stop / start)
        else:
            frac = (x - start) / (stop - start)
        return int(round(min(max(frac, 0.0), 1.0) * (points - 1)))

    def _progress_bar(self, desc):
        """Create a tqdm bar over the points of one sweep and return
        (bar, update_function) or (None, None) if not possible."""
        if tqdm is None:
            return None, None
        try:
            points = self.points()
            avg = max(self.averages(), 1)
            if self.sweep_mode().upper().startswith('POW'):
                start, stop, log = self.power_start(), self.power_stop(), False
                current = self.current_power
            else:
                start, stop = self.start(), self.stop()
                log = self.sweep_spacing().upper() == 'LOG'
                current = self.current_frequency
        except (SCPIError, ValueError, TimeoutError) as e:
            print(f"Progress bar disabled, could not read sweep settings: {e!r}")
            return None, None

        bar = tqdm(total=points, desc=desc, unit='pt')
        started = [False]

        def update():
            # position inside the currently running sweep (set absolutely, so
            # a new sweep / averaging pass starts the bar again from 0)
            idx = self._sweep_index(current(), start, stop, points, log)
            if not started[0]:
                # right after RUN the GUI may still report the last point of
                # the previous sweep -> show 0 until the new sweep is seen
                if idx >= points - 1:
                    idx = -1
                else:
                    started[0] = True
            bar.n = idx + 1
            if avg > 1:
                level = min(self.averaging_level() + 1, avg)
                bar.set_postfix_str(f'avg {level}/{avg}', refresh=False)
            bar.refresh()

        return bar, update

    def _wait(self, done, timeout, poll, progress, desc, stale_check=None):
        """Poll `done()` until True, optionally updating a tqdm progress bar."""
        t0 = time.time()
        if stale_check is not None:
            # avoid a stale 'done' state from before the sweep was (re)started
            while stale_check() and time.time() - t0 < 0.3:
                time.sleep(0.02)
        bar, update = self._progress_bar(desc) if progress else (None, None)
        warned = False
        try:
            while not done():
                if time.time() - t0 > timeout:
                    raise TimeoutError(f"{desc} did not finish in time.")
                if bar is not None:
                    try:
                        update()
                    except (SCPIError, ValueError, TimeoutError) as e:
                        if not warned:
                            bar.write(f"Progress not available: {e}")
                            warned = True
                time.sleep(poll)
            if bar is not None:
                bar.n = bar.total
                bar.refresh()
        finally:
            if bar is not None:
                bar.close()

    def wait_sweep(self, timeout=600, poll=0.1, progress=True, desc='Sweep'):
        """
        Wait until the (averaged) sweep is finished.

        progress : bool
            Show a tqdm progress bar of the current point within the sweep,
            derived from the current stimulus frequency (or power for power
            sweeps, :VNA:ACQ:FREQ?/POW?), polled every `poll` seconds. With
            averaging, the bar restarts for every pass and 'avg n/N' is shown.
        """
        self._wait(self.finished, timeout, poll, progress, desc,
                   stale_check=self.finished)

    def debug_progress(self, duration=None, poll=0.2):
        """
        Diagnostic: start a single sweep and print the raw values used for the
        progress bar (FIN?, AVGLEV?, FREQ?, POW?) every `poll` s until the sweep
        is finished (or `duration` s have passed).
        """
        print('points', self.points(), 'avg', self.averages(), 'start', self.start(),
              'stop', self.stop(), 'sweep', self.sweep_mode(), self.sweep_spacing())
        self.single(True)
        self.run()
        t0 = time.time()
        while True:
            dt = time.time() - t0
            fin = self.query(':VNA:ACQ:FIN?')
            print(f"{dt:7.2f} s  FIN={fin:5s} AVGLEV={self.query(':VNA:ACQ:AVGLEV?'):>3s} "
                  f"FREQ={self.query(':VNA:ACQ:FREQ?'):>14s} POW={self.query(':VNA:ACQ:POW?')}")
            if (fin == 'TRUE' and dt > 1) or (duration is not None and dt > duration):
                break
            time.sleep(poll)

    def sweep(self, traces=('S11',), timeout=600, progress=True):
        """
        Take a single (averaged) sweep and return the data.

        Returns (freq, data) for a single trace name, or (freq, dict) for a list
        of traces. `data` is a complex numpy array.
        """
        single_trace = isinstance(traces, str)
        if single_trace:
            traces = (traces,)
        self.single(True)
        self.run()
        self.wait_sweep(timeout=timeout, progress=progress)
        out = {}
        f = None
        for tr in traces:
            f, out[tr] = self.trace_data(tr)
        return (f, out[traces[0]]) if single_trace else (f, out)

    # ------------------------------------------------------------------
    # VNA: traces
    # ------------------------------------------------------------------
    def traces(self):
        return [t for t in self.query(':VNA:TRAC:LIST?').split(',') if t]

    @staticmethod
    def parse_trace(data, ncols=3):
        vals = np.array([v for v in re.split(r'[\[\],\s]+', data) if v], dtype=float)
        if vals.size % ncols:
            raise ValueError("Invalid trace data")
        return vals.reshape(-1, ncols)

    def trace_data(self, trace='S11', timeout=None):
        """Return (x, S) where x is frequency in Hz (or power/time) and S complex."""
        arr = self.parse_trace(self.query(f':VNA:TRAC:DATA? {trace}', timeout=timeout))
        return arr[:, 0], arr[:, 1] + 1j * arr[:, 2]

    def trace_at(self, trace, freq):
        re_, im_ = (float(v) for v in self.query(f':VNA:TRAC:AT? {trace} {freq:.0f}').split(','))
        return complex(re_, im_)

    def touchstone(self, traces=('S11', 'S12', 'S21', 'S22'), filename=None):
        """Touchstone text of n*n traces (order S11..S1n, S21.., ...). Optionally save to a local file."""
        self.dev.clear()
        self.dev.write(':VNA:TRAC:TOUCHSTONE? ' + ' '.join(traces))
        text = '\n'.join(self.dev.read_lines()) + '\n'
        if filename is not None:
            with open(filename, 'w') as f:
                f.write(text)
        return text

    def trace_max(self, trace):
        f, r, i = (float(v) for v in self.query(f':VNA:TRAC:MAXA? {trace}').split(','))
        return f, complex(r, i)

    def trace_min(self, trace):
        f, r, i = (float(v) for v in self.query(f':VNA:TRAC:MINA? {trace}').split(','))
        return f, complex(r, i)

    def trace_freq_range(self, trace):
        return (self.query_float(f':VNA:TRAC:MINF? {trace}'),
                self.query_float(f':VNA:TRAC:MAXF? {trace}'))

    def trace_new(self, name, parameter=None):
        self.write(f':VNA:TRAC:NEW {name}')
        if parameter is not None:
            self.trace_parameter(name, parameter)

    def trace_delete(self, trace):
        self.write(f':VNA:TRAC:DEL {trace}')

    def trace_rename(self, trace, new_name):
        self.write(f':VNA:TRAC:RENAME {trace} {new_name}')

    def trace_pause(self, trace, pause=True):
        self.write(f":VNA:TRAC:{'PAUSE' if pause else 'RESUME'} {trace}")

    def trace_paused(self, trace):
        return self.query_bool(f':VNA:TRAC:PAUSED? {trace}')

    def trace_parameter(self, trace, parameter=None):
        """'S11', 'S12', 'S21' or 'S22'."""
        if parameter is None:
            return self.query(f':VNA:TRAC:PARAM? {trace}')
        self.write(f':VNA:TRAC:PARAM {trace} {parameter}')

    def trace_type(self, trace, kind=None):
        """'OVERWRITE', 'MAXHOLD' or 'MINHOLD'."""
        if kind is None:
            return self.query(f':VNA:TRAC:TYPE? {trace}')
        self.write(f':VNA:TRAC:TYPE {trace} {kind}')

    def trace_deembedding(self, trace, active=None):
        if active is None:
            return self.query_bool(f':VNA:TRAC:DEEMB:ACT? {trace}')
        self.write(f':VNA:TRAC:DEEMB:ACT {trace} {_fmt_bool(active)}')

    # ------------------------------------------------------------------
    # VNA: calibration
    # ------------------------------------------------------------------
    def cal_reset(self):
        """Deactivate the calibration and delete all calibration measurements."""
        self.write(':VNA:CAL:RESET')

    def cal_add(self, kind, port=None, standard=None):
        """Add a calibration measurement ('OPEN', 'SHORT', 'LOAD', 'THROUGH',
        'ISOLATION', 'SLIDINGLOAD', 'REFLECT', 'LINE'). For one-port standards
        `port` is the port number; for THROUGH/LINE/ISOLATION pass the two
        ports as a string '1 2' or tuple (1, 2).
        Returns the (0-based) index of the new measurement."""
        kind = kind.upper()
        if kind not in self.CAL_MEAS_TYPES:
            raise ValueError(f"Unknown calibration measurement {kind}")
        self.write(f':VNA:CAL:ADD {kind}' + (f' {standard}' if standard else ''))
        idx = self.cal_num() - 1
        if port is not None:
            self.cal_port(idx, port)
        return idx

    def cal_num(self):
        return self.query_int(':VNA:CAL:NUM?')

    def cal_type(self, idx):
        return self.query(f':VNA:CAL:TYPE? {idx}')

    def cal_port(self, idx, port=None):
        if port is None:
            return self.query(f':VNA:CAL:PORT? {idx}')
        if isinstance(port, (tuple, list)):
            port = ' '.join(str(p) for p in port)
        self.write(f':VNA:CAL:PORT {idx} {port}')

    def cal_standard(self, idx, standard=None):
        if standard is None:
            return self.query(f':VNA:CAL:STANDARD? {idx}')
        self.write(f':VNA:CAL:STANDARD {idx} {standard}')

    def cal_busy(self):
        return self.query_bool(':VNA:CAL:BUSY?')

    def cal_measure(self, *idx, wait=True, timeout=600, progress=True):
        """Take calibration measurement(s) given by index. Several indices are
        measured simultaneously (must be on different ports)."""
        self.write(':VNA:CAL:MEAS ' + ','.join(str(i) for i in idx))
        if wait:
            time.sleep(0.1)
            self._wait(lambda: not self.cal_busy(), timeout, 0.1, progress,
                       desc='Calibration ' + ','.join(self.cal_type(i) for i in idx))

    def cal_available(self):
        """Calibration types that can be activated with the measurements taken."""
        return [t for t in self.query(':VNA:CAL:ACT?').split(',') if t]

    def cal_activate(self, kind):
        """Activate a calibration, e.g. 'SOLT_1', 'SOLT_12', 'TRL_12'."""
        self.write(f':VNA:CAL:ACT {kind}')

    def cal_active(self):
        return self.query(':VNA:CAL:ACTIVE?')

    def cal_save(self, filename):
        """Save the active calibration (path on the machine running the GUI)."""
        self.write(f':VNA:CAL:SAVE {filename}')

    def cal_load(self, filename):
        if not _to_bool(self.query(f':VNA:CAL:LOAD? {filename}')):
            raise SCPIError(f"Failed to load calibration '{filename}'")
        return self.cal_active()

    def cal_measurements(self):
        """List of (index, type, port, standard) of the configured measurements."""
        out = []
        for i in range(self.cal_num()):
            try:
                std = self.cal_standard(i)
            except SCPIError:
                std = None
            out.append((i, self.cal_type(i), self.cal_port(i), std))
        return out

    def _prompt(self, msg, prompt):
        if prompt is None:
            input(msg + " and press ENTER")
        else:
            prompt(msg)

    def calibrate_SOL(self, port=1, prompt=None, save=None):
        """
        Interactive one-port (Open/Short/Load) calibration -> SOLT_<port>.

        prompt : callable(str) or None
            Called before each standard (default: input() in the console).
        save : str or None
            Save the calibration to this file (on the GUI machine) afterwards.
        """
        self.mode('VNA')
        self.cal_reset()
        meas = {k: self.cal_add(k, port=port) for k in ('OPEN', 'SHORT', 'LOAD')}
        for name, idx in meas.items():
            self._prompt(f"Connect the {name} standard to port {port}", prompt)
            self.cal_measure(idx)
        self.cal_activate(f'SOLT_{port}')
        if save:
            self.cal_save(save)
        return self.cal_active()

    def calibrate_SOLT(self, ports=(1, 2), isolation=False, prompt=None, save=None):
        """
        Interactive full two-port SOLT calibration -> SOLT_12.
        The Open/Short/Load on both ports are measured simultaneously
        (connect the same standard type to both ports).
        """
        p1, p2 = ports
        self.mode('VNA')
        self.cal_reset()
        for name in ('OPEN', 'SHORT', 'LOAD'):
            i1 = self.cal_add(name, port=p1)
            i2 = self.cal_add(name, port=p2)
            self._prompt(f"Connect {name} standards to ports {p1} and {p2}", prompt)
            self.cal_measure(i1, i2)
        it = self.cal_add('THROUGH', port=(p1, p2))
        self._prompt(f"Connect the THROUGH between ports {p1} and {p2}", prompt)
        self.cal_measure(it)
        if isolation:
            ii = self.cal_add('ISOLATION', port=(p1, p2))
            self._prompt(f"Connect LOADs to ports {p1} and {p2} (isolation)", prompt)
            self.cal_measure(ii)
        self.cal_activate(f'SOLT_{p1}{p2}')
        if save:
            self.cal_save(save)
        return self.cal_active()

    # ------------------------------------------------------------------
    # VNA: calibration kit
    # ------------------------------------------------------------------
    def kit_load(self, filename):
        """Load a calibration kit file (.calkit, path on the GUI machine)."""
        if not _to_bool(self.query(f':VNA:CAL:KIT:LOAD? {filename}')):
            raise SCPIError(f"Failed to load calibration kit '{filename}'")

    def kit_save(self, filename):
        self.write(f':VNA:CAL:KIT:SAVE {filename}')

    def kit_filename(self):
        return self.query(':VNA:CAL:KIT:FILE?')

    def kit_manufacturer(self, value=None):
        return self._setget(':VNA:CAL:KIT:MAN', value, conv=str)

    def kit_serial(self, value=None):
        return self._setget(':VNA:CAL:KIT:SER', value, conv=str)

    def kit_description(self, value=None):
        return self._setget(':VNA:CAL:KIT:DESC', value, conv=str)

    def kit_clear(self):
        """Reset the kit to ideal default standards."""
        self.write(':VNA:CAL:KIT:STA:CLEAR')

    def kit_num(self):
        return self.query_int(':VNA:CAL:KIT:STA:NUM?')

    def kit_std_type(self, x):
        return self.query(f':VNA:CAL:KIT:STA:TYPE? {x}')

    def kit_new(self, kind, name):
        """Add a standard: kind in 'Open','Short','Load','Reflect','Through','Line'.
        Returns the index of the new standard."""
        self.write(f':VNA:CAL:KIT:STA:NEW {kind} {name}')
        return self.kit_num()

    def kit_delete(self, x):
        self.write(f':VNA:CAL:KIT:STA:DEL {x}')

    def kit_std(self, x, param, value=None):
        """
        Get/set a parameter of calibration standard number x, e.g.
            NAME, Z0, DELAY [ps], LOSS [GOhm/s],
            Open:  C0 [1e-15 F], C1 [1e-27 F/Hz], C2 [1e-36 F/Hz^2], C3 [1e-45 F/Hz^3]
            Short: L0 [1e-12 H], L1 [1e-24 H/Hz], L2 [1e-33 H/Hz^2], L3 [1e-42 H/Hz^3]
            Load:  RESistance [Ohm], CPARallel [F], LSERies [H], CFIRST (bool)
            Reflect: SHORT (bool)
        """
        cmd = f':VNA:CAL:KIT:STA:{x}:{param}'
        if value is None:
            return self.query(cmd + '?')
        if isinstance(value, bool):
            value = _fmt_bool(value)
        self.write(f'{cmd} {value}')

    def kit_std_file(self, x, filename, *ports):
        """Load the standard's coefficients from a touchstone file (on the GUI machine)."""
        self.write(f':VNA:CAL:KIT:STA:{x}:FILE {filename}' + ''.join(f' {p}' for p in ports))

    def kit_standards(self):
        """List of (index, type, name) of all standards in the kit (1-based index)."""
        return [(x, self.kit_std_type(x), self.kit_std(x, 'NAME'))
                for x in range(1, self.kit_num() + 1)]

    # ------------------------------------------------------------------
    # VNA: de-embedding
    # ------------------------------------------------------------------
    def deemb_clear(self):
        self.write(':VNA:DEEMB:CLEAR')

    def deemb_new(self, kind):
        """'PORT_EXTENSION', 'MATCHING_NETWORK' or 'IMPEDANCE_RENORMALIZATION'
        (2XTHRU has no SCPI configuration). Returns its 1-based index."""
        self.write(f':VNA:DEEMB:NEW {kind}')
        return self.deemb_num()

    def deemb_num(self):
        return self.query_int(':VNA:DEEMB:NUM?')

    def deemb_type(self, x):
        return self.query(f':VNA:DEEMB:TYPE? {x}')

    def deemb_delete(self, x):
        self.write(f':VNA:DEEMB:DEL {x}')

    def deemb_swap(self, x1, x2):
        self.write(f':VNA:DEEMB:SWAP {x1} {x2}')

    def deemb(self, x, param, value=None):
        """Get/set a de-embedding option parameter, e.g. PORT, DELAY [s], DCLOSS [dB],
        LOSS [dB], FREQuency [Hz] (port extension); PORT, ADD (matching network);
        IMPedance [Ohm] (renormalization)."""
        cmd = f':VNA:DEEMB:{x}:{param}'
        if value is None:
            return self.query(cmd + '?')
        if isinstance(value, bool):
            value = _fmt_bool(value)
        self.write(f'{cmd} {value}')

    def port_extension(self, port, delay, dc_loss=0, loss=0, loss_freq=1e9):
        """Convenience: add a port extension (delay in s, losses in dB)."""
        x = self.deemb_new('PORT_EXTENSION')
        self.deemb(x, 'PORT', port)
        self.deemb(x, 'DELAY', f'{delay:g}')
        self.deemb(x, 'DCLOSS', dc_loss)
        self.deemb(x, 'LOSS', loss)
        self.deemb(x, 'FREQ', f'{loss_freq:.0f}')
        return x

    def mn_new(self, x, component, pos=None):
        """Add a matching-network component (SeriesR, SeriesL, SeriesC, ParallelR,
        ParallelL, ParallelC, Touchstone_Through, Touchstone_Shunt)."""
        self.write(f':VNA:DEEMB:{x}:NEW {component}' + (f' {pos}' if pos is not None else ''))

    def mn_value(self, x, y, value=None):
        if value is None:
            return self.query_float(f':VNA:DEEMB:{x}:{y}:VAL?')
        self.write(f':VNA:DEEMB:{x}:{y}:VAL {value:g}')

    def mn_file(self, x, y, filename):
        self.write(f':VNA:DEEMB:{x}:{y}:FILE {filename}')

    # ------------------------------------------------------------------
    # Signal generator
    # ------------------------------------------------------------------
    def gen_frequency(self, freq=None):
        return self._setget(':GEN:FREQ', freq, fmt='{:.0f}')

    def gen_level(self, dBm=None):
        return self._setget(':GEN:LVL', dBm, fmt='{:.2f}')

    def gen_port(self, port=None):
        """0 = off, 1 or 2 = output port."""
        return self._setget(':GEN:PORT', port, conv=int, fmt='{:d}')

    def generator(self, freq, level, port=1):
        """Switch to generator mode and output a CW signal."""
        self.mode('GEN')
        self.gen_level(level)
        self.gen_frequency(freq)
        self.gen_port(port)

    def output(self, state=None):
        """Generator output on port 1 (True) or off (False)."""
        if state is None:
            return self.gen_port() != 0
        self.gen_port(1 if state else 0)

    # ------------------------------------------------------------------
    # Spectrum analyzer
    # ------------------------------------------------------------------
    def sa_start(self, f=None):
        return self._setget(':SA:FREQ:START', f, fmt='{:.0f}')

    def sa_stop(self, f=None):
        return self._setget(':SA:FREQ:STOP', f, fmt='{:.0f}')

    def sa_center(self, f=None):
        return self._setget(':SA:FREQ:CENT', f, fmt='{:.0f}')

    def sa_span(self, f=None):
        return self._setget(':SA:FREQ:SPAN', f, fmt='{:.0f}')

    def sa_full_span(self):
        self.write(':SA:FREQ:FULL')

    def sa_zero_span(self):
        self.write(':SA:FREQ:ZERO')

    def sa_rbw(self, bw=None):
        return self._setget(':SA:ACQ:IFBW', bw, fmt='{:.0f}')

    def sa_window(self, window=None):
        """'NONE', 'KAISER', 'HANN' or 'FLATTOP'."""
        return self._setget(':SA:ACQ:WIND', window, conv=str)

    def sa_detector(self, det=None):
        """'+PEAK', '-PEAK', 'NORMAL', 'SAMPLE' or 'AVERAGE'."""
        return self._setget(':SA:ACQ:DET', det, conv=str)

    def sa_averages(self, n=None):
        return self._setget(':SA:ACQ:AVG', n, conv=int, fmt='{:d}')

    def sa_single(self, state=None):
        return self._setget(':SA:ACQ:SINGLE', state, conv=bool)

    def sa_signal_id(self, state=None):
        return self._setget(':SA:ACQ:SIG', state, conv=bool)

    def sa_run(self):
        self.write(':SA:ACQ:RUN')

    def sa_halt(self):
        self.write(':SA:ACQ:STOP')

    def sa_finished(self):
        return self.query_bool(':SA:ACQ:FIN?')

    def sa_tracking(self, enable=None, port=None, level=None, offset=None):
        """Tracking generator; with no arguments returns its settings."""
        if enable is None and port is None and level is None and offset is None:
            return {'enable': self.query_bool(':SA:TRACK:EN?'),
                    'port': self.query_int(':SA:TRACK:PORT?'),
                    'level': self.query_float(':SA:TRACK:LVL?'),
                    'offset': self.query_float(':SA:TRACK:OFF?')}
        if port is not None:
            self.write(f':SA:TRACK:PORT {port:d}')
        if level is not None:
            self.write(f':SA:TRACK:LVL {level:.2f}')
        if offset is not None:
            self.write(f':SA:TRACK:OFF {offset:.0f}')
        if enable is not None:
            self.write(f':SA:TRACK:EN {_fmt_bool(enable)}')

    def sa_normalize(self, enable=None, level=None, measure=False):
        if level is not None:
            self.write(f':SA:TRACK:NORM:LVL {level:.2f}')
        if enable is not None:
            self.write(f':SA:TRACK:NORM:EN {_fmt_bool(enable)}')
        if measure:
            self.write(':SA:TRACK:NORM:MEAS')
        if enable is None and level is None and not measure:
            return self.query_bool(':SA:TRACK:NORM:EN?')

    def sa_traces(self):
        return [t for t in self.query(':SA:TRAC:LIST?').split(',') if t]

    def sa_trace_data(self, trace='PORT1', timeout=None):
        """Return (freq, dBm) numpy arrays."""
        arr = self.parse_trace(self.query(f':SA:TRAC:DATA? {trace}', timeout=timeout), ncols=2)
        return arr[:, 0], arr[:, 1]

    def sa_sweep(self, traces=('PORT1',), timeout=600):
        """Single (averaged) SA sweep. Returns (freq, dBm) or (freq, dict)."""
        single_trace = isinstance(traces, str)
        if single_trace:
            traces = (traces,)
        self.mode('SA')
        self.sa_single(True)
        self.sa_run()
        t0 = time.time()
        while self.sa_finished() and time.time() - t0 < 0.3:
            time.sleep(0.02)
        while not self.sa_finished():
            if time.time() - t0 > timeout:
                raise TimeoutError("SA sweep did not finish in time.")
            time.sleep(0.1)
        out = {}
        for tr in traces:
            f, out[tr] = self.sa_trace_data(tr)
        return (f, out[traces[0]]) if single_trace else (f, out)

    # ------------------------------------------------------------------
    # Manual control (LibreVNA v1 custom driver)
    # ------------------------------------------------------------------
    def manual(self, name, value=None):
        """Generic access to MANual:<name> (call manual_start() first), e.g.
        manual('HSRC_FREQ', 1e9), manual('PORT1_MAG')."""
        if value is None:
            return self.query(f':MAN:{name}?')
        if isinstance(value, bool):
            value = _fmt_bool(value)
        self.write(f':MAN:{name} {value}')

    def manual_start(self):
        self.write(':MAN:STA')

    def manual_stop(self):
        self.write(':MAN:STO')

    # ------------------------------------------------------------------
    # Streaming servers (enable them in Window->Preferences->Streaming Servers)
    # ------------------------------------------------------------------
    def stream(self, port=19000, n_points=None, timeout=10):
        """
        Generator yielding measurement points from a streaming server as dicts.
        For VNA data, the S-parameters in d['measurements'] are complex.
        Stops after n_points (if given).
        """
        with socket.create_connection((self.host, port), timeout=timeout) as s:
            buf = b''
            count = 0
            while n_points is None or count < n_points:
                while b'\n' not in buf:
                    chunk = s.recv(65536)
                    if not chunk:
                        return
                    buf += chunk
                line, buf = buf.split(b'\n', 1)
                d = json.loads(line)
                if 'Z0' in d:
                    m = d['measurements']
                    d['measurements'] = {k[:-5]: complex(m[k], m[k[:-5] + '_imag'])
                                         for k in m if k.endswith('_real')}
                count += 1
                yield d


if __name__ == '__main__':
    vna = LibreVNA()
    print(vna.device_info())
    vna.setup_sweep(start=1e9, stop=2e9, points=201, ifbw=1e3, power=-10)
    f, s11 = vna.sweep('S11')
    print(f[:5], 20 * np.log10(np.abs(s11[:5])))
    vna.close()
