#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Mar 23 11:14:53 2023

@author: filip
"""

import pyvisa as visa 
import numpy as np
from time import sleep

from .Instrument import Instrument

class Keithley2200(Instrument):
    
    def __init__ (self,rm,address, **kwargs):
        super().__init__(rm, address, **kwargs)
        
    def output(self, oper=False):
        if oper:
            command = 'OUTP {}'.format('ON')
        else:
            command = 'OUTP {}'.format('OFF')
        self.dev.write(command)
        print('Output is:',' ',self.dev.query('OUTPUT?'))
        
    def setvoltage(self, volt):
        command = 'VOLT {}V'.format(volt)
        self.dev.write(command)

    def getvoltage(self):
        command = 'MEAS:VOLT?'
        set_volt = self.dev.query(command)
        return float(set_volt)
    
    def setcurrent(self,curr):
        command = 'CURR {}A'.format(curr)
        self.dev.write(command)
        
    def getcurrent(self):
        command = 'MEAS:CURR?'
        set_curr = self.dev.query(command)
        return float(set_curr)
        