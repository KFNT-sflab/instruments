# -*- coding: utf-8 -*-
"""
Created on Sun Sep  6 11:02:29 2020

Class to control the AnaPico / BNC RF sources.

@author: Emil
"""

from .Instrument import Instrument

class RFsource(Instrument):
    """Very basic interface to the AnaPico / BNC RF sources."""
    
    def __init__(self, rm, address='USB0::0x03EB::0xAFFF::4C1-3A3200905-1225::0::INSTR'):
        super().__init__(rm, address)
        print(self.idn())
        
    def frequency(self, set_freq=None):
        """Set or query the frequency in Hz."""
        if set_freq is None:
            return float(self.dev.query(':FREQ?'))
        self.dev.write(':FREQ {:.3f}'.format(set_freq))
    
    def phase(self, set_phase=None):
        """
        Sets or queries the phase.

        Parameters
        ----------
        set_phase : float [radians], optional
            Sets the phase. If None (default) asks for the phase and returns it

        Returns
        -------
        The phase is set_phase=None.

        """
        if set_phase is None:
            return float(self.dev.query(':PHAS?'))
        self.dev.write(':PHAS {:.5f} rad'.format(set_phase))
    
    def output(self, set_status=None):
        """Set or query the output status."""
        if set_status is None:
            stat = int(self.dev.query(':OUTP?'))
            return bool(stat)
        if set_status:
            self.dev.write(':OUTP ON')
        else:
            self.dev.write(':OUTP OFF')
    
    def power(self, set_power=None):
        """Set or query the output power in dBm"""
        if set_power is None:
            return float(self.dev.query(':POW:LEV?'))
        self.dev.write(':POW:LEV {:.3f}'.format(set_power))
        
    def am(self, state=None, sens=0.1):
        if state is None:
            print(self.dev.query(':AM:STAT?'))
            print(self.dev.query(':AM:SOUR?'))
            print(self.dev.query(":AM:SENS?"))
            return
        if state:
            self.dev.write(':AM:SOUR EXT')
            self.dev.write(':AM:SENS {:.2f}'.format(sens))
            self.dev.write(':AM:STAT 1')
        else:
            self.dev.write(':AM:STAT 0')
    
    def pm(self, state=None, sens=1):
        if state is None:
            print(self.dev.query(':PM:STAT?'))
            print(self.dev.query(':PM:SOUR?'))
            print(self.dev.query(":PM:SENS?"))
            return
        if state:
            self.dev.write(':PM:SOUR EXT')
            self.dev.write(':PM:SENS {:.2f}'.format(sens))
            self.dev.write(':PM:STAT 1')
        else:
            self.dev.write(':PM:STAT 0')
    
    def reference(self, source=None, reffreq=None):
        if source is None:
            return self.dev.query(':ROSC:SOUR?').strip()
        self.dev.write(':ROSC:SOUR {}'.format(source))
        if reffreq is not None:
            self.dev.write(':ROSC:EXT:FREQ {:.5f}'.format(reffreq))
    
    def reflocked(self):
        return self.dev.query(':ROSC:LOCK?')
    
    def refout(self, state=None):
        if state is None:
            return self.dev.query(':ROSC:OUTPUT:STAT?')
        else:
            if state:
                self.dev.write(':ROSC:OUTPUT:STAT ON')
            else:
                self.dev.write(':ROSC:OUTPUT:STAT OFF')
    
BNC865 = RFsource

if __name__ == '__main__':
    import visa
    rm = visa.ResourceManager()
    rf = BNC865(rm, 'USB0::0x03EB::0xAFFF::4C1-3A3200905-1225::0::INSTR')
    # rf.frequency(2.78e9)
    # rf.power(16)
    # rf.output(True)
    print(rf.frequency())
    print(rf.output())
    print(rf.power())
    rf.close()