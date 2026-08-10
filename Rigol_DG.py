# -*- coding: utf-8 -*-
"""
Created on Thu Sep 17 12:56:38 2020

@author: emil
"""

import numpy as np
import time
from .Instrument import Instrument

class Rigol_DG(Instrument):
    """Rigol DG series signal generator.   
    """
    def __init__(self, rm, address, Z='inf', initialize_state=True, default_channel = 'CH1', **kwargs):
        super().__init__(rm, address, **kwargs)

        self.default_channel= default_channel
        if initialize_state:
            self.dev.write("FUNC SIN") # set the function to sine
            self.dev.write("VOLT:UNIT VPP")
            if Z == 'inf':
                self.dev.write("OUTP:LOAD INF")
            else:
                self.dev.write("OUTP:LOAD 50")
        self.output_amplitude = np.nan
        self.output_amplitude = float(self.amplitude())
        self.output_state = self.output()
        
        
        
    def parse_channel(self,value):
        if value == None:
            value = self.default_channel
        if value == 'CH1' or value == 'CH2':
            parsed = value[-1]
        else:
            raise(ValueError('Only "CH1" or "CH2" values are accepted!'))
        return parsed
        
    def function(self, function, channel = None):
        self.dev.write(":SOUR{}:FUNC {}".format(channel,function.upper()))
    
    def phase(self, phase, channel=None):
        _ch = self.default_channel if channel is None else channel
        _chn = self.parse_channel(_ch)
        self.dev.write(f':SOUR{_chn}:PHAS {phase%360:.4f}')

    def amplitude(self, value=None, unit=None, channel = None):
        """Availale units are VPP, VRMS and DBM
           Available channels are CH1 and CH2
        """
        
        channel = self.parse_channel(channel)
        
        if unit is not None:
            self.dev.write(f':SOUR{channel}:VOLT:UNIT {unit}')
        
        if value is not None:
            self.output_amplitude = value
            # if value < 0.0001:
            #     self.output_amplitude = 0
            #     self.output(False)
            # else:
            self.dev.write(":SOUR{}:VOLT {:.4f}".format(channel,value))

        else:
            if self.output_amplitude < 0.01:
                return 0
            return float(self.dev.query(f":SOUR{channel}:VOLT?"))
    
    def offset(self, value=None, unit=None, channel = None):
        """
        Available channels are CH1 and CH2
        """
        
        channel = self.parse_channel(channel)
        
        if unit is not None:
            self.dev.write(f':SOUR{channel}:VOLT:UNIT {unit}')
        
        if value is not None:
            self.dev.write(":SOUR{}:VOLT:LEV:OFFS {:.4f}".format(channel,value))

        else:
            if self.output_amplitude < 0.01:
                return 0
            return float(self.dev.query(f":SOUR{channel}:VOLT?"))
    
    def lolevel(self, value, channel = None):
        channel = self.parse_channel(channel)
        self.dev.write(":SOUR{}VOLT:LOW {:.4f}".format(channel,value))
    def hilevel(self, value, channel = None):
        channel = self.parse_channel(channel)
        self.dev.write(":SOUR{}VOLT:HIGH {:.4f}".format(channel,value))
    
    def frequency(self, freq=None, channel = None):
        
        channel = self.parse_channel(channel)
        
        if freq is not None:
            self.dev.write(":SOUR{}:FREQ {:.9f}".format(channel,freq))
            self.align_phase()
        else:
            return self.dev.query(f":SOUR{channel}:FREQ?")
    
    def frequency_sweep(self, enable, fi=None, ff=None, t=None, channel = None, extTrig=False):
        channel = self.parse_channel(channel)
        pref = f':SOUR{channel}:'
        if enable:
            self.dev.write(pref+"FREQ:STAR {:.3f}".format(fi))
            self.dev.write(pref+"FREQ:STOP {:.3f}".format(ff))
            self.dev.write(pref+"SWE:SPAC LIN")
            self.dev.write(pref+"SWE:TIME {:.3f}".format(t))
            if extTrig:
                print(pref+"TRIG:SOUR EXT")
                self.dev.write(pref+"SWE:TRIG:SOUR EXT")
            else:
                self.dev.write(pref+"SWE:TRIG:SOUR MAN")
                self.dev.write(pref+"SWE:TRIG:TRIGO POS")
            self.dev.write(pref+"SWE:TRIG:SLOP POS")
            self.dev.write(pref+"SWE:STAT ON")
        else:
            self.dev.write(pref+"TRIG:SOUR IMM")
            self.dev.write(pref+"SWE:STAT OFF")
        
    def amplitude_modulation(self, enable, depth, channel = None):
        """Specify the modulation depth in percent in the range 0 -- 120"""
        if enable:
            self.dev.write("AM:STAT ON")
            self.dev.write("AM:SOUR EXT")
            self.dev.write("AM:DEPTH {:.4f}".format(depth))
        else:
            self.dev.write("AM:STAT OFF")
        
    def amplitude_modulation_int(self, enable, depth, channel = None):
        """Specify the modulation depth in percent in the range 0 -- 120"""
        if enable:
            self.dev.write("AM:STAT ON")
            self.dev.write("AM:SOUR INT")
            self.dev.write("AM:DEPTH {:.4f}".format(depth))
        else:
            self.dev.write("AM:STAT OFF")
            
    def modulation_frequency (self, freq, channel = None):
        self.dev.write("AM:INT:FREQ {:.9f}".format(freq))
       
    
    def output(self, state=None, channel = None):
        channel = self.parse_channel(channel)
        if state is None:
            resp = self.dev.query(f'OUTP{channel}?')
            return bool(resp)
        if self.output_amplitude >= 0.0:
            toggled = self.output_state ^ state
            self.dev.write("OUTP{} {}".format(channel,'ON' if state else 'OFF'))
            self.output_state = state
            return toggled
        else:
            self.dev.write(f"OUTP{channel} OFF")
            return False
    
    '''
TODO?
 
# =============================================================================
#     def load_arb(self, waveform, name=None, channel = None):
#         if len(waveform)>8192:
#             raise ValueError("Maximum 8192 points allowed.")
#         waveform_txt = ""
#         for point in waveform:
#             waveform_txt += ',{:.4f}'.format(point)
#             # print(point)
#         old_timeout = self.dev.timeout
#         # print("Starting download.")
#         self.dev.timeout = 60000 #60 s
#         self.dev.write(':data volatile'+waveform_txt)
#         self.dev.timeout = old_timeout
#         # print("Download finished.")
#         # time.sleep(2)
#         if name is not None:
#             # print("Copying")
#             self.dev.write(':data:copy '+name)
#             # time.sleep(2)
# =============================================================================
    

    def select_arb(self, name, channel = None):
        # print("Selecting arb")
        self.dev.write(':func:user '+name)
        self.dev.write(':func user')
        # time.sleep(2)
        
    def burst(self, enable, N=1, source = 'bus',trig_delay = 0, channel = None):
        """
        Parameters
        ----------
        enable : Bool
            enable/disable burst mode
        N : Int, optional
            Number of cycles. The default is 1.
        source : Str, optional
            trigger source, options:
                bus - remote triggered \n
                ext - triggered from rear pannel bnc\n
            Default is 'bus', to trigger by bus use function 'gen.trig()'
        trig_delay : Float, optional
            set trigger delay in seconds, default is 0
        channel : Str, optional
            set gen output channel:
                'CH1' - channel 1\n
                'CH2' - channel 2\n
            
        Returns
        -------
        None.

        """
        channel=self.parse_channel(channel)
        if enable:
            self.dev.write(':burst:mode trig')
            self.dev.write(f':trig:sour {source}')
            self.dev.write(':trig:slop pos')
            self.dev.write(f':trig:del {trig_delay}')
            self.dev.write(':burst:ncyc {:d}'.format(N))
            self.dev.write(':burst:state on')
        else:
            self.dev.write(':burst:state off')
    '''
    
    def trig(self, channel = None):
        channel=self.parse_channel(channel)
        self.dev.write(f'TRIG{channel }')
    
    def trig_sweep(self, channel = None):
        channel=self.parse_channel(channel)
        self.dev.write(f':SOUR{channel}:SWE:TRIG')
        time.sleep(float(self.dev.query(f":SOUR{channel}:SWE:TIME?"))*1.2)

    def get_settings(self):
        """
        TODO
        

        Returns
        -------
        None.
        """
        
        return
    
    def reference_clock(self, source=None):
        if source is None:
            return self.dev.query(':SYST:ROSC:SOUR?')
        elif source in ['INT', 'EXT']:
            self.dev.write(f':SYST:ROSC:SOUR {source}')
        else:
            raise KeyError('Invalid value of "source". Available options are "INT", "EXT" or None')
    
    
    def phase_coupling(self, state=None):
        if state is None:
            resp = self.dev.query(':COUP:PHAS?')
            return True if resp == 'ON\n' else False
        elif state == True:
            self.dev.write(f":COUP:PHAS ON")
            return True
        elif state == False:
            self.dev.write(f":COUP:PHAS OFF")
            return False
        else:
            raise RuntimeError("Incorrect use of phase_coupling: state needs to be None, True or False")
    
    def align_phase(self):
        # self.dev.write(":SOUR1:PHAS:INIT")
        # self.dev.write(":SOUR2:PHAS:INIT")
        self.dev.write(":PHAS:INIT")
        
        
    