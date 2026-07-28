# -*- coding: utf-8 -*-
"""
Created on Wed Nov  6 22:37:53 2024

@author: balazs
"""

from .DAQcard import DAQcard

from scipy import signal
import numpy as np
from math import atan2

import warnings

import matplotlib.pyplot as plt


class Lock_in:
    def __init__(self, time_constant, filter_order = 4, phase = 0, harmomic = 1):
        self.time_constant = time_constant
        self.filter_order = filter_order
        self.phase = phase*180/np.pi
        self.harm = harmomic
    
    def get_ref(self, ref_freq, ts):
        ref_cos = np.cos(2*np.pi*ref_freq*ts + self.phase)
        ref_sin = np.sin(2*np.pi*ref_freq*ts + self.phase)
        
        return ref_cos, ref_sin
    
    def digital_ref(self, ref):
        ref_fft = np.fft.rfft(ref)
        psd = ref_fft*np.conj(ref_fft)
        fft_freq = np.fft.rfftfreq(len(ref))
        
        f_ref = abs(fft_freq[np.argsort(psd)[-2]])
        # print(f_ref)
        ts = np.arange(len(ref))
        
        # fig, ax = plt.subplots()
        # plt.plot(fft_freq, psd)
        # print(fft_freq[np.argsort(psd)])
        
        # raise
        
        # ref_comp = np.exp(2j*np.pi*f_ref*ts)
        
        ref_gen_r = np.cos(2*np.pi*f_ref*ts) > 0
        ref_gen_i = np.sin(2*np.pi*f_ref*ts) > 0 
                
        # overlap = ref_comp*ref
        # overlap_integral = np.sum(overlap)
        # phase = atan2(overlap_integral.imag, overlap_integral.real)
        
        overlap_r = np.sum(ref_gen_r*ref)
        overlap_i = np.sum(ref_gen_i*ref)
        
        phase = atan2(overlap_i, overlap_r)
        
        return f_ref, phase, ts
    
    def sig_out(self, sig, ref, sample_rate):
        ref_freq, phase0, ts = self.digital_ref(ref)
        #print(ref_freq, phase0)
        ref_cos, ref_sin = self.get_ref(self.harm*ref_freq, ts)
        
        ts = ts.astype(np.float64)/float(sample_rate)
        
        i_sig = sig*ref_cos
        q_sig = sig*ref_sin
        
        sos = signal.butter(self.filter_order, 2*np.pi/self.time_constant, 'low', output='sos', fs = sample_rate)
        
        i_sig_filt = signal.sosfilt(sos, i_sig)
        q_sig_filt = signal.sosfilt(sos, q_sig)
        
        return i_sig_filt, q_sig_filt


suffixes = {'n': 1e-9, 'u': 1e-6, 'm': 1e-3, 'k': 1e3}

def value_parser(tc):
    try:
        time_const = float(tc)
    except ValueError:
        val, ev = tc[:-1], tc[-1]
        time_const = float(val)*suffixes[ev]
    return time_const

fslps = {'6':1, '12':2, '18':3, '24':4}

