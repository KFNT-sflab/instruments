# -*- coding: utf-8 -*-
"""
Created on Thu Oct  6 12:29:54 2022

@author: Filip Novotny
"""
from time import time
from .Instrument import Instrument

class MKS670B(Instrument):
    def __init__(self, rm, address, **kwargs):
        super().__init__(rm, address, **kwargs)
        self.configure({'read_termination': '\r',
                        'write_termination': '\r',
                        'data_bits': 8})
        
    def readP(self, timeout=2):
        t0 = time()
        while time() - t0<timeout:
            try:
                resp = self.dev.query('@020?')
                self.Pressure = float(resp.split(' ')[1])
                break
            except:
                pass
             
        return self.Pressure
    
    @property
    def gain(self):
        _cmd = "@170?"
        resp = self.dev.query(_cmd)
        gains = {"0": "x1", "1": "x0.1", "2": "x0.01", "3": "auto"}
        return gains[resp[4]]

    @gain.setter
    def gain(self, gain_setting="auto"):
        _cmd = "@170"
        match gain_setting:
            case "x1": _cmd += "0"
            case "x0.1": _cmd += "1"
            case "x0.01": _cmd += "2"
            case "auto": _cmd += "3"
            case _:
                raise ValueError("Unknown gain setting. Available are 'x1', 'x0.1', 'x0.01' and 'auto'")
        resp = self.dev.query(_cmd)
        if resp[0] != "@":
            raise RuntimeError(f"Failed to change gain: \"{resp}\". Check that they key is switched to \"REMOTE\".")

