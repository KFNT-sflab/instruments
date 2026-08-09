# -*- coding: utf-8 -*-
"""
Created on Thu Feb 20 13:09:34 2025

@author: sflab
"""

from .Instrument import Instrument
import pyvisa as vi

class PR4000B(Instrument):
    def __init__(self, rm, address, channel=1, **kwargs):
        super().__init__(rm, address, **kwargs)
        self.configure({'read_termination': '\r',
                        'write_termination': '\r',
                        'baud_rate': 9600,
                        'data_bits': 7,
                        'parity': vi.constants.Parity.odd,
                        'stop_bits': vi.constants.StopBits.one})
        self.dev.query('RE')
        self.dev.query('RT,ON')
        self.dev.query('RS,ON')
        self.dev.query('SM1,0')
        self.other = None
        self.channel = channel
        
    def set_relative(self, other, unit = 'Pa'):
        self.other = other
        self.other_unit = unit
        
    def readP(self, ch=None):
        if ch is None:
            resp = self.dev.query(f'AV{self.channel}')
        elif ch in [1,2]:
            resp = self.dev.query(f'AV{ch}')
        else:
            raise KeyError('Allowed values of int:"ch" are 1 or 2')
        self.Pressure = float(resp)
        
        if self.other:
            if self.other_unit == 'Pa':
                other_pressure = self.other.readP()*0.00750062
            else:
                other_pressure = self.other.readP()
            self.Pressure = other_pressure - self.Pressure
        
        return self.Pressure
    
    def close(self):
        self.dev.query('RT,OFF')
        if self.other:
            self.other.close()
        super().close()