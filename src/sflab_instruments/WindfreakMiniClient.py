#!/usr/bin/env python3
"""
Client for WindfreakMiniServer.py (Windfreak SynthHD Mini, one channel).

    mini = WindfreakMiniClient()
    mini.frequency = 5e9             # sends ("set_frequency", 5e9) to the server
    mini.power = -10
    mini.enable = True
    print(mini.lock_status)          # sends ("get_lock_status", None)
    mini.close()                     # disconnects; the device stays open on the server

For code written for the 2-channel SynthHD, mini[0] returns the client itself,
so mini[0].frequency = 5e9 also works.

Units: frequencies in Hz, power in dBm, times as noted per property.
"""

import os
import tempfile
from multiprocessing.connection import Client

PORT_FILE = os.path.join(tempfile.gettempdir(), "windfreak_mini_server_port.txt")


class WindfreakMiniClient:
    def __init__(self, address="localhost", port=None):
        if port is None:
            with open(PORT_FILE) as f:
                port = int(f.readline())
        self.conn = Client((address, port))

    def send(self, command, value=None):
        """Send one command to the server and return its result."""
        self.conn.send((command, value))
        status, result = self.conn.recv()
        if status == "ERROR":
            raise RuntimeError(f"Windfreak Mini server: {result}")
        return result

    def close(self):
        """Disconnect from the server (the Mini stays open on the server)."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __getitem__(self, index):
        """mini[0] is the (only) channel, for compatibility with SynthHD code."""
        if index != 0:
            raise IndexError("The SynthHD Mini has only channel 0")
        return self

    def __len__(self):
        return 1

    # ---------------- general ----------------
    def init(self):
        """Safe state: sweep, modulations and triggers off, internal reference, output off."""
        self.send("init")

    def save(self):
        """Save all current settings to EEPROM (power-up defaults)."""
        self.send("save")

    def settings(self):
        """All device settings as a list of strings (device command '?1')."""
        return self.send("settings")

    def write(self, attribute, *args):
        """Low-level write of a SynthHDMini.API entry, e.g. mini.write('frequency', 1000.0)  # MHz"""
        self.send("write", (attribute, *args))

    def read(self, attribute, *args):
        """Low-level read of a SynthHDMini.API entry, e.g. mini.read('frequency')  # MHz"""
        return self.send("read", (attribute, *args))

    @property
    def model_type(self):
        return self.send("get_model_type")

    @property
    def serial_number(self):
        return self.send("get_serial_number")

    @property
    def firmware_version(self):
        return self.send("get_firmware_version")

    @property
    def hardware_version(self):
        return self.send("get_hardware_version")

    @property
    def temperature(self):
        """Temperature in Celsius."""
        return self.send("get_temperature")

    @property
    def communication_mode(self):
        """'USB' or 'UART'."""
        return self.send("get_communication_mode")

    # ---------------- RF output ----------------
    @property
    def frequency(self):
        """Frequency in Hz (10 MHz - 15 GHz)."""
        return self.send("get_frequency")

    @frequency.setter
    def frequency(self, value):
        self.send("set_frequency", value)

    @property
    def power(self):
        """Power in dBm (-20 to +20)."""
        return self.send("get_power")

    @power.setter
    def power(self, value):
        self.send("set_power", value)

    @property
    def calibrated(self):
        return self.send("get_calibrated")

    @property
    def vga_dac(self):
        """Raw VGA DAC value, 0 - 4000."""
        return self.send("get_vga_dac")

    @vga_dac.setter
    def vga_dac(self, value):
        self.send("set_vga_dac", value)

    @property
    def rf_enable(self):
        """RF not muted (True) / muted (False)."""
        return self.send("get_rf_enable")

    @rf_enable.setter
    def rf_enable(self, value):
        self.send("set_rf_enable", value)

    @property
    def pll_enable(self):
        return self.send("get_pll_enable")

    @pll_enable.setter
    def pll_enable(self, value):
        self.send("set_pll_enable", value)

    @property
    def enable(self):
        """Output on/off (PLL and RF mute together)."""
        return self.send("get_enable")

    @enable.setter
    def enable(self, value):
        self.send("set_enable", value)

    @property
    def lock_status(self):
        """True if the PLL is locked."""
        return self.send("get_lock_status")

    # ---------------- PLL / reference ----------------
    @property
    def charge_pump_current(self):
        """1 - 15."""
        return self.send("get_charge_pump_current")

    @charge_pump_current.setter
    def charge_pump_current(self, value):
        self.send("set_charge_pump_current", value)

    @property
    def reference_doubler(self):
        return self.send("get_reference_doubler")

    @reference_doubler.setter
    def reference_doubler(self, value):
        self.send("set_reference_doubler", value)

    @property
    def channel_spacing(self):
        """Frequency resolution in Hz."""
        return self.send("get_channel_spacing")

    @channel_spacing.setter
    def channel_spacing(self, value):
        self.send("set_channel_spacing", value)

    @property
    def reference_mode(self):
        """'external' or 'internal 27mhz'."""
        return self.send("get_reference_mode")

    @reference_mode.setter
    def reference_mode(self, value):
        self.send("set_reference_mode", value)

    @property
    def reference_frequency(self):
        """External reference frequency in Hz (10 - 100 MHz)."""
        return self.send("get_reference_frequency")

    @reference_frequency.setter
    def reference_frequency(self, value):
        self.send("set_reference_frequency", value)

    # ---------------- sweep ----------------
    @property
    def sweep_freq_low(self):
        """Hz."""
        return self.send("get_sweep_freq_low")

    @sweep_freq_low.setter
    def sweep_freq_low(self, value):
        self.send("set_sweep_freq_low", value)

    @property
    def sweep_freq_high(self):
        """Hz."""
        return self.send("get_sweep_freq_high")

    @sweep_freq_high.setter
    def sweep_freq_high(self, value):
        self.send("set_sweep_freq_high", value)

    @property
    def sweep_freq_step(self):
        """Hz."""
        return self.send("get_sweep_freq_step")

    @sweep_freq_step.setter
    def sweep_freq_step(self, value):
        self.send("set_sweep_freq_step", value)

    @property
    def sweep_time_step(self):
        """ms per step (0.25 - 60000)."""
        return self.send("get_sweep_time_step")

    @sweep_time_step.setter
    def sweep_time_step(self, value):
        self.send("set_sweep_time_step", value)

    @property
    def sweep_power_low(self):
        """dBm."""
        return self.send("get_sweep_power_low")

    @sweep_power_low.setter
    def sweep_power_low(self, value):
        self.send("set_sweep_power_low", value)

    @property
    def sweep_power_high(self):
        """dBm."""
        return self.send("get_sweep_power_high")

    @sweep_power_high.setter
    def sweep_power_high(self, value):
        self.send("set_sweep_power_high", value)

    @property
    def sweep_direction(self):
        """'up' or 'down'."""
        return self.send("get_sweep_direction")

    @sweep_direction.setter
    def sweep_direction(self, value):
        self.send("set_sweep_direction", value)

    @property
    def sweep_type(self):
        """'linear' or 'tabular'."""
        return self.send("get_sweep_type")

    @sweep_type.setter
    def sweep_type(self, value):
        self.send("set_sweep_type", value)

    @property
    def sweep_display(self):
        """0 = off, 1 = frequency, 2 = frequency and power."""
        return self.send("get_sweep_display")

    @sweep_display.setter
    def sweep_display(self, value):
        self.send("set_sweep_display", value)

    @property
    def sweep_run(self):
        """True = start/continue, False = pause."""
        return self.send("get_sweep_run")

    @sweep_run.setter
    def sweep_run(self, value):
        self.send("set_sweep_run", value)

    @property
    def sweep_enable(self):
        """Sweep continuously."""
        return self.send("get_sweep_enable")

    @sweep_enable.setter
    def sweep_enable(self, value):
        self.send("set_sweep_enable", value)

    # ---------------- list mode ----------------
    def list_set(self, index, frequency, power):
        """Store list point index: frequency in Hz, power in dBm."""
        self.send("list_set", (index, frequency, power))

    def list_read(self):
        return self.send("list_read")

    # ---------------- trigger ----------------
    @property
    def trigger_mode(self):
        return self.send("get_trigger_mode")

    @trigger_mode.setter
    def trigger_mode(self, value):
        self.send("set_trigger_mode", value)

    @property
    def trigger_polarity(self):
        """'active low' or 'active high'."""
        return self.send("get_trigger_polarity")

    @trigger_polarity.setter
    def trigger_polarity(self, value):
        self.send("set_trigger_polarity", value)

    @property
    def trigger_level(self):
        return self.send("get_trigger_level")

    # ---------------- AM ----------------
    @property
    def am_time_step(self):
        """us."""
        return self.send("get_am_time_step")

    @am_time_step.setter
    def am_time_step(self, value):
        self.send("set_am_time_step", value)

    @property
    def am_num_samples(self):
        return self.send("get_am_num_samples")

    @am_num_samples.setter
    def am_num_samples(self, value):
        self.send("set_am_num_samples", value)

    @property
    def am_enable(self):
        return self.send("get_am_enable")

    @am_enable.setter
    def am_enable(self, value):
        self.send("set_am_enable", value)

    def am_lookup_table_set(self, index, power):
        """Row 0 - 199, power in dBm."""
        self.send("am_lookup_table_set", (index, power))

    def am_lookup_table_get(self, index):
        return self.send("am_lookup_table_get", index)

    # ---------------- pulse ----------------
    @property
    def pulse_on_time(self):
        """us."""
        return self.send("get_pulse_on_time")

    @pulse_on_time.setter
    def pulse_on_time(self, value):
        self.send("set_pulse_on_time", value)

    @property
    def pulse_off_time(self):
        """us."""
        return self.send("get_pulse_off_time")

    @pulse_off_time.setter
    def pulse_off_time(self, value):
        self.send("set_pulse_off_time", value)

    @property
    def pulse_num_rep(self):
        return self.send("get_pulse_num_rep")

    @pulse_num_rep.setter
    def pulse_num_rep(self, value):
        self.send("set_pulse_num_rep", value)

    @property
    def pulse_invert(self):
        return self.send("get_pulse_invert")

    @pulse_invert.setter
    def pulse_invert(self, value):
        self.send("set_pulse_invert", value)

    def pulse_single(self):
        """Run one pulse burst."""
        self.send("pulse_single")

    @property
    def pulse_mod_enable(self):
        return self.send("get_pulse_mod_enable")

    @pulse_mod_enable.setter
    def pulse_mod_enable(self, value):
        self.send("set_pulse_mod_enable", value)

    # ---------------- FM ----------------
    @property
    def fm_frequency(self):
        """Hz (1 - 5000)."""
        return self.send("get_fm_frequency")

    @fm_frequency.setter
    def fm_frequency(self, value):
        self.send("set_fm_frequency", value)

    @property
    def fm_deviation(self):
        """+/- Hz."""
        return self.send("get_fm_deviation")

    @fm_deviation.setter
    def fm_deviation(self, value):
        self.send("set_fm_deviation", value)

    @property
    def fm_num_samples(self):
        return self.send("get_fm_num_samples")

    @fm_num_samples.setter
    def fm_num_samples(self, value):
        self.send("set_fm_num_samples", value)

    @property
    def fm_mod_type(self):
        """Raw 0 or 1 (sinusoid/chirp, see SynthHDMini.fm_mod_type)."""
        return self.send("get_fm_mod_type")

    @fm_mod_type.setter
    def fm_mod_type(self, value):
        self.send("set_fm_mod_type", value)

    @property
    def fm_enable(self):
        return self.send("get_fm_enable")

    @fm_enable.setter
    def fm_enable(self, value):
        self.send("set_fm_enable", value)


if __name__ == "__main__":
    # quick read-only check: python WindfreakMiniClient.py (with the server running)
    with WindfreakMiniClient() as mini:
        print("model:", mini.model_type)
        print("temperature:", mini.temperature, "C")
        print(f"{mini.frequency} Hz, {mini.power} dBm, enabled={mini.enable}, locked={mini.lock_status}")
