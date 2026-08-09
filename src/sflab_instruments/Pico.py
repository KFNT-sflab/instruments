#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jan  1 22:26:02 2024

@author: emil
"""

from .Instrument import Instrument
import numpy as np

class Pico(Instrument):
    code_to_accel = 2*9.81 / 32768
    code_to_gyro = 250 / 32768  # degrees per second per count

    def __init__(self, rm, addr, **kwargs):
        super().__init__(rm, addr, **kwargs)
        
        self.configure({'read_termination': '\n',
                        'write_termination': '\n'})
    
    # def LED(self, n, status):
    #     msg = f':LED {n} 1' if status else f':LED {n} 0'
    #     return self.dev.query(msg)
    
    def led(self, n, onoff):
        #turn the LED n on or off
        self.dev.query(f':LED {n:d} {onoff:d}')
    
    def readACC(self):
        #read the accelerometer, which returns data as a string
        # ax ay az (space-separated floating point numbers)
        acc_str = self.dev.query(':READ:ACC?')
        acc = np.array([float(c)*self.code_to_accel for c in acc_str.split()])
        return acc
    
    def readGYR(self):
        # read the gyroscope, returns similar data as accelerometer
        gyr_str = self.dev.query(':READ:GYR?')
        gyr = np.array([float(c)*self.code_to_gyro for c in gyr_str.split()])
        return gyr
    
    def readT(self):
        # read the temperature, the response string
        # is 100*T, where T is the temperature in celsius
        resp = self.dev.query(':READ:T?')
        return float(resp)/100

    def readP(self):
        #read pressure, in Pa
        resp = self.dev.query(':READ:P?')
        return float(resp)
    
    def shut_down(self):
        for k in range(5):
            self.led(k, 0)

