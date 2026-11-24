#!/usr/bin/env python3
"""
Windfreak SynthHD server.

Opens the SynthHD once at startup and keeps it open while the server runs.
Clients (WindfreakClient.py) connect over a socket and send a message

    (command, channel, value)

e.g. ("set_frequency", 0, 5e9). The server runs the matching SynthHD call,
e.g. synth[0].frequency = 5e9, and sends back

    ("OK", result)        or        ("ERROR", "error message")

Usage:
    python WindfreakServer.py COM5
"""

import argparse
import logging as log
import os
import tempfile
import threading
from multiprocessing.connection import Listener

from windfreak import SynthHD

PORT_FILE = os.path.join(tempfile.gettempdir(), "windfreak_server_port.txt")

# Only one client may talk to the device at a time.
device_lock = threading.Lock()


def run_command(synth, command, channel, value):
    """Execute one command on the SynthHD and return the result."""
    ch = synth[channel] if channel is not None else None

    match command:
        # ---------------- device commands ----------------
        case "init":
            synth.init()
        case "save":
            synth.save()
        case "get_model":
            return synth.model
        case "get_model_type":
            return synth.model_type
        case "get_serial_number":
            return synth.serial_number
        case "get_firmware_version":
            return synth.firmware_version
        case "get_hardware_version":
            return synth.hardware_version
        case "get_temperature":
            return synth.temperature

        case "get_reference_modes":
            return synth.reference_modes
        case "get_reference_mode":
            return synth.reference_mode
        case "set_reference_mode":
            synth.reference_mode = value

        case "get_reference_frequency_range":
            return synth.reference_frequency_range
        case "get_reference_frequency":
            return synth.reference_frequency
        case "set_reference_frequency":
            synth.reference_frequency = value

        case "get_trigger_modes":
            return synth.trigger_modes
        case "get_trigger_mode":
            return synth.trigger_mode
        case "set_trigger_mode":
            synth.trigger_mode = value

        case "get_sweep_enable":
            return synth.sweep_enable
        case "set_sweep_enable":
            synth.sweep_enable = value
        case "get_am_enable":
            return synth.am_enable
        case "set_am_enable":
            synth.am_enable = value
        case "get_pulse_mod_enable":
            return synth.pulse_mod_enable
        case "set_pulse_mod_enable":
            synth.pulse_mod_enable = value
        case "get_dual_pulse_mod_enable":
            return synth.dual_pulse_mod_enable
        case "set_dual_pulse_mod_enable":
            synth.dual_pulse_mod_enable = value
        case "get_fm_enable":
            return synth.fm_enable
        case "set_fm_enable":
            synth.fm_enable = value

        # low-level access to SynthHD.API, value = (attribute, arg1, arg2, ...)
        case "write":
            synth.write(*value)
        case "read":
            return synth.read(*value)

        # ---------------- channel commands ----------------
        case "channel_init":
            ch.init()

        case "get_frequency_range":
            return ch.frequency_range
        case "get_frequency":
            return ch.frequency
        case "set_frequency":
            ch.frequency = value

        case "get_power_range":
            return ch.power_range
        case "get_power":
            return ch.power
        case "set_power":
            ch.power = value

        case "get_calibrated":
            return ch.calibrated

        case "get_temp_compensation_modes":
            return ch.temp_compensation_modes
        case "get_temp_compensation_mode":
            return ch.temp_compensation_mode
        case "set_temp_compensation_mode":
            ch.temp_compensation_mode = value

        case "get_vga_dac_range":
            return ch.vga_dac_range
        case "get_vga_dac":
            return ch.vga_dac
        case "set_vga_dac":
            ch.vga_dac = value

        case "get_phase_range":
            return ch.phase_range
        case "get_phase":
            return ch.phase
        case "set_phase":
            ch.phase = value

        case "get_rf_enable":
            return ch.rf_enable
        case "set_rf_enable":
            ch.rf_enable = value
        case "get_pa_enable":
            return ch.pa_enable
        case "set_pa_enable":
            ch.pa_enable = value
        case "get_pll_enable":
            return ch.pll_enable
        case "set_pll_enable":
            ch.pll_enable = value
        case "get_enable":
            return ch.enable
        case "set_enable":
            ch.enable = value

        case "get_lock_status":
            return ch.lock_status

        # SynthHD v2 only
        case "get_channel_spacing_range":
            return ch.channel_spacing_range
        case "get_channel_spacing":
            return ch.channel_spacing
        case "set_channel_spacing":
            ch.channel_spacing = value

        case _:
            raise ValueError(f"Unknown command: {command}")

    return None


def handle_client(conn, synth, name):
    """Serve one client until it disconnects. Runs in its own thread."""
    log.info(f"{name} connected")
    try:
        while True:
            command, channel, value = (
                conn.recv()
            )  # raises EOFError when the client disconnects
            log.debug(f"{name}: {command} ch={channel} value={value}")
            try:
                with device_lock:
                    result = run_command(synth, command, channel, value)
                conn.send(("OK", result))
            except Exception as e:
                log.warning(f"{name}: {command} failed: {e!r}")
                conn.send(("ERROR", f"{type(e).__name__}: {e}"))
    except EOFError, OSError:
        pass
    finally:
        conn.close()
        log.info(f"{name} disconnected")


def main():
    parser = argparse.ArgumentParser(description="Windfreak SynthHD server")
    parser.add_argument(
        "devpath", default=None, help="serial port of the SynthHD, e.g. COM5"
    )
    parser.add_argument(
        "--port", type=int, default=0, help="TCP port, 0 = any free port"
    )
    parser.add_argument(
        "--address", default="", help="'' = all interfaces, 'localhost' = this PC only"
    )
    args = parser.parse_args()

    log.basicConfig(
        filename="windfreak_server_log.txt",
        format="%(asctime)s %(levelname)s:%(message)s",
        level=log.INFO,
    )

    synth = SynthHD(args.devpath)  # opened once, kept open
    print(f"Opened {synth.model} at {args.devpath}")
    log.info(f"Opened {synth.model} at {args.devpath}")

    listener = Listener((args.address, args.port))
    port = listener.address[1]
    with open(PORT_FILE, "w") as f:
        f.write(f"{port}\n")
    print(f"Windfreak server listening on port {port}")

    try:
        client_number = 0
        while True:
            conn = listener.accept()  # wait for the next client
            client_number += 1
            threading.Thread(
                target=handle_client,
                args=(conn, synth, f"client {client_number}"),
                daemon=True,
            ).start()
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        listener.close()
        synth.close()
        os.remove(PORT_FILE)
        log.info("Server stopped")


if __name__ == "__main__":
    main()
