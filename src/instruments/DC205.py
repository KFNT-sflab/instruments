# -*- coding: utf-8 -*-
"""
Created on Fri Oct 15 11:22:22 2021

@author: ev
"""

from .Instrument import Instrument

class DC205(Instrument):
    def __init__(self, rm , address):
        super().__init__(rm, address)
        self.dev.baud_rate = 115200
        print(self.dev.query('*IDN?'))
    
    def output_range(self, rng=None):
        rngs = {1: 0, 10: 1, 100: 2}
        rngs_r = {0: 1, 1: 10, 2: 100}
        if rng is None:
            resp = self.dev.query('RNGE?')
            return rngs_r[int(resp)]
        self.dev.write('RNGE {}'.format(rngs[rng]))
            
    def output(self, out=None):
        if out is None:
            resp = self.dev.query('SOUT?')
            return bool(resp)
        if out:
            self.dev.write('SOUT 1')
        else:
            self.dev.write('SOUT 0')
    
    def volts(self, V=None):
        if V is None:
            resp = self.dev.query('VOLT?')
            return float(resp)
        self.dev.write('VOLT {:.6f}'.format(V))