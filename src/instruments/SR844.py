# -*- coding: utf-8 -*-
"""
Created on Thu July  7 15:00 2022

@author: Emil
"""

from .Instrument import Instrument

import time

tcs = ["100u", "300u",
       "1m", "3m", "10m", "30m", "100m", "300m",
       "1", "3", "10", "30", "100", "300",
       "1k", "3k", "10k", "30k"]

time_constants = {val:code for code, val in enumerate(tcs)}

senss = ["100n", "300n", "1u", "3u", "10u", "30u", "100u", "300u",
         "1m", "3m", "10m", "30m", "100m", "300m", "1"]

sensitivities = {val:code for code, val in enumerate(senss)}
sensitivities_r = {code:val for code, val in enumerate(senss)}

fslps = ['nofilter', '6', '12', '18', '24']
lpfslopes = {val:code for code, val in enumerate(fslps)}

suffixes = {'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3}
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

class SR844(Instrument):
    """Stanford SR844 lockin."""
    
    def __init__(self, rm, address, **kwargs):
        super().__init__(rm, address, **kwargs)
        self.sensitivities = sensitivities
        self.sensitivities_r = sensitivities_r
        self.dev.clear()
        
    def phase(self, phi=None):
        if phi is None:
            return float(self.dev.query('PHAS?'))
        else:
            self.dev.write('PHAS {:.3f}'.format(phi))
    
    def auto_phase(self):
        self.dev.write('APHS')
    
    def auto_offset(self, channel='X'):
        self.dev.write('AOFF {}'.format(channels[channel]))
        
    def auto_gain(self):
        self.dev.write('AGAN')
    
    def get_offset_expand(self, channel):
        """
        Parameters
        ----------
        channel : int
            1 : CH1
            2 : CH2

        Returns
        -------
        offset : float
            percent of full scale of display variable
        expand : int
            expand of offsetted display variable
        """
        expands = {0: 1, 1: 10, 2: 100}
        exp_str = self.dev.query('DEXP? {},0'.format(channel))
        offset = float(self.dev.query('DOFF? {},0'.format(channel)))
        expand = expands[int(exp_str)]
        return offset, expand
    
    def set_offset_expand(self, channel, expand=1, offset='auto'):
        """
        right now sets only the expand of the channel
        """
        if offset == 'auto':
            self.auto_offset(channel)
            offset, _ = self.get_offset_expand(channel)
        expands = {1: 0, 10: 1, 100: 2}
        command = "OEXP {}, {}, {}".format(channels[channel], offset, expands[expand])
        self.dev.write(command)
    
    def input_impedance(self, imp=None):
        if imp == None:
            code = int(self.dev.query('INPZ?'))
            if code == 0:
                return '50'
            elif code == 1:
                return 'HIZ'
            else:
                raise ValueError("Invalid code.")   
        if imp == '50':
            self.dev.write('INPZ 0')
        elif imp.upper() == 'HIZ':
            self.dev.write('INPZ 1')
        else:
            raise RuntimeError(f"Unknown coupling {imp}, only '50' (50 Ohm) or 'HIZ' (1 Mohm) allowed")
            
    
    def wide_reserve(self, res=None):
        """Select or get wide reserve, before the mixer.\n Unless something overloads, LOW is preferred. \n
        Available options are 'HIGH', 'NORMAL' and 'LOW'. Input 'None' to get reserve."""
        reserves = {'HIGH': 0, 'NORMAL': 1, 'LOW': 2}
        reserves_inverse = {0:'HIGH', 1:'NORMAL', 2:'LOW'}
        if res == None:
            return reserves_inverse[int(self.dev.query('WRSV?'))]
        else:
            try:
                self.dev.write("WRSV {}".format(reserves[res.upper()]))
            except KeyError:
                raise ValueError("Only 'HIGH', 'NORMAL' and 'LOW'  reserves are available.")
    
    def close_reserve(self, res=None):
        """Select or get close reserve, after the mixer and before analog to digital conversion.\n Unless something overloads, LOW is preferred. \n
        Available options are 'HIGH', 'NORMAL' and 'LOW'. Input 'None' to get reserve."""
        reserves = {'HIGH': 0, 'NORMAL': 1, 'LOW': 2}
        reserves_inverse = {0:'HIGH', 1:'NORMAL', 2:'LOW'}
        if res == None:
            return reserves_inverse[int(self.dev.query('CRSV?'))]
        else:
            try:
                self.dev.write("CRSV {}".format(reserves[res.upper()]))
            except KeyError:
                raise ValueError("Only 'HIGH', 'NORMAL' and 'LOW'  reserves are available.")
    
    def reference(self, ref=None):
        if ref=='external':
            self.dev.write('FMOD 0') # external reference
        elif ref=='internal':
            self.dev.write('FMOD 1') # internal reference
        elif ref == None:
            pass
        else:
            raise RuntimeError("bad reference option: {}".format(ref))
        code = float(self.dev.query('FMOD?'))
        if code == 0:
            return 'external'
        elif code == 1:
            return 'internal'
            
    def ref_impedance(self,imp = None):
        ref_imp_settings={'50':0,'10k':1}
        if imp in ['50','10k']:
            self.dev.write('REFZ {}'.format(ref_imp_settings[imp]))
        elif imp == None:
            pass
        else:
            raise RuntimeError('Invalid value of imp: "{}"'.format(imp))
        return list(ref_imp_settings.keys())[int(self.dev.query('REFZ?'))]
        
    def harmonic(self, harm=None):
        """
        Set or get harmonic.\n
        Allowed values: 1, 2, None. \n
        1, 2 for first and second harmonic, respectively. \n
        'None' returns the harmonic value.\n
        """
        if harm == None:
            pass
        elif harm in [1,2]:
                harm -= 1
                self.dev.write('HARM {}'.format(harm))        
        else:
                raise RuntimeError('Bad harmonic option {}'.format(harm))
        return int(self.dev.query('HARM?')) + 1        
    
    def set_timeconstant(self, tc):
        self.dev.write("OFLT {}".format(time_constants[tc]))

    def get_timeconstant(self):
        return tcs[int(self.dev.query('OFLT?'))]
    
    def set_sensitivity(self, sens):
        self.dev.write("SENS {}".format(sensitivities[sens]))
    
    def get_sensitivity(self, return_code=False):
        code = int(self.dev.query("SENS?"))
        if return_code:
            return code
        return code_to_value(senss[code])
    
    def set_slope(self, slope):
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
    
    def get_chop_frequency(self):
        return float(self.dev.query('FRIQ?'))
    
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
    
    def set_display(self,channel,display):
        """
        TODO write
        """
        self.dev.write()
        
    def get_display(self):
        codesx = ['X',r'R[V]',r'R[dbm]','Xn','AuxIn1']
        codesy = ['Y','Theta','Yn',r'Yn[dbm]','AuxIn2']
        codex = int(self.dev.query('DDEF? 1'))
        codey = int(self.dev.query('DDEF? 2'))
        return codesx[codex],codesy[codey]
        
    def get_analog_output_settings(self):
        codesx = ['Display','X']
        codesy = ['Display','Y']
        codex = int(self.dev.query('FPOP? 1'))
        codey = int(self.dev.query('FPOP? 2'))
        return codesx[codex],codesy[codey]
    
    def set_analog_output_settings(self, ch, what):
        match what:
            case 'XY':
                code = 1
            case 'display':
                code = 0
            case _:
                raise ValueError(f"Invalid setting {what}")
        self.dev.write(f'FPOP {ch} {code}')
    
    def get_aux_input(self,input_number):
        if input_number in [1,2]:
            return float(self.dev.query('AUXI? {}'.format(input_number)))
        else:
            raise RuntimeError('Invalid number "{}"'.format(input_number))
    
    def get_ratio_settings(self):
        settings = ['Off','div by AuxIn1','div by AuxIn2']
        code = int(self.dev.query('DRAT?'))
        return settings[code]
    
        
    def get_settings(self):
        """
        Return the device settings as a dictionary. \n
        
        ---------------------------------------
        
        Included features: Input impedance, wide reserve, time constant,\n
        filter slope, close reserve, sensitivity, phase, reference mode, harmonic
        """
        self.dev.clear()
        impedance = self.input_impedance()
        wide_reserve = self.wide_reserve()
        timeconstant = self.get_timeconstant()
        slope = self.get_slope()
        close_reserve = self.close_reserve()
        sens = self.get_sensitivity()
        phase = self.phase()
        reference = self.reference()
        harmonic = self.harmonic()
        reference_impedance = self.ref_impedance()
        offs1,exp1 = self.get_offset_expand(1)
        offs2,exp2 = self.get_offset_expand(2)
        disp1,disp2 = self.get_display()
        analog_outp1,analog_outp2 = self.get_analog_output_settings()
        aux_ratio = self.get_ratio_settings()
        frequency = self.get_frequency()
        
        return {'Input impedance':impedance,'Wide reserve':wide_reserve,'Time constant (s)':timeconstant,
                'Filter slope (dB)':slope,'Close reserve':close_reserve,'Sensitivity (V)':sens,
                'Phase (deg)':phase,'Referece':reference,'Ref impedance':reference_impedance,
                'Harmonic':harmonic,'CH1 expand':exp1,'CH2 expand':exp2,'X offset (percent)':offs1,
                'Y offset (percent)':offs2,'CH1 display':disp1,'CH2 display':disp2,'Aux ratio settings':aux_ratio,
                'CH1 analog output':analog_outp1,'CH2 analog output':analog_outp2,'Frequency':frequency}
    
    def query_unlock(self):
        """
        Query lockin reference unlock, True if unlocked, False if locked

        Returns
        -------
        TYPE
            bool

        """
        return bool(int(self.dev.query('LIAS? 0')))