# -*- coding: utf-8 -*-
"""
Created on Thu Sep 17 16:15:46 2020

@author: emil
"""

from .Instrument import Instrument

class SG384(Instrument):
    """Stanford SG384 signal generator (up-to 4 GHz)"""
    
    def __init__(self, rm, address):
        super().__init__(rm, address)
        
    def output(self, outp=None):
        if outp is None:
            return bool(int(self.dev.query('ENBR?')))
        self.dev.write('ENBR {}'.format(1 if outp else 0))

    def frequency(self, freq=None):
        if freq is None:
            return float(self.dev.query('FREQ?'))
        self.dev.write('FREQ {:.3f}'.format(freq))
    
    def phase(self, phase=None):
        if phase is None:
            return float(self.dev.query('PHAS?'))
        self.dev.write('PHAS {:.0f}'.format(phase))
    
    def power(self, ampl=None):
        if ampl is None:
            return float(self.dev.query('AMPR?'))
        self.dev.write('AMPH {:.2f}'.format(ampl))
    
    def BNCamp(self, ampl=None, unit='VPP'):
        """Set the amplitude in peak-to-peak voltage."""
        if ampl is None:
            return float(self.dev.query('AMPL? VPP'))
        if ampl >= 0.001:
            self.dev.write('AMPL {:.3f} {}'.format(ampl, unit))
            self.enableLF(True)
        else:
            self.enableLF(False)
    
    def enableLF(self, status=None):
        if status is None:
            return self.dev.query('ENBL?')
        self.dev.write('ENBL {}'.format(1 if status else 0))
    
    def enableRF(self, status=None):
        if status is None:
            return self.dev.query('ENBR?')
        self.dev.write('ENBR {}'.format(1 if status else 0))
    
    def enableHF(self, status=None):
        if status is None:
            return self.dev.query('ENBH?')
        self.dev.write('ENBH {}'.format(1 if status else 0))
        
    def extAM(self, enable=True, depth=100):
        if enable:
            self.dev.write('TYPE 0') # select AM modulation
            self.dev.write('COUP 1') # DC coupling for the AM input
            self.dev.write('MFNC 5') # external source for AM
            self.dev.write('ADEP {:.1f}'.format(depth)) #modulation depth in %
            self.dev.write('MODL 1') #enable modulation
        else:
            self.dev.write('MODL 0') #disable modulation
    
    def extFM(self, enable=True, deviation=50):
        if enable:
            self.dev.write('TYPE 1') # select FM modulation
            self.dev.write('COUP 1') # DC coupling for the FM input
            self.dev.write('MFNC 5') # external source for FM
            self.dev.write('FDEV {:.1f}'.format(deviation)) #frequency deviation in Hz
            self.dev.write('MODL 1') #enable modulation
        else:
            self.dev.write('MODL 0') #disable modulation