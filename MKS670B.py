# -*- coding: utf-8 -*-
"""
Created on Thu Oct  6 12:29:54 2022

@author: Filip Novotny
"""
from time import time
from .Instrument import Instrument

class MKS670B(Instrument):
    def __init__ (self, rm, address, **kwargs):
        super().__init__(rm, address, **kwargs)
        self.configure({'read_termination': '\r',
                        'write_termination': '\r',
                        'data_bits': 8})
        
    def readP (self, timeout=2):
        t0 = time()
        while time() - t0<timeout:
            try:
                resp = self.dev.query('@020?')
                self.Pressure = float(resp.split(' ')[1])
                break
            except:
                pass
             
        return self.Pressure