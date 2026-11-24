#!/usr/bin/env python3
"""
Windfreak SynthHD Mini server.

The windfreak library's SynthHD class does not support the SynthHD Mini
(it crashes on the Mini's hardware version and uses commands the Mini does not
have, e.g. channel select "C"). So this file defines a SynthHDMini class built
on the library's SerialDevice, using ONLY the commands documented in
WFT_SynthHDMini_API_11a.pdf.

The server opens the Mini once at startup and keeps it open while it runs.
Clients (WindfreakMiniClient.py) send a message

    (command, value)

e.g. ("set_frequency", 5e9). The server runs the matching SynthHDMini call,
e.g. mini.frequency = 5e9, and sends back

    ("OK", result)        or        ("ERROR", "error message")

Usage:
    python WindfreakMiniServer.py COM6
"""

import argparse
import logging as log
import os
import tempfile
import threading
from multiprocessing.connection import Listener

from windfreak.device import SerialDevice

PORT_FILE = os.path.join(tempfile.gettempdir(), "windfreak_mini_server_port.txt")


def check_range(name, value, low, high):
    """Raise ValueError if value is not a number within [low, high]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name}: expected a number, got {value!r}")
    if not low <= value <= high:
        raise ValueError(f"{name}: {value} is outside the allowed range [{low}, {high}]")


def check_bool(name, value):
    if not isinstance(value, bool):
        raise TypeError(f"{name}: expected True or False, got {value!r}")


class SynthHDMini(SerialDevice):
    """Windfreak SynthHD Mini (single channel). Commands from WFT_SynthHDMini_API_11a.pdf."""

    # Serial commands, same format as windfreak.SynthHD.API:
    # name: (type, write command, read command)
    API = {
        "frequency":        (float, "f{:.8f}", "f?"),  # MHz, 10 - 15000
        "power":            (float, "W{:.3f}", "W?"),  # dBm, -20 - +20
        "calibrated":       (bool,  None,      "V"),   # amplitude calibration succeeded
        "vga_dac":          (int,   "a{}",     "a?"),  # raw VGA DAC, 0 - 4000
        "rf_enable":        (bool,  "h{}",     "h?"),  # RF mute: 1 = not muted, 0 = muted
        "pll_power_on":     (bool,  "E{}",     "E?"),  # PLL on/off
        "charge_pump":      (int,   "U{}",     "U?"),  # PLL charge pump current, 1 - 15
        "ref_doubler":      (bool,  "b{}",     "b?"),  # reference doubler on/off
        "channelspacing":   (float, "i{:.3f}", "i?"),  # Hz, 0.01 - 10000000
        "reference_mode":   (int,   "x{}",     "x?"),  # 0 = external, 1 = internal 27 MHz
        "ref_frequency":    (float, "*{:.3f}", "*?"),  # MHz, 10 - 100

        "sweep_freq_low":   (float, "l{:.8f}", "l?"),  # MHz
        "sweep_freq_high":  (float, "u{:.8f}", "u?"),  # MHz
        "sweep_freq_step":  (float, "s{:.8f}", "s?"),  # MHz
        "sweep_time_step":  (float, "t{:.3f}", "t?"),  # ms, 0.25 - 60000
        "sweep_power_low":  (float, "[{:.3f}", "[?"),  # dBm
        "sweep_power_high": (float, "]{:.3f}", "]?"),  # dBm
        "sweep_direction":  (int,   "^{}",     "^?"),  # 1 = up, 0 = down
        "sweep_type":       (int,   "X{}",     "X?"),  # 0 = linear, 1 = tabular (list)
        "sweep_display":    (int,   "d{}",     "d?"),  # 0 = off, 1 = freq, 2 = freq + amp
        "sweep_single":     (bool,  "g{}",     "g?"),  # run sweep
        "sweep_cont":       (bool,  "c{}",     "c?"),  # sweep continuously

        "trig_function":    (int,   "w{}",     "w?"),  # trigger connector function, 0 - 10
        "trig_polarity":    (bool,  "Y{}",     "Y?"),  # 1 = active high, 0 = active low
        "trigger_level":    (bool,  None,      "I"),   # trigger input: 1 = high, 0 = low

        "am_time_step":     (int,   "F{}",     "F?"),  # us
        "am_num_samples":   (int,   "q{}",     "q?"),  # cycles in one burst
        "am_cont":          (bool,  "A{}",     "A?"),  # continuous AM on/off
        "am_lookup_table":  ((int, float), "@{}a{:.3f}", "@{}a?"),  # row 0 - 199, dBm

        "pulse_on_time":    (int,   "P{}",     "P?"),  # us, 1 - 10000000
        "pulse_off_time":   (int,   "O{}",     "O?"),  # us, 1 - 10000000
        "pulse_num_rep":    (int,   "R{}",     "R?"),  # 1 - 65000
        "pulse_invert":     (bool,  ":{}",     ":?"),
        "pulse_single":     ((),    "G",       None),  # run one pulse burst
        "pulse_cont":       (bool,  "j{}",     "j?"),  # continuous pulse modulation

        "fm_frequency":     (int,   "<{}",     "<?"),  # Hz, 1 - 5000
        "fm_deviation":     (int,   ">{}",     ">?"),  # +/- Hz
        "fm_num_samples":   (int,   ",{}",     ",?"),  # FM cycles in a burst
        "fm_mod_type":      (int,   ";{}",     ";?"),  # sinusoid / chirp, see fm_mod_type
        "fm_cont":          (bool,  "/{}",     "/?"),  # continuous FM on/off

        "pll_lock":         (bool,  None,      "p"),   # 1 = locked
        "temperature":      (float, None,      "z"),   # Celsius
        "comm_mode":        (int,   None,      "m"),   # 0 = USB, 1 = UART
        "fw_version":       (str,   None,      "v0"),
        "hw_version":       (str,   None,      "v1"),
        "model_type":       (str,   None,      "+"),
        "serial_number":    (int,   None,      "-"),
        "save":             ((),    "e",       None),  # write all settings to EEPROM
    }  # fmt: skip

    reference_modes = ("external", "internal 27mhz")
    trigger_modes = (
        "disabled",
        "full frequency sweep",
        "single frequency step",
        "stop all",
        "rf enable",
        "remove interrupts",
        "reserved",
        "reserved",
        "am modulation",
        "fm modulation",
        "sleep",
    )
    frequency_range = {"start": 10e6, "stop": 15000e6}  # Hz
    power_range = {"start": -20.0, "stop": 20.0}  # dBm
    vga_dac_range = {"start": 0, "stop": 4000}
    reference_frequency_range = {"start": 10e6, "stop": 100e6}  # Hz

    def _query(self, data):
        # Throw away any old unread lines (e.g. from sweep display) so the answer matches the question.
        self._dev.reset_input_buffer()
        return super()._query(data)

    def _query_until_eom(self, data):
        """Send a query whose answer is several lines ending with 'EOM.'; return the lines."""
        self._dev.reset_input_buffer()
        self._write(data)
        lines = []
        while True:
            line = self._read()  # raises TimeoutError if the device stops answering
            if line == "EOM.":
                return lines
            lines.append(line)

    # ---------------- general ----------------
    def init(self):
        """Put device into a known, safe state: modulations, sweep and triggers off, output off."""
        self.sweep_enable = False
        self.sweep_run = False
        self.am_enable = False
        self.pulse_mod_enable = False
        self.fm_enable = False
        self.trigger_mode = "disabled"
        self.reference_mode = "internal 27mhz"
        self.enable = False

    def save(self):
        """Save all current settings to EEPROM (used as power-up defaults)."""
        self.write("save")

    def settings(self):
        """All settings in the device's programming format ('?1'), as a list of strings."""
        return self._query_until_eom("?1")

    @property
    def model_type(self):
        return self.read("model_type")

    @property
    def serial_number(self):
        return self.read("serial_number")

    @property
    def firmware_version(self):
        return self.read("fw_version")

    @property
    def hardware_version(self):
        return self.read("hw_version")

    @property
    def temperature(self):
        """Temperature in Celsius."""
        return self.read("temperature")

    @property
    def communication_mode(self):
        """'USB' or 'UART'."""
        return ("USB", "UART")[self.read("comm_mode")]

    # ---------------- RF output ----------------
    @property
    def frequency(self):
        """Frequency in Hz."""
        return self.read("frequency") * 1e6

    @frequency.setter
    def frequency(self, value):
        check_range("frequency (Hz)", value, self.frequency_range["start"], self.frequency_range["stop"])
        self.write("frequency", value / 1e6)

    @property
    def power(self):
        """Power in dBm."""
        return self.read("power")

    @power.setter
    def power(self, value):
        check_range("power (dBm)", value, self.power_range["start"], self.power_range["stop"])
        self.write("power", value)

    @property
    def calibrated(self):
        """True if amplitude calibration succeeded after the last frequency/power change."""
        return self.read("calibrated")

    @property
    def vga_dac(self):
        """Raw VGA DAC value, 0 - 4000 (bypasses the power calibration)."""
        return self.read("vga_dac")

    @vga_dac.setter
    def vga_dac(self, value):
        check_range("vga_dac", value, self.vga_dac_range["start"], self.vga_dac_range["stop"])
        self.write("vga_dac", int(value))

    @property
    def rf_enable(self):
        """RF not muted (True) / muted (False)."""
        return self.read("rf_enable")

    @rf_enable.setter
    def rf_enable(self, value):
        check_bool("rf_enable", value)
        self.write("rf_enable", value)

    @property
    def pll_enable(self):
        """PLL, VCO and internal reference powered on."""
        return self.read("pll_power_on")

    @pll_enable.setter
    def pll_enable(self, value):
        check_bool("pll_enable", value)
        self.write("pll_power_on", value)

    @property
    def enable(self):
        """Output on: PLL powered and RF not muted."""
        return self.pll_enable and self.rf_enable

    @enable.setter
    def enable(self, value):
        check_bool("enable", value)
        self.pll_enable = value
        self.rf_enable = value

    @property
    def lock_status(self):
        """True if the PLL is locked."""
        return self.read("pll_lock")

    # ---------------- PLL / reference ----------------
    @property
    def charge_pump_current(self):
        """PLL charge pump current setting, 1 - 15."""
        return self.read("charge_pump")

    @charge_pump_current.setter
    def charge_pump_current(self, value):
        check_range("charge_pump_current", value, 1, 15)
        self.write("charge_pump", int(value))

    @property
    def reference_doubler(self):
        return self.read("ref_doubler")

    @reference_doubler.setter
    def reference_doubler(self, value):
        check_bool("reference_doubler", value)
        self.write("ref_doubler", value)

    @property
    def channel_spacing(self):
        """Channel spacing (frequency resolution) in Hz, 0.01 - 10000000."""
        return self.read("channelspacing")

    @channel_spacing.setter
    def channel_spacing(self, value):
        check_range("channel_spacing (Hz)", value, 0.01, 10_000_000)
        self.write("channelspacing", value)

    @property
    def reference_mode(self):
        """'external' or 'internal 27mhz'."""
        return self.reference_modes[self.read("reference_mode")]

    @reference_mode.setter
    def reference_mode(self, value):
        if value not in self.reference_modes:
            raise ValueError(f"reference_mode: expected one of {self.reference_modes}")
        self.write("reference_mode", self.reference_modes.index(value))

    @property
    def reference_frequency(self):
        """External reference frequency in Hz."""
        return self.read("ref_frequency") * 1e6

    @reference_frequency.setter
    def reference_frequency(self, value):
        r = self.reference_frequency_range
        check_range("reference_frequency (Hz)", value, r["start"], r["stop"])
        self.write("ref_frequency", value / 1e6)

    # ---------------- sweep ----------------
    @property
    def sweep_freq_low(self):
        """Sweep lower frequency in Hz."""
        return self.read("sweep_freq_low") * 1e6

    @sweep_freq_low.setter
    def sweep_freq_low(self, value):
        check_range("sweep_freq_low (Hz)", value, self.frequency_range["start"], self.frequency_range["stop"])
        self.write("sweep_freq_low", value / 1e6)

    @property
    def sweep_freq_high(self):
        """Sweep upper frequency in Hz."""
        return self.read("sweep_freq_high") * 1e6

    @sweep_freq_high.setter
    def sweep_freq_high(self, value):
        check_range("sweep_freq_high (Hz)", value, self.frequency_range["start"], self.frequency_range["stop"])
        self.write("sweep_freq_high", value / 1e6)

    @property
    def sweep_freq_step(self):
        """Sweep step size in Hz."""
        return self.read("sweep_freq_step") * 1e6

    @sweep_freq_step.setter
    def sweep_freq_step(self, value):
        check_range("sweep_freq_step (Hz)", value, 0.01, self.frequency_range["stop"])
        self.write("sweep_freq_step", value / 1e6)

    @property
    def sweep_time_step(self):
        """Time per sweep step in ms, 0.25 - 60000."""
        return self.read("sweep_time_step")

    @sweep_time_step.setter
    def sweep_time_step(self, value):
        check_range("sweep_time_step (ms)", value, 0.25, 60000)
        self.write("sweep_time_step", value)

    @property
    def sweep_power_low(self):
        """Sweep power at the lower frequency, dBm."""
        return self.read("sweep_power_low")

    @sweep_power_low.setter
    def sweep_power_low(self, value):
        check_range("sweep_power_low (dBm)", value, self.power_range["start"], self.power_range["stop"])
        self.write("sweep_power_low", value)

    @property
    def sweep_power_high(self):
        """Sweep power at the upper frequency, dBm."""
        return self.read("sweep_power_high")

    @sweep_power_high.setter
    def sweep_power_high(self, value):
        check_range("sweep_power_high (dBm)", value, self.power_range["start"], self.power_range["stop"])
        self.write("sweep_power_high", value)

    @property
    def sweep_direction(self):
        """'up' or 'down'."""
        return ("down", "up")[self.read("sweep_direction")]

    @sweep_direction.setter
    def sweep_direction(self, value):
        if value not in ("down", "up"):
            raise ValueError("sweep_direction: expected 'up' or 'down'")
        self.write("sweep_direction", ("down", "up").index(value))

    @property
    def sweep_type(self):
        """'linear' or 'tabular' (list mode)."""
        return ("linear", "tabular")[self.read("sweep_type")]

    @sweep_type.setter
    def sweep_type(self, value):
        if value not in ("linear", "tabular"):
            raise ValueError("sweep_type: expected 'linear' or 'tabular'")
        self.write("sweep_type", ("linear", "tabular").index(value))

    @property
    def sweep_display(self):
        """0 = off, 1 = print frequency, 2 = print frequency and power at every sweep step."""
        return self.read("sweep_display")

    @sweep_display.setter
    def sweep_display(self, value):
        if value not in (0, 1, 2):
            raise ValueError("sweep_display: expected 0, 1 or 2")
        self.write("sweep_display", value)

    @property
    def sweep_run(self):
        """True = start/continue sweep, False = pause."""
        return self.read("sweep_single")

    @sweep_run.setter
    def sweep_run(self, value):
        check_bool("sweep_run", value)
        self.write("sweep_single", value)

    @property
    def sweep_enable(self):
        """Sweep continuously."""
        return self.read("sweep_cont")

    @sweep_enable.setter
    def sweep_enable(self, value):
        check_bool("sweep_enable", value)
        self.write("sweep_cont", value)

    # ---------------- list mode (tabular sweep) ----------------
    # Deleting the table ("Ld") and saving it to nonvolatile memory ("Le") are
    # deliberately not implemented, so the stored table can't be erased from here.
    def list_set(self, index, frequency, power):
        """Store one list point: frequency in Hz, power in dBm."""
        check_range("list index", index, 0, 499)
        check_range("list frequency (Hz)", frequency, self.frequency_range["start"], self.frequency_range["stop"])
        check_range("list power (dBm)", power, self.power_range["start"], self.power_range["stop"])
        self._write(f"L{int(index)}f{frequency / 1e6:.8f}L{int(index)}a{power:.2f}")

    def list_read(self):
        """Return the list table as lines like 'L00f1000.0000000a-30.00'."""
        return self._query_until_eom("L?")

    # ---------------- trigger ----------------
    @property
    def trigger_mode(self):
        """Function of the trigger connector, one of trigger_modes."""
        return self.trigger_modes[self.read("trig_function")]

    @trigger_mode.setter
    def trigger_mode(self, value):
        if value not in self.trigger_modes or value == "reserved":
            raise ValueError(f"trigger_mode: expected one of {self.trigger_modes}")
        self.write("trig_function", self.trigger_modes.index(value))

    @property
    def trigger_polarity(self):
        """'active high' or 'active low'."""
        return ("active low", "active high")[self.read("trig_polarity")]

    @trigger_polarity.setter
    def trigger_polarity(self, value):
        if value not in ("active low", "active high"):
            raise ValueError("trigger_polarity: expected 'active low' or 'active high'")
        self.write("trig_polarity", value == "active high")

    @property
    def trigger_level(self):
        """Current digital level at the trigger input (True = high)."""
        return self.read("trigger_level")

    # ---------------- AM ----------------
    @property
    def am_time_step(self):
        """Extra delay per AM sample in us."""
        return self.read("am_time_step")

    @am_time_step.setter
    def am_time_step(self, value):
        check_range("am_time_step (us)", value, 0, 1e9)
        self.write("am_time_step", int(value))

    @property
    def am_num_samples(self):
        """Number of AM cycles in one burst."""
        return self.read("am_num_samples")

    @am_num_samples.setter
    def am_num_samples(self, value):
        check_range("am_num_samples", value, 0, 1e9)
        self.write("am_num_samples", int(value))

    @property
    def am_enable(self):
        """Continuous AM on/off."""
        return self.read("am_cont")

    @am_enable.setter
    def am_enable(self, value):
        check_bool("am_enable", value)
        self.write("am_cont", value)

    def am_lookup_table_set(self, index, power):
        """Set AM lookup table row index (0 - 199) to power in dBm (-75.0 = row not played)."""
        check_range("AM table index", index, 0, 199)
        check_range("AM table power (dBm)", power, -75.0, self.power_range["stop"])
        self.write("am_lookup_table", int(index), power)

    def am_lookup_table_get(self, index):
        """Power in dBm stored in AM lookup table row index (0 - 199)."""
        check_range("AM table index", index, 0, 199)
        return self.read("am_lookup_table", int(index))

    # ---------------- pulse modulation ----------------
    @property
    def pulse_on_time(self):
        """Pulse on time in us."""
        return self.read("pulse_on_time")

    @pulse_on_time.setter
    def pulse_on_time(self, value):
        check_range("pulse_on_time (us)", value, 1, 10_000_000)
        self.write("pulse_on_time", int(value))

    @property
    def pulse_off_time(self):
        """Pulse off time in us."""
        return self.read("pulse_off_time")

    @pulse_off_time.setter
    def pulse_off_time(self, value):
        check_range("pulse_off_time (us)", value, 1, 10_000_000)
        self.write("pulse_off_time", int(value))

    @property
    def pulse_num_rep(self):
        """Number of pulses in one burst."""
        return self.read("pulse_num_rep")

    @pulse_num_rep.setter
    def pulse_num_rep(self, value):
        check_range("pulse_num_rep", value, 1, 65000)
        self.write("pulse_num_rep", int(value))

    @property
    def pulse_invert(self):
        return self.read("pulse_invert")

    @pulse_invert.setter
    def pulse_invert(self, value):
        check_bool("pulse_invert", value)
        self.write("pulse_invert", value)

    def pulse_single(self):
        """Run one pulse burst."""
        self.write("pulse_single")

    @property
    def pulse_mod_enable(self):
        """Continuous pulse modulation on/off."""
        return self.read("pulse_cont")

    @pulse_mod_enable.setter
    def pulse_mod_enable(self, value):
        check_bool("pulse_mod_enable", value)
        self.write("pulse_cont", value)

    # ---------------- FM ----------------
    @property
    def fm_frequency(self):
        """FM modulation frequency in Hz, 1 - 5000."""
        return self.read("fm_frequency")

    @fm_frequency.setter
    def fm_frequency(self, value):
        check_range("fm_frequency (Hz)", value, 1, 5000)
        self.write("fm_frequency", int(value))

    @property
    def fm_deviation(self):
        """FM deviation in +/- Hz (maximum depends on frequency band, see PDF)."""
        return self.read("fm_deviation")

    @fm_deviation.setter
    def fm_deviation(self, value):
        check_range("fm_deviation (Hz)", value, 0, 30_000_000)
        self.write("fm_deviation", int(value))

    @property
    def fm_num_samples(self):
        """Number of FM cycles in one burst."""
        return self.read("fm_num_samples")

    @fm_num_samples.setter
    def fm_num_samples(self, value):
        check_range("fm_num_samples", value, 0, 1e9)
        self.write("fm_num_samples", int(value))

    @property
    def fm_mod_type(self):
        """Raw FM shape setting, 0 or 1. The PDF contradicts itself on which is
        sinusoid and which is chirp, so check the result on a spectrum analyzer."""
        return self.read("fm_mod_type")

    @fm_mod_type.setter
    def fm_mod_type(self, value):
        if value not in (0, 1):
            raise ValueError("fm_mod_type: expected 0 or 1")
        self.write("fm_mod_type", value)

    @property
    def fm_enable(self):
        """Continuous FM on/off."""
        return self.read("fm_cont")

    @fm_enable.setter
    def fm_enable(self, value):
        check_bool("fm_enable", value)
        self.write("fm_cont", value)


