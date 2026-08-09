# -*- coding: utf-8 -*-
"""
Created on Thu Sep 17 12:56:38 2020

@author: emil
"""

from .Instrument import Instrument
import re

class DS345(Instrument):
    """Stanford DS345 DC to 30 MHz signal generator."""
    
    def __init__(self, rm, address):
        super().__init__(rm, address)
        print(self.dev.query('*IDN?'))
        self.dev.write("FUNC 0") # set the function to sine
        self.output_amplitude = self.amplitude() 
        self.output_state = (self.output_amplitude > 0)
            
    def output(self, state):
        if state:
            self.amplitude(self.output_amplitude)
            self.output_state = True
        else:
            self.amplitude(0)
            self.output_state = False

    def amplitude(self, value=None, unit='VP'):
        """Available units are VP = peak-to-peak, VR = Vrms, DB = dBm"""
        if value is not None:
            if unit not in ['VP', 'VR', 'DB']:
                raise RuntimeError("Unknown amplitude unit {}".format(unit))
            _val = value
            if value < 0 and not (unit == 'DB'):
                _val=0
            self.dev.write("AMPL {:.4f} {}".format(_val, unit))
            self.output_amplitude=_val
            if value > 0 or unit == 'DB':
                self.output_state = True
        else:
            resp = self.dev.query("AMPL?")
            units_str_match = re.search('[A-Z]+', resp)
            return float(resp[:units_str_match.start()])
    
    def offset(self, value=None):
        """Set or query the offset in volts."""
        if value is not None:
            self.dev.write("OFFS {:.4f}".format(value))
        else:
            resp = self.dev.query("OFFS?")
            return float(resp)
    
    def set_AM_depth(self, value=0):
        self.dev.write('DPTH {:.0f}'.format(value))
    
    def frequency(self, freq=None):
        if freq is not None:
            self.dev.write("FREQ {:.3f}".format(freq))
        else:
            return self.dev.query("FREQ?")