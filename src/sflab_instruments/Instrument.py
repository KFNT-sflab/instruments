# -*- coding: utf-8 -*-
"""
Created on Fri Sep  3 11:31:09 2021

Base class to represent instruments. Only opening and access control.

@author: emil
"""

import pyvisa as visa
import pyvisa.constants
from .InstrumentClient import InstrumentClient
from threading import Lock

class Instrument:
    def __init__(self, rm, address, access_mode='exclusive', **kwargs):
        self.rm = rm
        self.address = address
        self.access_mode = access_mode
        match access_mode:
            case 'shared':
                self.dev = rm.open_resource(address, access_mode=pyvisa.constants.AccessModes.shared_lock, **kwargs)
            case 'exclusive':
                self.dev = rm.open_resource(address, **kwargs)
            case 'socket':
                self.dev = InstrumentClient(address, **kwargs)
        self.locked = False
        self._lock = Lock()
    
    def configure(self, conf):
        if self.access_mode == 'socket':
            self.dev.configure(conf)
        else:
            for attr in conf:
                setattr(self.dev, attr, conf[attr])
    
    def lock(self, timeout=5000):
        self.dev.lock(timeout=timeout)
        self.locked = True
        
    def unlock(self):
        self.dev.unlock()
        self.locked = False
        
    def idn(self):
        return self.dev.query('*IDN?')
    
    def clear(self):
        self.dev.clear()
        
    def close(self):
        if self.locked:
            self.clear()
            self.unlock()
        self.dev.close()
