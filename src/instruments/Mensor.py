# -*- coding: utf-8 -*-
"""
Created on Sun Oct  3 10:41:50 2021

@author: ev
"""

from .Instrument import Instrument

class Mensor(Instrument):
    def __init__(self, rm, address):
        super().__init__(rm, address)
        self.dev.timeout=10000
        # self.dev.read_termination='\r'
        # self.dev.write_termination='\r'

    def read(self):
        resp = self.dev.query('#*?')
        self.clear()
        # print('response:', resp)
        return float(resp.split()[-1])
    
    def read2(self, attempts=5):
        attempted=0
        self.locked=False
        while True:
            try:
                self.lock()
                self.locked=True
                P = self.read()
                break
            except:
                attempted += 1
                if attempted > attempts:
                    continue
                else:
                    raise
            finally:
                if self.locked:
                    self.unlock()
        return P