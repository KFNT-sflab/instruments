# -*- coding: utf-8 -*-
"""
Created on Wed Apr  5 11:16:17 2023

@author: sflab
"""
from .Instrument import Instrument
import pyvisa as visa
import time

class VATvalve(Instrument):
    def __init__(self, rm, address, **kwargs):
        super().__init__(rm, address, **kwargs)
        self.dev.clear()
        self.dev.baud_rate = 9600
        self.dev.data_bits = 7
        self.dev.stop_bits = visa.constants.StopBits.one
        self.dev.parity = visa.constants.Parity.even
        self.dev.read_termination='\r\n'
        self.dev.write_termination='\r\n'
    
    def get(self):
        resp = self.dev.query('A:', delay=0.1)
        return(float(resp[2:])/1000)

    def set_pos(self, pos):
        self.dev.query('R:{:06d}'.format(pos*1000))
        
    def close_valve(self):
        self.dev.query('C:')