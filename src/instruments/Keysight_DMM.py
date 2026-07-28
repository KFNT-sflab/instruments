# -*- coding: utf-8 -*-
"""
Created on Fri Oct 15 11:22:22 2021

@author: ev
"""

from .Instrument import Instrument

class Keysight_DMM(Instrument):
    def __init__(self, rm , address, **kwargs):
        super().__init__(rm, address, **kwargs)
        # print(self.dev.query('*IDN?'))
        
    def get_temperature(self,probe = 'FRTD',unit = 'C'):
        """
        For detailed info about probes check: 
            https://www.testequipmentdepot.com/media/akeneo_connector/asset_files/3/4/34460a_34461a_34465a_34470a_manual_1577.pdf
            
        -----------------------------------------
        
        probe : string, which probe type to measure              
            "FRTD"  : 4 point PT100 thermometer                     \n      
            "RTD"   : 2 point  PT100 thermometer                    \n 
            "TC"    : Thermo Cuple                                  \n
            "FTHER" : 4 point thermistor                            \n
            "THER"  : 3 point thermistor
            
        unit : string, which unit to display
            "C" : celsius \n
            "K" : kelvin  \n
            "F" : farenheit (please dont use this option)
        
        """
        self.dev.write(f'UNIT:TEMP {unit}')
        return float(self.dev.query(f'MEAS:TEMp? {probe}'))
    
    def setup_voltage(self):
        self.dev.write('CONF:VOLT:DC')
        self.dev.write('TRIG:SOUR IMM')
        self.dev.write('INIT')
            
    def setup_current(self):
        self.dev.write('CONF:CURR:DC')
        self.dev.write('TRIG:SOUR IMM')
        self.dev.write('INIT')
    
    def fetch(self):
        resp = self.dev.query("FETC?")
        return float(resp)
    
    def get_value(self):
        resp = self.dev.query('MEAS?')
        # print()
        # print(resp)
        return float(resp)
    
