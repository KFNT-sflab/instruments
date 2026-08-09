#
# TODO: use the Instrument base class
#

import matplotlib as mpl
mpl.use('qt5agg')
import matplotlib.pyplot as plt
import matplotlib.animation as anim
import numpy as np
import lmfit as lm

import serial
import struct
import time
import math
from typing import Tuple, List, Optional
from tqdm import tqdm

def peak(f, f0, A, w, phi, b1, b2, b1i, b2i):
    p = A*f0*w/(f**2 - f0**2 - 1j*w*f)*np.exp(1j*phi)
    background = b1 + b2*f + 1j*(b1i + b2i*f)
    return p + background

model = lm.Model(peak)

def fit_peak(f, s11, p0=None):
    if p0 is None:
        p0 = model.make_params(f0=5.09, A=0.4, w=0.001, phi=-np.pi/2, b1=-1.4, b2=0, b1i=0, b2i=0)
    
    result = model.fit(s11, p0, f=f)
    return result
    

class LiteVNA:
    """
    A Python class to control the LiteVNA over its USB (CDC) serial interface.

    This class implements the protocol described in the "Appendix- USB data interface"
    of the LiteVNA User Guide.
    """

    # Register Addresses from the manual (Page 26)
    REG_SWEEP_START_HZ = 0x00  # uint64
    REG_SWEEP_STEP_HZ = 0x10   # uint64
    REG_SWEEP_POINTS = 0x20    # uint16
    REG_VALUES_FIFO = 0x30     # FIFO
    REG_CHANNEL_SELECT = 0x44  # uint8 (0x00=S11&S21, 0x01=S11, 0x02=S21)
    REG_FW_MAJOR = 0xF3        # uint8
    REG_FW_MINOR = 0xF4        # uint8

    # Command opcodes from the manual (Page 25)
    CMD_READ = 0x10
    CMD_READ2 = 0x11
    CMD_READ4 = 0x12
    CMD_READFIFO = 0x18
    CMD_WRITE = 0x20
    CMD_WRITE2 = 0x21
    CMD_WRITE4 = 0x22
    CMD_WRITE8 = 0x23 # Used for uint64

    def __init__(self, port: str):
        """
        Initializes the LiteVNA controller.

        Args:
            port: The COM port (e.g., 'COM3' on Windows) or device path
                  (e.g., '/dev/ttyACM0' on Linux) for the LiteVNA.
        """
        self.port = port
        self.ser: Optional[serial.Serial] = None
        self.num_points = 101  # Default, will be set by set_frequency_range
        self.start_hz = 0
        self.step_hz = 0

    def open(self):
        """
        Opens the serial connection to the VNA.
        The baudrate is often ignored for USB CDC devices but is set for compatibility.
        """
        try:
            self.ser = serial.Serial(self.port, baudrate=115200, timeout=2)
            print(f"Successfully opened port {self.port}")
        except serial.SerialException as e:
            print(f"Error opening serial port {self.port}: {e}")
            self.ser = None
            raise

    def close(self):
        """Closes the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"Closed port {self.port}")
            self.ser = None

    def __enter__(self):
        """Context manager entry: opens the connection."""
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: closes the connection."""
        self.close()

    def _check_connection(self):
        """Raises an error if the serial port is not open."""
        if not self.ser or not self.ser.is_open:
            raise ConnectionError("LiteVNA is not connected. Call open() first.")

    # --- Low-Level Protocol Methods ---

    def _write_u8(self, reg_addr: int, value: int):
        """Writes a 1-byte (uint8) value to a register."""
        self._check_connection()
        cmd = bytes([self.CMD_WRITE, reg_addr, value & 0xFF])
        self.ser.write(cmd)

    def _write_u16(self, reg_addr: int, value: int):
        """Writes a 2-byte (uint16) value to a register (little-endian)."""
        self._check_connection()
        data = struct.pack('<H', value)
        cmd = bytes([self.CMD_WRITE2, reg_addr]) + data
        self.ser.write(cmd)

    def _write_u64(self, reg_addr: int, value: int):
        """Writes an 8-byte (uint64) value to a register (little-endian)."""
        self._check_connection()
        data = struct.pack('<Q', value)
        # Uses CMD_WRITE8 (0x23) which writes 8 bytes
        cmd = bytes([self.CMD_WRITE8, reg_addr]) + data
        self.ser.write(cmd)

    def _read_u8(self, reg_addr: int) -> int:
        """Reads a 1-byte (uint8) value from a register."""
        self._check_connection()
        cmd = bytes([self.CMD_READ, reg_addr])
        self.ser.write(cmd)
        response = self.ser.read(1)
        if len(response) != 1:
            raise TimeoutError("Timeout reading from LiteVNA register.")
        return struct.unpack('<B', response)[0]

    def _clear_fifo(self):
        """
        Clears the VALUES_FIFO by writing a dummy value to it,
        as per the manual (Page 27).
        """
        self._write_u8(self.REG_VALUES_FIFO, 0x01) # Value doesn't matter

    def _read_fifo(self, num_points: int) -> bytes:
        """
        Reads the specified number of data points from the FIFO.
        Each point is 32 bytes.
        """
        self._check_connection()
        
        # Command is [0x18, REG_ADDR, NN_low, NN_high]
        # where NN is the number of *values* (points) to read
        num_points_bytes = struct.pack('<H', num_points)
        # num_points = np.uint(num_points)
        # , np.uint8(num_points & 0xff), np.uint8(num_points >> 8)
        # cmd = bytes([self.CMD_READFIFO, self.REG_VALUES_FIFO]) + num_points_bytes

        data = b''

        num = num_points
        if num_points > 255:
            pbar = tqdm(total=num_points)
        # with tqdm(total=num_points) as pbar:
        while num>0:
            num_low = min(num, 255)
            num -= num_low
            cmd = bytes([self.CMD_READFIFO, self.REG_VALUES_FIFO, num_low])
            # print(cmd)

            self.ser.write(cmd)
            data += self.ser.read(num_low*32)
            if num_points > 255:
                pbar.update(num_low)
        
        if num_points > 255:
            pbar.close()
        
        bytes_to_read = num_points * 32
        if len(data) != bytes_to_read:
            raise TimeoutError(f"FIFO read timeout: Expected {bytes_to_read} bytes, got {len(data)}")
        else:
            pass
        
        return data

    def _parse_sweep_data(self, data: bytes) -> Tuple[List[int], List[complex], List[complex]]:
        """
        Parses the 32-byte-per-point raw data from the FIFO.
        
        Returns:
            (list[complex], list[complex]): A tuple containing (s11_data, s21_data)
        """
        s11_list = []
        s21_list = []
        fidx_list = []
        
        num_points_received = len(data) // 32
        
        for i in range(num_points_received):
            chunk = data[i * 32 : (i + 1) * 32]
            
            # Unpack data based on FIFO data format (Page 27)
            # All are int32, little-endian
            fwd0Re = struct.unpack('<i', chunk[0:4])[0]
            fwd0Im = struct.unpack('<i', chunk[4:8])[0]
            rev0Re = struct.unpack('<i', chunk[8:12])[0]
            rev0Im = struct.unpack('<i', chunk[12:16])[0]
            rev1Re = struct.unpack('<i', chunk[16:20])[0]
            rev1Im = struct.unpack('<i', chunk[20:24])[0]
            freqIndex = struct.unpack('<H', chunk[24:26])[0] # We can use this for validation
            
            # Create complex numbers
            fwd0 = complex(fwd0Re, fwd0Im) # Reference channel
            rev0 = complex(rev0Re, rev0Im) # S11 channel (reflection)
            rev1 = complex(rev1Re, rev1Im) # S21 channel (transmission)
            
            # Calculate S-parameters (as per manual, divide by reference)
            if fwd0 == 0:
                s11 = complex(float('inf'), float('inf'))
                s21 = complex(float('inf'), float('inf'))
            else:
                s11 = rev0 / fwd0
                s21 = rev1 / fwd0
                
            s11_list.append(s11)
            s21_list.append(s21)
            fidx_list.append(freqIndex)
            
        return fidx_list, s11_list, s21_list

    # --- Public API Methods ---

    def get_version(self) -> str:
        """Reads and returns the device firmware version string."""
        major = self._read_u8(self.REG_FW_MAJOR)
        minor = self._read_u8(self.REG_FW_MINOR)
        return f"{major}.{minor}"

    def set_channels(self, s11: bool = True, s21: bool = True):
        """
        Configures which S-parameters to measure.
        Writing to this register puts the VNA in USB data mode.

        Args:
            s11: True to measure S11.
            s21: True to measure S21.
        """
        val = 0x00 # Default to S11 and S21
        if s11 and not s21:
            val = 0x01
        elif not s11 and s21:
            val = 0x02
        
        self._write_u8(self.REG_CHANNEL_SELECT, val)
        print(f"Channels set to: S11={s11}, S21={s21} (reg_val={val})")

    def set_frequency_range(self, start_hz: int, stop_hz: int, num_points: int):
        """
        Sets the frequency sweep parameters.
        Writing to these registers puts the VNA in USB data mode.

        Args:
            start_hz: The starting frequency in Hz.
            stop_hz: The stopping frequency in Hz.
            num_points: The number of points in the sweep.
        """
        if num_points <= 1:
            step_hz = 0
        else:
            step_hz = int(round((stop_hz - start_hz) / (num_points - 1)))
        
        self.start_hz = start_hz
        self.step_hz = step_hz
        self.num_points = num_points
        
        self._write_u64(self.REG_SWEEP_START_HZ, start_hz)
        self._write_u64(self.REG_SWEEP_STEP_HZ, step_hz)
        self._write_u16(self.REG_SWEEP_POINTS, num_points)
        print(f"Sweep set: {start_hz/1e6:.2f} MHz to {stop_hz/1e6:.2f} MHz in {num_points} points")
        
        # Give the VNA a moment to process the new settings
        time.sleep(0.1)

    def read_sweep(self) -> Tuple[np.ndarray, List[complex], List[complex]]:
        """
        Performs a full frequency sweep and returns the data.

        Returns:
            A tuple containing:
            - (list[int]): List of frequencies in Hz.
            - (list[complex]): List of complex S11 data.
            - (list[complex]): List of complex S21 data.
        """
        self._check_connection()
        
        # 1. Clear any stale data from the FIFO
        self._clear_fifo()
        
        # 2. Wait for the VNA to perform a sweep and fill the FIFO
        # The time this takes depends on sweep points and averaging.
        # We'll poll, but a simple sleep is easier to start.
        # A 101-point sweep is fast, but let's be safe.
        # TODO: A more robust method would be to poll the FIFO or calculate sweep time.
        # time.sleep(1) # A guess, adjust as needed.
        
        # 3. Read all points from the FIFO
        try:
            raw_data = self._read_fifo(self.num_points)
        except TimeoutError as e:
            print(f"Warning: {e}. Retrying after a longer delay.")
            time.sleep(1) # Longer delay
            self._clear_fifo() # Clear again
            time.sleep(3) # Wait for new sweep
            raw_data = self._read_fifo(self.num_points)
        
        # 4. Parse the raw data
        fidx, s11_data, s21_data = self._parse_sweep_data(raw_data)
        
        # 5. Generate the frequency list
        frequencies = np.array([self.start_hz + i * self.step_hz for i in range(self.num_points)])[fidx]
        
        return frequencies, s11_data, s21_data
    
    def get_vals(self, num=1):
        raw_data = self._read_fifo(num)
        fidx, s11_data, s21_data = self._parse_sweep_data(raw_data)
        frequencies = np.array([self.start_hz + i * self.step_hz for i in range(self.num_points)])[fidx]

        if num > 1:
            return frequencies, s11_data, s21_data
        else:
            return frequencies[0], s11_data[0], s21_data[0]



