# Instruments (`sflab-instruments`)

`sflab-instruments` is a Python library providing clean interfaces and drivers for laboratory measurement instruments, including VISA devices, lock-in amplifiers, VNAs, power supplies, signal generators, and temperature controllers.

## Installation

### standard installation
```bash
pip install sflab-instruments
```

### Installation from Source
```bash
git clone https://github.com/emil-varga/instruments.git
cd instruments
pip install .
```

### Optional Hardware Extras
For NI-DAQmx or Zurich Instruments support:
```bash
pip install sflab-instruments[daq]      # NI-DAQmx support
pip install sflab-instruments[zhinst]   # Zurich Instruments support
pip install sflab-instruments[all]      # All optional hardware packages
```

## Quick Start

```python
from instruments import SR830, Keithley2200

# Connect to Stanford Research SR830 Lock-in Amplifier
lockin = SR830("GPIB0::24::INSTR")
print("Frequency:", lockin.frequency)

# Connect to Keithley Power Supply
psu = Keithley2200("USB0::0x05E6::0x2200::...::INSTR")
psu.voltage = 5.0
psu.output_enabled = True
```

## Supported Devices

- **Lock-in Amplifiers**: SR830, SR844, ziLockin (Zurich Instruments), DAQ_Lockin
- **Signal Generators & Function Generators**: DS345, KS33210A, Rigol_DG, SG384
- **Power Supplies & Voltage Sources**: DC205, Keithley2200, KeithleyMultichannel
- **Vector Network Analyzers**: LiteVNA, vna
- **Multimeters & Sensors**: Keysight DMM, LakeShore, LakeShore336, MKS670B, Mensor, PR4000B, Pico, VATvalve

## Building and Uploading to PyPI

To build and publish to PyPI:

1. Install build tools:
   ```bash
   pip install build twine
   ```

2. Build source distribution and wheel:
   ```bash
   python -m build
   ```

3. Upload to PyPI:
   ```bash
   python -m twine upload dist/*
   ```

## License

[MIT License](LICENSE)
