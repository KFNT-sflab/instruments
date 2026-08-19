# Instruments (`sflab-instruments`)

`sflab-instruments` is a Python library providing clean interfaces and drivers for laboratory measurement instruments, including VISA devices, lock-in amplifiers, VNAs, power supplies, signal generators, and temperature controllers.

## Installation

### Installation from Source
```bash
git clone https://github.com/KFNT-sflab/instruments
cd instruments
pip install .
```

### Using the instrument server
The project includes a simple instrument server that allows multiple programs to communicate with a single instruments concurrently, and also supports communication over the network. During installation, a script `sflab_instrument_server` is installed in the current environment, which can be used to start the server. Ths easiest way to use it is with `uv`, i.e. `uv run sflab_instrument_server`.

All instrument classes inhereited from `Instrument` base class (that is, most of them) can then connect to this server by specifiying `access_mode="socket"` and then communicate as normal. An example for the `SR830` lock-in amplifier:
```python
from sflab_instruments.SR830 import SR830

# if the instrument server is running on localhost
lockin = SR830(None, 'GPIB0::1::INSTR', access_mode="socket")
# or if the instrument server is running on a remote
lockin = SR830(None, 'GPIB0::1::INSTR', access_mode="socket", remote_addr="<remote IP address>", port=<port number>)

x, y = lockin.get_xy()
# or for general queries
resp = lockin.dev.query("*IDN?")
```

When the server is started it prints the port number on the output and also saves it in `instrument_server_port.txt` stored in the location returned by `tempfile.gettempdir()`, which is searched if `port` is not specified

There is no password, or any security to speak of. So do not use this on open networks.

## License

[MIT License](LICENSE)
