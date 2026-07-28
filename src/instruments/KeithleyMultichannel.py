#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Mar 27 09:39:52 2023

@author: filip
"""
import pyvisa as visa 
import numpy as np
from time import sleep

from .Instrument import Instrument

class Keithley(Instrument):
    
    def __init__ (self, rm, address, **kwargs):
        super().__init__(rm, address, **kwargs)
        self.previously_applied = {
            1: [None, None],
            2: [None, None],
            3: [None, None]
        }
        self.default_channel = "CH1"
        
    def channel(self, channel):
        '''
        Parameters
        ----------
        channel : string
        
        choose output channel: CH1, CH2, CH3

        '''
        command = f'INST:SEL {channel}'
        self.dev.write(command)
        sleep(1)
        ch = self.dev.query('INST:SEL?')
        self.default_channel = channel
        return ch
    
    def apply(self, channel, voltage=None, current=None):
        if voltage is None:
            voltage = self.previously_applied[channel][0]
        if current is None:
            current = self.previously_applied[channel][1]
        if voltage is None or current is None:
            raise ValueError("Both current and voltage need to specified at least once.")
        command = f"APPL CH{channel:d}, {voltage}, {current}"
        self.dev.write(command)
        self.previously_applied[channel][0] = voltage
        self.previously_applied[channel][1] = current

    def setvoltage(self, volt):
        command = 'VOLT {:.3f}V'.format(volt)
        self.dev.write(command)
        
    def getvoltage(self, channel='CH1'):
        command = 'FETC:VOLT?'
        set_volt = self.dev.query(command)
        return float(set_volt)
    
    def setcurrent(self,curr):
        command = 'CURR {:.3f}A'.format(curr)
        self.dev.write(command)
        
    def getcurrent(self):
        command = 'FETC:CURR?'
        set_curr = self.dev.query(command)
        return float(set_curr)
    
    def output(self, oper = False):
        if oper == True:
            #command1 = 'OUTP:ENAB 1'
            command2 = 'OUTP ON'
        if oper == False:
            #command1 = 'OUTP:ENAB 0'
            command2 = 'OUTP OFF'
        #self.dev.write(command1)
        self.dev.write(command2)
        return self.dev.query('OUTP?')
        
        
        
        