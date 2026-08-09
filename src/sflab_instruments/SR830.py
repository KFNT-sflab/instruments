# -*- coding: utf-8 -*-
"""
Created on Thu Sep 17 13:09:58 2020

@author: emil
"""

from .Instrument import Instrument

import time
import sys
import numpy as np
from ilock import ILock


tcs = ["10u", "30u", "100u", "300u",
       "1m", "3m", "10m", "30m", "100m", "300m",
       "1", "3", "10", "30", "100", "300",
       "1k", "3k", "10k", "30k"]

time_constants = {val:code for code, val in enumerate(tcs)}


senss = ["2n", "5n", "10n", "20n", "50n", "100n", "200n", "500n",
         "1u", "2u", "5u", "10u", "20u", "50u", "100u", "200u", "500u",
         "1m", "2m", "5m", "10m", "20m", "50m", "100m", "200m", "500m",
         "1"]

sensitivities = {val:code for code, val in enumerate(senss)}
sensitivities_r = {code:val for code, val in enumerate(senss)}

fslps = ['6', '12', '18', '24']
lpfslopes = {val:code for code, val in enumerate(fslps)}

suffixes = {'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3}

sample_rates = {'62.5mHz':0,'125mHz':1,'250mHz':2,'500mHz':3,'1Hz':4,'2Hz':5,'4Hz':6,
                '8Hz':7,'16Hz':8,'32Hz':9,'64Hz':10,'128Hz':11,'256Hz':12,'512Hz':13,
                'Trigger':14}

x_display = ['X','R','X noise','AUX in 1','AUX in 2']
y_display = ['Y','Theta','Y noise','AUX in 3','AUX in 4']

def code_to_value(code):
    if code[-1] in suffixes:
        return float(code[:-1])*suffixes[code[-1]]
    else:
        return float(code)

def find_best_sens(val):
    for scode in senss:
        sens = code_to_value(scode)
        if sens > 1.5*val:
            return scode
    return "1"

channels = {'X': 1, 'Y': 2, 'R': 3}

class SR830(Instrument):
    """Stanford SR830 lockin."""
    
    def __init__(self, rm, address, **kwargs):
        super().__init__(rm, address, **kwargs)
        self.sensitivities = sensitivities
        self.sensitivities_r = sensitivities_r
        
    def phase(self, phi=None):
        """ Sets or queries the phase in degree."""
        if phi is None:
            pass
        elif phi <= 729.99 and phi >= -360:
            self.dev.write('PHAS {:.3f}'.format(phi))
        else:
            raise RuntimeError('"phi" needs to be a number between -360 and 729.99 or "None", not "{}"'.format(phi))
        return float(self.dev.query('PHAS?'))
    
    def auto_phase(self):
        self.dev.write('APHS')
    
    def auto_offset(self, channel='X'):
        self.dev.write('AOFF {}'.format(channels[channel]))
        
    def auto_gain(self):
        self.dev.write('AGAN')
    
    def get_offset_expand(self, channel):
        expands = {0: 1, 1: 10, 2: 100}
        resp = self.dev.query('OEXP? {}'.format(channels[channel]))
        off_str, exp_str = resp.split(',')
        offset = float(off_str)
        expand = expands[int(exp_str)]
        return offset, expand
    
    def set_offset_expand(self, channel, expand=1, offset='auto'):
        if offset == 'auto':
            self.auto_offset(channel)
            offset, _ = self.get_offset_expand(channel)
        expands = {1: 0, 10: 1, 100: 2}
        command = "OEXP {}, {}, {}".format(channels[channel], offset, expands[expand])
        self.dev.write(command)
        
    def get_aux(self, n):
        """Reads the auxiliary input n."""
        return float(self.dev.query('OAUX? {}'.format(n)))
    
    def set_aux(self,n,U):
        """Sets the voltage (V) on auxiliary output n"""
        if abs(U) > 10.5:
            raise RuntimeError('Set voltage exceeds lockin limit 10.5 V')
        else:
            self.dev.write('AUXV {}, {}'.format(n,U))
    

    
    def reserve(self, res=None):
        """Available options are None, 'HIGH', 'NORMAL' and 'LOW'.
        Returns reserve, None option does does not set anything.
        
        """
        reserves = ['HIGH','NORMAL','LOW']
        if res in reserves:
            self.dev.write("RMOD {}".format(reserves.index(res)))
        elif not res == None:
            print("Invalid value of 'res' supplied: '{}'".format(res))
        code = int(self.dev.query('RMOD?'))
        return reserves[code]

    
    def reference(self, ref=None):
        """ Sets the reference to 'external' or 'internal'."""
        if ref=='external':
            self.dev.write('FMOD 0') # external reference
        elif ref=='internal':
            self.dev.write('FMOD 1') # internal reference
        elif ref == None:
            pass
        else:
            raise RuntimeError("Bad reference option: {}".format(ref))
        code = int(self.dev.query('FMOD?'))
        if code == 0:
            return 'external'
        elif code == 1:
            return 'internal'
    
    def reference_trigger(self,trigger = None):
        """
        Read and optionally set the reference trigger option. \n
        Options:
            None : Read the value only
            
            'Sine' : Set Sine and read
            
            'Pos edge' : Set Pos edge and read
            
            'Neg edge' : Set Neg edge and read
        """
        codes = ['Sine','Pos edge','Neg edge']
        if trigger == None:
            pass
        elif trigger in codes:
            self.dev.write('RSLP {}'.format(codes.index(trigger)))  
        else:
            raise RuntimeError('Invalid value of "trigger" supplied: "{}"'.format(trigger))
        code = int(self.dev.query('RSLP?'))
        return codes[code]
    
    def get_signal_input(self):
        """
        Read signal input configuration
        """
        codes = ['A','A-B','I (1 MOhm)','I (100 MOhm)']
        code = int(self.dev.query('ISRC?'))
        return codes[code]
    
    def set_signal_input(self, input):
        """
        Read signal input configuration
        """
        codes = ['A','A-B','I (1 MOhm)','I (100 MOhm)']
        code = codes.index(input)
        self.dev.write(f'ISRC {code}')
        
    def harmonic(self, harm=None):
        """
        Sets or queries the harmonic

        Parameters
        ----------
        harm : int or None, optional
            Sets the harmonic to this number. If None, queries and returns the set harmonic. The default is None.

        Returns
        -------
        int
            The harmonic set on the instrument.
        """
        if harm is None:
            pass
        else:
            self.dev.write('HARM {}'.format(harm))
        return int(self.dev.query('HARM?'))
    
    def input_shield(self,grounding=None):
        """
        Read and optionally set the input shield coupling. \n
        Options:
            None : Read the value only
            
            'Float' : Set Float and read
            
            'Ground' : Set Ground and read
            
        """
        codes = ['Float','Ground']
        if grounding == None:
            pass
        elif grounding in codes:
            self.dev.write('IGND {}'.format(codes.index(grounding)))
        else:
            raise RuntimeError('Invalid value of "grounding" supplied: {}'.format(grounding))
        code = int(self.dev.query('IGND?'))
        return codes[code]
    
    def coupling(self, cpl=None):
        """Sets the coupling to 'AC' or 'DC'."""
        codes = ['AC','DC']
        if cpl == 'AC':
            self.dev.write('ICPL 0')
        elif cpl == 'DC':
            self.dev.write('ICPL 1')
        elif cpl == None:
               pass
        else:
            raise RuntimeError("Unknown coupling {}, only DC or AC allowed".format(cpl))
        return codes[int(self.dev.query('ICPL?'))]
    
    def line_filter(self,line = None):
        """
        Read and optionally set the line filter. \n
        Options:
            None : Read the value only
            
            'No filter', '1x line', '2x line', 'Both' : Set and read
        """
        codes = ['No filter','1x line','2x line','Both']
        if line == None:
            pass
        elif line in codes:
            self.dev.write('ILIN {}'.format(codes.index(line)))
        else:
            raise RuntimeError('Invalid value of "line" supplied: {}'.format(line))
        code = int(self.dev.query('ILIN?'))
        return codes[code]
    
    def sync(self,sync = None):
        """
        Read and optionally set the sync. \n
        Options:
            None : Read the value only
            
            'On', 'Off' : Set and read value
        """
        codes = ['Off','On']
        if sync == None:
            pass
        elif sync in codes:
            self.dev.write('SYNC {}'.format(codes.index(sync)))
        else:
            raise RuntimeError('Invalid value of "sync" supplied: {}'.format(sync))
        code = int(self.dev.query('SYNC?'))
        return codes[code]
    
    
    
    def set_timeconstant(self, tc):
        """
        Sets the time constant

        Parameters
        ----------
        tc : string
            The time constant in the format as written on the front panel of the instrument.
            "10m", "30m", "100m" would be 10ms, 30ms and 100ms, and so on ("10u" is minimum)

        Returns
        -------
        None.

        """
        # print("Setting tc")
        self.dev.write("OFLT {}".format(time_constants[tc]))
        # print("OK")

    def get_timeconstant(self):
        return tcs[int(self.dev.query('OFLT?'))]
    
    def get_drive(self):
        return self.dev.query('SLVL?')
           
    def set_sensitivity(self, sens):
        """
        Sets the sensitivity.

        Parameters
        ----------
        sens : string
            The sensitivity in the format as written on the front panel of the instrument for voltage measurement.
            "10m", "20m", "50m" would be 10mV, 20mV, 50mV and so on.

        Returns
        -------
        None.

        """
        self.dev.write("SENS {}".format(sensitivities[sens]))
    
    def get_sensitivity(self, return_code=False):
        code = int(self.dev.query("SENS?"))
        if return_code:
            return code
        return code_to_value(senss[code])
    
    def set_slope(self, slope):
        """ Set the low-pass filter slope. Options are '6', '12', '18', '24'."""
        self.dev.write("OFSL {}".format(lpfslopes[slope]))

    def get_slope(self):
        return fslps[int(self.dev.query('OFSL?'))]
     
    def set_output_amplitude(self, A):
        self.dev.write("SLVL {:.3f}".format(A))
    
    def get_output_amplitude(self):
        return float(self.dev.query("SLVL?"))

    def set_frequency(self, freq):
        """Set the demodulation frequency to freq, only for the internal reference mode."""
        self.dev.write('FREQ {:.3f}'.format(freq))
    
    def get_frequency(self):
        return float(self.dev.query('FREQ?'))
    
    def get_xy(self):
        resp = self.dev.query("SNAP? 1,2")
        xstr, ystr = resp.split(',')
        x = float(xstr)
        y = float(ystr)
        return x, y
    
    def auto_sens(self, maxval, do_set=True):
        sens = find_best_sens(maxval)
        if do_set:
            self.set_sensitivity(sens)
        return code_to_value(sens)
    
    def overloadp(self):
        status = int(self.dev.query('LIAS?'))
        self.dev.clear()
        inputo = bool(status & (1 << 0))
        filtro = bool(status & (1 << 1))
        outputo = bool(status & (1 << 2))
        return (inputo or filtro or outputo)

    def set_display(self, channel:int,  display:str):
        """
        Set display value on channel.
        ----------
        channel : lockin channel\n
        display : quantity to display \n
            channel == 1:
                'X', 'R', 'X noise', 'AUX in 1', 'AUX in 2' 
            channel == 2:
                'Y', 'Theta', 'Y noise', 'AUX in 3', 'AUX in 4'
        -----------
        
        Important function, because data buffer saves display values       
        """

        try:
            if channel == 1:
                i = x_display.index(display)
            elif channel == 2:
                i = y_display.index(display)
            else:
                raise KeyError("Invalid value '{}' of 'channel'".format(channel))
        except:
            raise KeyError("Invalid value '{}' of 'display'".format(display))
            
        self.dev.write("DDEF {:d}, {:d}, 0".format(channel, i))

    def get_display(self):
        """
        Get display value on CH1 and CH2.
        ----------
        Returns
        ----------
        display :  (int)
            0 : Y   \n
            1 : Theta    \n
            2 : Y noise  \n
            3 : AUX in 3  \n
            4 : AUX in 4   \n
        -----------
        Important function, because data buffer saves display values       
        """
        display1 = self.dev.query("DDEF? 1")
        display2 = self.dev.query("DDEF? 2")
        return x_display[int(display1[0])],y_display[int(display2[0])]
    
    def get_analog_output_settings(self):
        codesx = ['Display','X']
        codesy = ['Display','Y']
        codex = int(self.dev.query('FPOP? 1'))
        codey = int(self.dev.query('FPOP? 2'))
        return codesx[codex],codesy[codey]
    
    def get_ratio_settings(self,channel:int):
        settings=[ ['Off','div by AuxIn1','div by AuxIn2'],['Off','div by AuxIn3','div by AuxIn4']]
        
        code = int(self.dev.query('DDEF? {}'.format(channel)).split(',')[1])
        return settings[channel-1][code]
    
    def buffer_shot(self,sample_rate:str,N:int,debug:bool=False):
        """
        Measure buffer in shot mode, with given sample rate. SR830 saves data from
        CH1 and CH2 DISPLAY and stores them into the internal buffer. \n
        CH1 and CH2 display points are measured at the same time. \n
        IMPORTANT: MAKE SURE LOCKIN DISPLAY IS SET TO CORRECT QUANTITY. \n
        While buffer data are transfered to PC, data transfer from other
        lockins is locked, but it is advised to have only one console using this function at any given time.
        
        Parameters
        ----------
        sample_rate : str
            permitted values \n
            62.5mHz  \n
            125mHz  \n
            250mHz  \n
            500mHz  \n
            1Hz  \n
            2Hz  \n
            4Hz  \n
            8Hz  \n
            16Hz  \n
            32Hz  \n
            64Hz  \n
            128Hz  \n
            256Hz  \n
            512Hz  \n
            Trigger
            
        N  : int
            number of measured points, max 16383

        debug : bool
            print progress
        Returns
        -------
        CH1 : numpy array
            measured CH1 display points
        CH2 : numpy array
            measured CH2 display points
        """ 
        try:
            i = sample_rates[sample_rate]
        except:
            raise KeyError('Invalid sample rate')
            
        self.dev.write(f'SRAT {i}')
        if N > 16383:
            raise Exception('Maximum number of measured points (16383) exceeded!')
        
       
        with ILock('aaa'):
            self.dev.write('PAUS')
            self.dev.write('REST')
            self.dev.write('STRT')
        j = 0
        
        sample_rate_float = 0.0625*2**i
        time.sleep(N/sample_rate_float +2)
        
        with ILock('aaa'):
            j = int(self.dev.query('SPTS?'))
            if j<N:
                while j+1<=N:
                    time.sleep(2)
                    j = int(self.dev.query('SPTS?'))
            self.dev.write('PAUS')
        
        if debug:
            print(f'\nNumber of points in buffer: {j}')
        
        try:
            start = time.time()
            old_timeout = self.dev.timeout
            self.dev.timeout = None
            with ILock('aaa',timeout=5*60):
                X_buffer = self.dev.query_binary_values(f'TRCB? 1,0,{N}',datatype='f',data_points = N,header_fmt='empty')
                Y_buffer = self.dev.query_binary_values(f'TRCB? 2,0,{N}',datatype='f',data_points = N,header_fmt='empty')
            self.dev.timeout = old_timeout
            end = time.time()
            if debug:
                print(f'Transfer took: {end-start}s')
        except Exception as e:
            self.dev.write('REST')
            raise Exception(f'Could not extract buffer data\nError: {e}')
        
        CH1 = np.array(X_buffer)
        CH2 = np.array(Y_buffer)
        self.dev.write('REST')
        self.buffer_X = X_buffer
        self.buffer_Y = Y_buffer
    
        return CH1,CH2
    
    def get_settings(self):
        """
        Return the device settings as a dictionary. \n
        
        ---------------------------------------
        
        Included features: Input impedance, reserve, time constant,\n
        filter slope, sensitivity, phase, reference mode, harmonic and more
        """
        self.dev.clear()
        signal_input = self.get_signal_input()
        coupling = self.coupling()
        reserve = self.reserve()
        line_filter = self.line_filter()
        sync = self.sync()
        timeconstant = self.get_timeconstant()
        slope = self.get_slope()
        sens = self.get_sensitivity()
        phase = self.phase()
        reference = self.reference()
        ref_trigger = self.reference_trigger()
        harmonic = self.harmonic()
        offsX,expX = self.get_offset_expand('X')
        offsY,expY = self.get_offset_expand('Y')
        offsR,expR = self.get_offset_expand('R')
        disp1,disp2 = self.get_display()
        analog_outp1,analog_outp2 = self.get_analog_output_settings()
        aux_ratio1 = self.get_ratio_settings(1)
        aux_ratio2 = self.get_ratio_settings(2)
        amp = self.get_drive()
        freq = self.get_frequency()
        
        return {'Signal input':signal_input,'Reserve':reserve,'Time constant (s)':timeconstant,
                'Filter slope (dB)':slope,'Sensitivity (V)':sens,'Coupling':coupling,'Line filter':line_filter,
                'Sync':sync,'Ref trigger':ref_trigger ,'Phase (deg)':phase,'Referece':reference,
                'Harmonic':harmonic,'X expand':expX,'Y expand':expY, 'R expand':expR, 'X offset (percent)':offsX,
                'Y offset (percent)':offsY,'R offset (percent)':offsR ,'CH1 display':disp1,'CH2 display':disp2,
                'CH1 Aux ratio settings':aux_ratio1,'CH2 Aux ratio settings':aux_ratio2,
                'CH1 analog output':analog_outp1,'CH2 analog output':analog_outp2,'Sine output amplitude (Vrms)': amp,
                'Frequency': freq}