#!/usr/bin/env python3
"""
Client for WindfreakServer.py.

Used exactly like windfreak.SynthHD, only the constructor changes:

    synth = WindfreakClient()        # instead of SynthHD("COM5")
    synth[0].frequency = 5e9         # sends ("set_frequency", 0, 5e9) to the server
    print(synth[0].power)            # sends ("get_power", 0, None)
    synth.close()                    # disconnects; the device stays open on the server
"""

import os
import tempfile
from multiprocessing.connection import Client

PORT_FILE = os.path.join(tempfile.gettempdir(), "windfreak_server_port.txt")


class WindfreakClient:
    def __init__(self, address="localhost", port=None):
        if port is None:
            with open(PORT_FILE) as f:
                port = int(f.readline())
        self.conn = Client((address, port))
        self.channels = [WindfreakChannel(self, 0), WindfreakChannel(self, 1)]

    def send(self, command, channel=None, value=None):
        """Send one command to the server and return its result."""
        self.conn.send((command, channel, value))
        status, result = self.conn.recv()
        if status == "ERROR":
            raise RuntimeError(f"Windfreak server: {result}")
        return result

    def close(self):
        """Disconnect from the server (the SynthHD stays open on the server)."""
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # synth[0], synth[1], len(synth), for ch in synth
    def __getitem__(self, index):
        return self.channels[index]

    def __len__(self):
        return len(self.channels)

    # ---------------- device methods ----------------
    def init(self):
        """Put device into a safe state (internal reference, no modulation, outputs off)."""
        self.send("init")

    def save(self):
        """Save all settings to EEPROM."""
        self.send("save")

    def write(self, attribute, *args):
        """Low-level write, e.g. synth.write('sweep_freq_low', 1000.0)."""
        self.send("write", value=(attribute, *args))

    def read(self, attribute, *args):
        """Low-level read, e.g. synth.read('sweep_freq_low')."""
        return self.send("read", value=(attribute, *args))

    # ---------------- device properties (read only) ----------------
    @property
    def model(self):
        return self.send("get_model")

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
    def reference_modes(self):
        return self.send("get_reference_modes")

    @property
    def trigger_modes(self):
        return self.send("get_trigger_modes")

    @property
    def reference_frequency_range(self):
        return self.send("get_reference_frequency_range")

    # ---------------- device properties (read / write) ----------------
    @property
    def reference_mode(self):
        """'external', 'internal 27mhz' or 'internal 10mhz'."""
        return self.send("get_reference_mode")

    @reference_mode.setter
    def reference_mode(self, value):
        self.send("set_reference_mode", value=value)

    @property
    def reference_frequency(self):
        """Reference frequency in Hz."""
        return self.send("get_reference_frequency")

    @reference_frequency.setter
    def reference_frequency(self, value):
        self.send("set_reference_frequency", value=value)

    @property
    def trigger_mode(self):
        return self.send("get_trigger_mode")

    @trigger_mode.setter
    def trigger_mode(self, value):
        self.send("set_trigger_mode", value=value)

    @property
    def sweep_enable(self):
        return self.send("get_sweep_enable")

    @sweep_enable.setter
    def sweep_enable(self, value):
        self.send("set_sweep_enable", value=value)

    @property
    def am_enable(self):
        return self.send("get_am_enable")

    @am_enable.setter
    def am_enable(self, value):
        self.send("set_am_enable", value=value)

    @property
    def pulse_mod_enable(self):
        return self.send("get_pulse_mod_enable")

    @pulse_mod_enable.setter
    def pulse_mod_enable(self, value):
        self.send("set_pulse_mod_enable", value=value)

    @property
    def dual_pulse_mod_enable(self):
        return self.send("get_dual_pulse_mod_enable")

    @dual_pulse_mod_enable.setter
    def dual_pulse_mod_enable(self, value):
        self.send("set_dual_pulse_mod_enable", value=value)

    @property
    def fm_enable(self):
        return self.send("get_fm_enable")

    @fm_enable.setter
    def fm_enable(self, value):
        self.send("set_fm_enable", value=value)


class WindfreakChannel:
    """One output channel, used like synth[0] of windfreak.SynthHD."""

    def __init__(self, client, index):
        self.client = client
        self.index = index

    def send(self, command, value=None):
        return self.client.send(command, self.index, value)

    def init(self):
        """Output off, lowest frequency and power, phase 0."""
        self.send("channel_init")

    # ---------------- read only ----------------
    @property
    def frequency_range(self):
        return self.send("get_frequency_range")

    @property
    def power_range(self):
        return self.send("get_power_range")

    @property
    def vga_dac_range(self):
        return self.send("get_vga_dac_range")

    @property
    def phase_range(self):
        return self.send("get_phase_range")

    @property
    def temp_compensation_modes(self):
        return self.send("get_temp_compensation_modes")

    @property
    def channel_spacing_range(self):
        return self.send("get_channel_spacing_range")

    @property
    def calibrated(self):
        return self.send("get_calibrated")

    @property
    def lock_status(self):
        """True if the PLL is locked."""
        return self.send("get_lock_status")

    # ---------------- read / write ----------------
    @property
    def frequency(self):
        """Frequency in Hz."""
        return self.send("get_frequency")

    @frequency.setter
    def frequency(self, value):
        self.send("set_frequency", value)

    @property
    def power(self):
        """Power in dBm."""
        return self.send("get_power")

    @power.setter
    def power(self, value):
        self.send("set_power", value)

    @property
    def phase(self):
        """Phase in degrees."""
        return self.send("get_phase")

    @phase.setter
    def phase(self, value):
        self.send("set_phase", value)

    @property
    def vga_dac(self):
        return self.send("get_vga_dac")

    @vga_dac.setter
    def vga_dac(self, value):
        self.send("set_vga_dac", value)

    @property
    def temp_compensation_mode(self):
        """'none', 'on set', '1 sec' or '10 sec'."""
        return self.send("get_temp_compensation_mode")

    @temp_compensation_mode.setter
    def temp_compensation_mode(self, value):
        self.send("set_temp_compensation_mode", value)

    @property
    def rf_enable(self):
        return self.send("get_rf_enable")

    @rf_enable.setter
    def rf_enable(self, value):
        self.send("set_rf_enable", value)

    @property
    def pa_enable(self):
        return self.send("get_pa_enable")

    @pa_enable.setter
    def pa_enable(self, value):
        self.send("set_pa_enable", value)

    @property
    def pll_enable(self):
        return self.send("get_pll_enable")

    @pll_enable.setter
    def pll_enable(self, value):
        self.send("set_pll_enable", value)

    @property
    def enable(self):
        """Output on/off (RF, PLL and PA together)."""
        return self.send("get_enable")

    @enable.setter
    def enable(self, value):
        self.send("set_enable", value)

    @property
    def channel_spacing(self):
        """Channel spacing in Hz (SynthHD v2 only)."""
        return self.send("get_channel_spacing")

    @channel_spacing.setter
    def channel_spacing(self, value):
        self.send("set_channel_spacing", value)


if __name__ == "__main__":
    # quick check: python WindfreakClient.py (with the server running)
    with WindfreakClient() as synth:
        print("model:", synth.model)
        print("temperature:", synth.temperature, "C")
        for ch in synth:
            print(f"channel {ch.index}: {ch.frequency} Hz, {ch.power} dBm, enabled={ch.enable}")