if __name__ == "__main__":
    # --- Example Usage ---
    # NOTE: Replace 'COM3' with your VNA's actual serial port.
    # On Linux, it might be '/dev/ttyACM0'
    # On macOS, it might be '/dev/cu.usbmodem...'
    
    VNA_PORT = 'COM4' # <-- **** CHANGE THIS TO YOUR PORT ****

    t0 = time.time()
    ts = []
    f0s = []
    try:
        with LiteVNA(VNA_PORT) as vna:
            
            # 1. Get Firmware Version
            version = vna.get_version()
            print(f"Connected to LiteVNA, Firmware: {version}")
            
            # 2. Configure Sweep
            start_f = int(5.05e9)
            stop_f = int(5.15e9)
            points = 500
            
            vna.set_channels(s11=True, s21=True)
            vna.set_frequency_range(start_f, stop_f, points)
            
            # 3. Read Sweep Data
            print("Reading sweep...")
            fig = plt.figure(layout='constrained')
            gs = fig.add_gridspec(2, 2)
            ax_logmagS11 = fig.add_subplot(gs[0, 0])
            ax_phaseS11 = fig.add_subplot(gs[1, 0], sharex=ax_logmagS11)
            ax_freq = fig.add_subplot(gs[:, 1])
                        
            ax_phaseS11.set_xlabel('Frequency (MHz)')
            ax_logmagS11.set_ylabel('|S11| (dB)')
            ax_phaseS11.set_ylabel('Phase (deg)')
            ax_freq.set_xlabel('Time (s)')
            ax_freq.set_ylabel('Frequency (GHz)')
            
            frequencies, s11, s21 = vna.read_sweep()
            
            print(f"\n--- Sweep Results (Read {len(frequencies)} points) ---")

            """ fs = []
            s11_dbs = []
            s11_phases = []

            for i in tqdm(range(points)):
                f, s11, s21 = vna.get_vals()

                s11_db = 20 * math.log10(abs(s11))
                fs.append(f)
                s11_dbs.append(s11_db)
                s11_phases.append(np.angle(s11))

                if i%20 != 0:
                    continue
                ax_logmagS11.clear()
                ax_logmagS11.plot(fs, s11_dbs, 'o')

                ax_phaseS11.clear()
                ax_phaseS11.plot(fs, s11_dbs, 'o')

                fig.canvas.flush_events()
                plt.pause(0.001) """


            s11_db = [20 * math.log10(abs(s)) for s in s11]
            s11_phase = np.unwrap(np.angle(s11))
            s11_phase -= s11_phase.mean()
            
            # frequencies = fs
            absS11_plot = ax_logmagS11.plot(frequencies, s11_db, 'o')
            phaseS11_plot = ax_phaseS11.plot(frequencies, s11_phase, 'o')

            fit = fit_peak(frequencies/1e9, s11)
            fitplot_S11db = ax_logmagS11.plot(frequencies, 20*np.log10(abs(fit.best_fit)), 'r-')
            fit_phase = np.unwrap(np.angle(fit.best_fit))
            fit_phase -= fit_phase.mean()
            fitplot_S11phase = ax_phaseS11.plot(frequencies, fit_phase, 'r-')

            ts.append(time.time() - t0)
            f0s.append(fit.params['f0'].value)

            freqplot = ax_freq.plot(ts, f0s, '-o')
            ax_freq.set_xlim(0, 100)
            plt.pause(0.001)

            p0 = fit.params

            def update(frame):
                frequencies, s11, s21 = vna.read_sweep()
                s11_db = [20 * math.log10(abs(s)) for s in s11]
                s11_phase = np.unwrap(np.angle(s11))
                s11_phase -= s11_phase.mean()
                absS11_plot[0].set_data(frequencies, s11_db)
                phaseS11_plot[0].set_data(frequencies, s11_phase)

                try:
                    fit = fit_peak(frequencies/1e9, s11, p0=p0)
                    idx = np.argsort(frequencies)
                    fit_phase = np.unwrap(np.angle(fit.best_fit))
                    fit_phase -= fit_phase.mean()
                    fitplot_S11db[0].set_data(frequencies[idx], 20*np.log10(abs(fit.best_fit[idx])))
                    fitplot_S11phase[0].set_data(frequencies[idx], fit_phase[idx])

                    ts.append(time.time() - t0)
                    f0s.append(fit.params['f0'].value)
                    freqplot[0].set_data(ts, f0s)
                    ax_freq.set_xlim(0, ts[-1])
                    ax_freq.set_ylim(np.min(f0s), np.max(f0s))
                except:
                    print("Fit failed.")
                
                plt.pause(0.001)
            
            # an = anim.FuncAnimation(fig, update, interval=0)
            while True:
                update(None)
                plt.pause(0.001)
            
            plt.show()
    except serial.SerialException:
        print(f"Error: Could not find or open port '{VNA_PORT}'.")
        print("Please check your device connection and port name.")
    except ConnectionError as e:
        print(f"Connection Error: {e}")
    except TimeoutError as e:
        print(f"VNA Timeout: {e}. Try increasing delays in read_sweep().")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")