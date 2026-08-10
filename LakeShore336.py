#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Wed Mar 22 14:49:05 2023

@author: filip
"""

import numpy as np
import scipy.interpolate as intp
import pyvisa as visa
from pyvisa.constants import Parity
from time import sleep
from .Instrument import Instrument

class LakeShore336(Instrument):
    def __init__ (self, rm, address, **kwargs):
        super().__init__(rm, address, **kwargs)
        config = {
            'baud_rate': 57600,
            'data_bits': 7,
            'parity': Parity.odd}
        self.configure(config)
        self.calibration = {}
    
    def add_calibration(self, channel, file):
        data = np.loadtxt(file)
        R = data[:,0]
        T = data[:,1]
        self.calibration[channel] = intp.interp1d(R, T, bounds_error=False, fill_value='extrapolate')
        
    def set_manual_control(self, range=3, maxI=0.1, resistance=50):
        self.dev.write("CMODE 1,3") # set to open loop control
        self.dev.write('CSET 1,,,1,') # set channel A to manual control
        self.dev.write('CDISP 1,1,{resistance:.0f},1')
        self.dev.write("CLIMIT 1,,,,5,5")
        self.dev.write(f"CLIMI {maxI:.3f}") # set max current limit
        self.dev.write(f'RANGE {range}') # heater range up-to 
    
    def manual_heat(self, power=None):
        if power is None:
            resp = self.dev.query("MOUT? 1")
            return float(resp.strip())
        command = f"MOUT 1,{power:.1f}"
        self.dev.write(command)
        
    def read(self, channel, unit='K', softcal=True):
        '''
        K = Kelvin
        C = Celsius
        S = Sensor imput (Ohm)
        
        channel = A,B,C,D, 0 = all
        '''
        do_softcal = False
        if unit=='K' and softcal and channel in self.calibration:
            do_softcal=True
            unit = 'S'
        command = f'{unit}RDG? {channel}'
        resp = float(self.dev.query(command))
        if do_softcal:
            T = self.calibration[channel](resp).item()
            # print(T)
            return T
        return resp
         
        