# Only one client may talk to the device at a time.
device_lock = threading.Lock()


def run_command(mini, command, value):
    """Execute one command on the SynthHD Mini and return the result."""
    match command:
        # ---------------- general ----------------
        case "init":
            mini.init()
        case "save":
            mini.save()
        case "settings":
            return mini.settings()
        case "get_model_type":
            return mini.model_type
        case "get_serial_number":
            return mini.serial_number
        case "get_firmware_version":
            return mini.firmware_version
        case "get_hardware_version":
            return mini.hardware_version
        case "get_temperature":
            return mini.temperature
        case "get_communication_mode":
            return mini.communication_mode

        # low-level access to SynthHDMini.API, value = (attribute, arg1, ...)
        case "write":
            mini.write(*value)
        case "read":
            return mini.read(*value)

        # ---------------- RF output ----------------
        case "get_frequency":
            return mini.frequency
        case "set_frequency":
            mini.frequency = value
        case "get_power":
            return mini.power
        case "set_power":
            mini.power = value
        case "get_calibrated":
            return mini.calibrated
        case "get_vga_dac":
            return mini.vga_dac
        case "set_vga_dac":
            mini.vga_dac = value
        case "get_rf_enable":
            return mini.rf_enable
        case "set_rf_enable":
            mini.rf_enable = value
        case "get_pll_enable":
            return mini.pll_enable
        case "set_pll_enable":
            mini.pll_enable = value
        case "get_enable":
            return mini.enable
        case "set_enable":
            mini.enable = value
        case "get_lock_status":
            return mini.lock_status

        # ---------------- PLL / reference ----------------
        case "get_charge_pump_current":
            return mini.charge_pump_current
        case "set_charge_pump_current":
            mini.charge_pump_current = value
        case "get_reference_doubler":
            return mini.reference_doubler
        case "set_reference_doubler":
            mini.reference_doubler = value
        case "get_channel_spacing":
            return mini.channel_spacing
        case "set_channel_spacing":
            mini.channel_spacing = value
        case "get_reference_mode":
            return mini.reference_mode
        case "set_reference_mode":
            mini.reference_mode = value
        case "get_reference_frequency":
            return mini.reference_frequency
        case "set_reference_frequency":
            mini.reference_frequency = value

        # ---------------- sweep ----------------
        case "get_sweep_freq_low":
            return mini.sweep_freq_low
        case "set_sweep_freq_low":
            mini.sweep_freq_low = value
        case "get_sweep_freq_high":
            return mini.sweep_freq_high
        case "set_sweep_freq_high":
            mini.sweep_freq_high = value
        case "get_sweep_freq_step":
            return mini.sweep_freq_step
        case "set_sweep_freq_step":
            mini.sweep_freq_step = value
        case "get_sweep_time_step":
            return mini.sweep_time_step
        case "set_sweep_time_step":
            mini.sweep_time_step = value
        case "get_sweep_power_low":
            return mini.sweep_power_low
        case "set_sweep_power_low":
            mini.sweep_power_low = value
        case "get_sweep_power_high":
            return mini.sweep_power_high
        case "set_sweep_power_high":
            mini.sweep_power_high = value
        case "get_sweep_direction":
            return mini.sweep_direction
        case "set_sweep_direction":
            mini.sweep_direction = value
        case "get_sweep_type":
            return mini.sweep_type
        case "set_sweep_type":
            mini.sweep_type = value
        case "get_sweep_display":
            return mini.sweep_display
        case "set_sweep_display":
            mini.sweep_display = value
        case "get_sweep_run":
            return mini.sweep_run
        case "set_sweep_run":
            mini.sweep_run = value
        case "get_sweep_enable":
            return mini.sweep_enable
        case "set_sweep_enable":
            mini.sweep_enable = value

        # ---------------- list mode ----------------
        case "list_set":  # value = (index, frequency_Hz, power_dBm)
            mini.list_set(*value)
        case "list_read":
            return mini.list_read()

        # ---------------- trigger ----------------
        case "get_trigger_mode":
            return mini.trigger_mode
        case "set_trigger_mode":
            mini.trigger_mode = value
        case "get_trigger_polarity":
            return mini.trigger_polarity
        case "set_trigger_polarity":
            mini.trigger_polarity = value
        case "get_trigger_level":
            return mini.trigger_level

        # ---------------- AM ----------------
        case "get_am_time_step":
            return mini.am_time_step
        case "set_am_time_step":
            mini.am_time_step = value
        case "get_am_num_samples":
            return mini.am_num_samples
        case "set_am_num_samples":
            mini.am_num_samples = value
        case "get_am_enable":
            return mini.am_enable
        case "set_am_enable":
            mini.am_enable = value
        case "am_lookup_table_set":  # value = (index, power_dBm)
            mini.am_lookup_table_set(*value)
        case "am_lookup_table_get":  # value = index
            return mini.am_lookup_table_get(value)

        # ---------------- pulse ----------------
        case "get_pulse_on_time":
            return mini.pulse_on_time
        case "set_pulse_on_time":
            mini.pulse_on_time = value
        case "get_pulse_off_time":
            return mini.pulse_off_time
        case "set_pulse_off_time":
            mini.pulse_off_time = value
        case "get_pulse_num_rep":
            return mini.pulse_num_rep
        case "set_pulse_num_rep":
            mini.pulse_num_rep = value
        case "get_pulse_invert":
            return mini.pulse_invert
        case "set_pulse_invert":
            mini.pulse_invert = value
        case "pulse_single":
            mini.pulse_single()
        case "get_pulse_mod_enable":
            return mini.pulse_mod_enable
        case "set_pulse_mod_enable":
            mini.pulse_mod_enable = value

        # ---------------- FM ----------------
        case "get_fm_frequency":
            return mini.fm_frequency
        case "set_fm_frequency":
            mini.fm_frequency = value
        case "get_fm_deviation":
            return mini.fm_deviation
        case "set_fm_deviation":
            mini.fm_deviation = value
        case "get_fm_num_samples":
            return mini.fm_num_samples
        case "set_fm_num_samples":
            mini.fm_num_samples = value
        case "get_fm_mod_type":
            return mini.fm_mod_type
        case "set_fm_mod_type":
            mini.fm_mod_type = value
        case "get_fm_enable":
            return mini.fm_enable
        case "set_fm_enable":
            mini.fm_enable = value

        case _:
            raise ValueError(f"Unknown command: {command}")

    return None