def lpf_slope_parser(lpfs):
    try:
        order = fslps[lpfs]
    except KeyError:
        if isinstance(lpfs, str):
            try:
                order = int(lpfs)
            except ValueError:
                raise(Exception('Lowpass filter slope must be convertable to integer'))
            order = max(1, lpfs//6)
    return order



default_args = {'time_const': '100m',
                'sensitivity': 1,
                'lpfs': 2}

class Dev_emulator():
    def __init__(self, name = 'dev'):
        self.name = name
        
    def clear(self):
        pass
    def query(self, *args, **kwarg):
        return self.name
    def configure(self, conf):
        pass
    def lock(self, timeout=5000):
        pass
    def unlock(self):
        pass
    def close(self):
        pass
    
    
    
class DAQ_Lockin():
    """Lockin emulator with DAQcard"""
    
    def __init__(self, *args, **kwargs):
        self.daq_kwargs = {'channels': ['ai1', 'ai2'],
                           'max_val': 10,
                           'min_val': -10,
                           'rate': 100_000,
                           'samples': 10_000,
                           'terminal_config': 'RSE'}
        
        self.daq = DAQcard(**self.daq_kwargs)
        
        self.lockin = Lock_in(value_parser(default_args['time_const']),
                                filter_order=default_args['lpfs'])
        self.ref_freq = None
        self.dev = Dev_emulator('DAQ_lockin')
        
        self.locked = False
        
    def phase(self, phi=None):
        """ Sets or queries the phase in degree."""
        if phi is None:
            return self.lockin.phase
        else:
            self.lockin.phase = phi
    
    def auto_phase(self):
        raise NotImplementedError('auto_phase function of SR830 not implemented in DAQ_Lockin')
    
    def auto_offset(self, channel='X'):
        raise NotImplementedError('auto_offset function of SR830 not implemented in DAQ_Lockin')
        
    def auto_gain(self):
        raise NotImplementedError('auto_gain function of SR830 not implemented in DAQ_Lockin')
    
    def offset_expandq(self, channel):
        raise NotImplementedError('offset_expandq function of SR830 not implemented in DAQ_Lockin')
    
    def offset_expand(self, channel, expand=1, offset='auto'):
        raise NotImplementedError('offset_expand function of SR830 not implemented in DAQ_Lockin')
        
    def get_aux(self, n):
        raise NotImplementedError('get_aux function of SR830 not implemented in DAQ_Lockin')
    
    def set_aux(self,n,U):
        raise NotImplementedError('set_aux function of SR830 not implemented in DAQ_Lockin')
    
    def coupling(self, cpl):
        """Sets the coupling to 'AC' or 'DC'."""
        raise NotImplementedError('couling function of SR830 not implemented in DAQ_Lockin')
    
    def set_reserve(self, res):
        """Available options are 'high', 'normal' and 'low'."""
        raise NotImplementedError('set_reserve function of SR830 not implemented in DAQ_Lockin')
    
    def reference(self, ref):
        """ Sets the reference to 'external' or 'internal'."""
        if ref != 'external':
            raise NotImplementedError('only external reference is implemented DAQ_Lockin')
        
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
            The harmonic set on the instrument. Does not return anything if harm is a number.
        """
        if harm is None:
            return self.lockin.harm
        else:
            self.lockin.harm = harm
    
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
        self.lockin.time_constant = value_parser(tc)
        self.set_wait(self.lockin.time_constant)
    
    def set_wait(self, wait_time):
        '''
        New function added to DAQ_Lockin, sets the length of one measuremet.
        Reinitiates the DAQcard used.
        '''
        self.daq_kwargs['samples'] = int(wait_time*self.daq_kwargs['rate'])
        self.daq.close()
        self.daq = DAQcard(**self.daq_kwargs)
    
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
        warnings.warn('DAQ do not have sensitivity in that sense') 
    
    def get_sensitivity(self, return_code=False):
        warnings.warn('DAQ do not have sensitivity in that sense') 
    
    def set_slope(self, slope):
        """ Set the low-pass filter slope. Options are '6', '12', '18', '24'."""
        self.lockin.filter_order = lpf_slope_parser(slope)
        
    def set_output_amplitude(self, A):
        raise NotImplementedError('set_output_amplitude function of SR830 not implemented in DAQ_Lockin')
    
    def get_output_amplitude(self):
        raise NotImplementedError('get_output_amplitude function of SR830 not implemented in DAQ_Lockin')

    def set_frequency(self, freq):
        raise NotImplementedError('set_frequency function of SR830 not implemented in DAQ_Lockin')
    
    def get_frequency(self):
        raise NotImplementedError('get_frequency function of SR830 not implemented in DAQ_Lockin')
    
    def get_xy(self, which = 0):
        data = self.daq.measure()
        sig = data[which, :]
        ref = data[-1, :]
        
        
        samp_freq = self.daq_kwargs['samples']
        ts = np.arange(0, len(sig), dtype = np.float64)/samp_freq
        
        xs, ys = self.lockin.sig_out(sig, ref, self.daq_kwargs['rate'])
        
        # print(xs, ys)
        
        # raise
        
        # if self.ref_freq:
        #     xs, ys = self.lockin.sig_out(sig, ts, self.ref_freq)
        # else:
        #     raise Exception('you need to make sure to set the frequency manually to the generator frequency')
        
        x = np.mean(xs)
        y = np.mean(ys)
        
        return x, y
    
    def auto_sens(self, maxval, do_set=True):
        raise NotImplementedError('auto_sens function of SR830 not implemented in DAQ_Lockin')
    
    def overloadp(self):
        raise NotImplementedError('overloadp function of SR830 not implemented in DAQ_Lockin')

    def set_display_x(self,  display:str):
        raise NotImplementedError('set_display_x function of SR830 not implemented in DAQ_Lockin')

    def set_display_y(self,  display:str):
        raise NotImplementedError('set_display_y function of SR830 not implemented in DAQ_Lockin')
            
    def get_display_x(self):
        raise NotImplementedError('get_display_x function of SR830 not implemented in DAQ_Lockin')
    
    def get_display_y(self):
        raise NotImplementedError('get_display_y function of SR830 not implemented in DAQ_Lockin')
    
    def buffer_shot(self,sample_rate:str,N:int,debug:bool=False):
        raise NotImplementedError('buffer_shot measurement method of SR830 not implemented in DAQ_Lockin')
    
    #========= Instrument general ==========================
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
        self.daq.close()
        if self.locked:
            self.clear()
            self.unlock()
        self.dev.close()
    