def handle_client(conn, mini, name):
    """Serve one client until it disconnects. Runs in its own thread."""
    log.info(f"{name} connected")
    try:
        while True:
            command, value = conn.recv()  # raises EOFError when the client disconnects
            log.debug(f"{name}: {command} value={value}")
            try:
                with device_lock:
                    result = run_command(mini, command, value)
                conn.send(("OK", result))
            except Exception as e:
                log.warning(f"{name}: {command} failed: {e!r}")
                conn.send(("ERROR", f"{type(e).__name__}: {e}"))
    except (EOFError, OSError):
        pass
    finally:
        conn.close()
        log.info(f"{name} disconnected")


def main():
    parser = argparse.ArgumentParser(description="Windfreak SynthHD Mini server")
    parser.add_argument("devpath", help="serial port of the SynthHD Mini, e.g. COM6")
    parser.add_argument("--port", type=int, default=0, help="TCP port, 0 = any free port")
    parser.add_argument("--address", default="", help="'' = all interfaces, 'localhost' = this PC only")
    args = parser.parse_args()

    log.basicConfig(
        filename="windfreak_mini_server_log.txt",
        format="%(asctime)s %(levelname)s:%(message)s",
        level=log.INFO,
    )

    mini = SynthHDMini(args.devpath)  # opened once, kept open
    model = mini.model_type
    if "Mini" not in model:
        mini.close()
        raise SystemExit(f"Device at {args.devpath} reports '{model}', not a SynthHD Mini. Not starting.")
    print(f"Opened {model} at {args.devpath}")
    log.info(f"Opened {model} at {args.devpath}")

    listener = Listener((args.address, args.port))
    port = listener.address[1]
    with open(PORT_FILE, "w") as f:
        f.write(f"{port}\n")
    print(f"Windfreak Mini server listening on port {port}")

    try:
        client_number = 0
        while True:
            conn = listener.accept()  # wait for the next client
            client_number += 1
            threading.Thread(
                target=handle_client,
                args=(conn, mini, f"client {client_number}"),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        listener.close()
        mini.close()
        os.remove(PORT_FILE)
        log.info("Server stopped")


if __name__ == "__main__":
    main()
