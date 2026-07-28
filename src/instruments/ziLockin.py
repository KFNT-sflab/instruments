#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jul  8 16:10:54 2019

@author: emil
"""

import numpy as np
import time
import zhinst.utils

def best_range(amp, possible_ranges = [0.01, 0.1, 1.0, 10.0]):
    for r in possible_ranges:
        if amp <= r:
            return r
    raise ValueError('Amplitude {} is outside max range of 10 V'.format(amp))
    
scan_sequential = 0
scan_binary = 1
scan_bidirectional = 2
scan_reverse = 3

class ziLockin():
    def __init__(self, devid, apilevel=6):
        self.devid = devid
        
        err_msg = "This program only supports instruments with demodulators."
        (daq, device, props) = zhinst.utils.create_api_session(devid, apilevel,
                                                               required_devtype='.*LI|.*IA|.*IS',
                                                               required_err_msg=err_msg)
        zhinst.utils.api_server_version_check(daq)
        
        self.daq = daq
        self.device = device
        self.props = props
        self.disable_everything()
    
    def dspath(self, demod):
        """
        Returns a path to the samples for a given demodulator id **demod**. Useful for
        taking out data from the sweeper results.
        """
        return '/{}/demods/{}/sample'.format(self.device, demod)
    
    def add_output(self, output, addstate):
        self.daq.set([['/{}/sigouts/{}/add'.format(self.device, output), 1 if addstate else 0]])
    
    def get_clockbase(self):
        return float(self.daq.getInt(f"/{self.devid}/clockbase"))
    
    def disable_everything(self):
        zhinst.utils.disable_everything(self.daq, self.device)
    
    def sync(self):
        self.daq.sync()
    
    def configure_input(self, input_id, input_range, ac_coupling=True, imp50 = False,
                        differential=False):
        input_settings = [
                ['/%s/sigins/%d/range' % (self.device, input_id), input_range],
                ['/%s/sigins/%d/ac'    % (self.device, input_id), 1 if ac_coupling else 0],
                ['/%s/sigins/%d/imp50' % (self.device, input_id), 1 if imp50 else 0],
                ['/%s/sigins/%d/diff'  % (self.device, input_id), 1 if differential else 0]]
        self.daq.set(input_settings);
    
    def configure_oscillator(self, osc_id, freq):
        osc_settings = [
                ['/{}/oscs/{}/freq'.format(self.device, osc_id), freq]]
        self.daq.set(osc_settings)
        self.daq.sync()
        
    def configure_demodulator(self, demod_id, rate, input_channel, filter_order,
                              tc, osc, harm=1, sinc=False, sync=True):
        """
        Configures and enables the demodulator.
        
        Parameters:
        -----------
        **demod_id** : Demodulator id, 0 -- 5
        
        **rate** : transfer rate, Hz
    
        **input_channel** : input channel to the demodulator
        
        **filter_order** : Low-pass filter order. 0 -- 7 (roll of 6(n+1) dB/oct)
        
        **tc** : Time constant, in seconds.
        
        **osc** : Oscillator to use for this demodulator.
        
        **harm** : Which harmonic to use.
        
        **sinc** : Enable the Sinc filter
        """
        demod_settings = [
                ['/%s/demods/%d/enable'         % (self.device, demod_id), 1],
                ['/%s/demods/%d/rate'           % (self.device, demod_id), rate],
                ['/%s/demods/%d/adcselect'      % (self.device, demod_id), input_channel],
                ['/%s/demods/%d/order'          % (self.device, demod_id), filter_order],
                ['/%s/demods/%d/timeconstant'   % (self.device, demod_id), tc],
                ['/%s/demods/%d/oscselect'      % (self.device, demod_id), osc],
                ['/%s/demods/%d/harmonic'       % (self.device, demod_id), harm],
                ['/%s/demods/%d/sinc'           % (self.device, demod_id), 1 if sinc else 0]]
        self.daq.set(demod_settings)
        if sync:
            self.daq.sync()
            
    def configure_plls(self, pll_id, input_channel, sync=True):
        """
        Configures the PLLs (demodulators 7 and 8).
        
        Parameters:
        -----------
        **demod_id** : Demodulator id, 6 or 7 (indexing from 0 -- 7 or 8 in LabOne)
        
        **input_channel** : input channel to the demodulator
        
        **osc** : Oscillator to use for this demodulator.
        """
        demod_settings = [
                ['/%s/plls/%d/adcselect'      % (self.device, pll_id), input_channel]]
        self.daq.set(demod_settings)
        if sync:
            self.daq.sync()
    
    def configure_output(self, output_id, demod_id, amplitude, enable=True):
        range_path = '/{}/sigouts/{}/range'.format(self.device, output_id)
        rng = self.daq.get(range_path, flat=True)[range_path][0]
        output_settings = [
                ['/%s/sigouts/%d/enables/%d'     % (self.device, output_id, demod_id), 1 if enable else 0],
                ['/%s/sigouts/%d/amplitudes/%d' % (self.device, output_id, demod_id), amplitude/rng]]
        # print(output_settings)
        self.daq.set(output_settings)
        self.daq.sync()
    
    def output(self, output_id, output_on=None, output_range=None, offset=None):
        output_settings = []
        if output_on is not None:
            output_settings.append(['/%s/sigouts/%d/on'  % (self.device, output_id), 1 if output_on else 0])
        if offset is not None:
            output_settings.append(['/%s/sigouts/%d/offset' % (self.device, output_id), offset])
        if output_range is not None:
            output_settings.append(['/%s/sigouts/%d/range'  % (self.device, output_id), output_range])
        #print(output_settings)
        self.daq.set(output_settings)
        self.daq.sync()
        
    def configure_sweeper(self, demods, auto_bw = False, 
                          settling_time = 0, settling_inaccuracy = 1e-3,
                          avg_samples = 1, avg_tc = 0,
                          scan = 0, sinc_filter = False):
        sweeper = self.daq.sweep()
        
        sweeper.set('sweep/device', self.device)
        
        #configure settling
        sweeper.set('sweep/settling/time', settling_time)
        sweeper.set('sweep/settling/inaccuracy', settling_inaccuracy)
        
        #configure averaging
        sweeper.set('sweep/averaging/sample', avg_samples)
        sweeper.set('sweep/averaging/tc', avg_tc)
        
        #set scan
        sweeper.set('sweep/scan', scan)
        
        #bandwidth settings are either auto or left unchanged
        #I don't see the point in re-implementing configuration of
        #demodulators here
        if auto_bw:
            sweeper.set('sweep/bandwidthcontrol', 2)
        else:
            sweeper.set('sweep/bandwidthcontrol', 0)
        
        if sinc_filter:
            sweeper.set('sweep/sincfilter', 1)
        else:
            sweeper.set('sweep/sincfilter', 0)
            
        #subscribe to demodulators
        paths = ['/{}/demods/{}/sample'.format(self.device, demod) for demod in demods]
        for path in paths:
           # print("Sweeper:subscribing to " + path)
            sweeper.subscribe(path)
        self.sweeper_subscribed_paths = paths
        
        return sweeper
    
    def freq_sweep(self, fi, ff, samples, A, osc, output_id, output_ch,
                   demods, auto_bw = False,
                   settling_time = 0, settling_inaccuracy = 1e-4,
                   avg_samples = 1, avg_tc = 0,
                   scan = 0, sinc_filter = False,
                   timeout = 600, verbose=False):
        """
        Sweeps the frequency from **fi** to **ff** on oscillator **osc**. Steps through
        **samples** points and the output amplitude is **A** (Volts).
        
        Reads the data from **demods** (should be a list). The demodulators should be
        configured beforehand using ziLockin.configure_demodulator.
        
        For other parameters see manual.
        """
        
        sweeper = self.configure_sweeper(demods, auto_bw,
                                         settling_time, settling_inaccuracy,
                                         avg_samples, avg_tc,
                                         scan, sinc_filter)
        
        #configure the sweep
        sweeper.set('sweep/gridnode', 'oscs/{}/freq'.format(osc))
        sweeper.set('sweep/start', fi)
        sweeper.set('sweep/stop', ff)
        sweeper.set('sweep/samplecount', samples)
        
        #configure the excitation
        if A < 1e-6: #1 uV is the minimum output, just turn the output of completely for smaller values
            self.output(output_id, output_on=False)
        else:
            rng = best_range(A)
            self.output(output_id, output_range=rng, output_on=False)
            time.sleep(1)
            self.configure_output(output_id, output_ch, A/rng, enable=True)
            time.sleep(1)
            self.output(output_id, output_on=True)
        
        #start measuring
        start = time.time()
        sweeper.execute()
        while not sweeper.finished():
            time.sleep(0.2)
            
            if verbose:
                prog = sweeper.progress()
                print("Sweeper progress: {:.0f}%".format(100*prog[0]), end='\r')
            
            now = time.time()
            if now - start > timeout:
                sweeper.finish()
                raise RuntimeError("Frequency sweeper timed out.") 
        
        self.output(output_id, output_on = False)
        data = sweeper.read(True)
        for path in self.sweeper_subscribed_paths:
            sweeper.unsubscribe(path)
        self.sweeper_subscribed_paths = []
        sweeper.clear()
        
        return data

    def amp_sweep(self, Ai, Af, samples, f0, osc, output_id, output_ch,
                   demods, auto_bw = False,
                   settling_time = 0, settling_inaccuracy = 1e-4,
                   avg_samples = 1, avg_tc = 0,
                   scan = 0, sinc_filter = False,
                   timeout = 600, verbose=False,
                   dont_change_output_state = False,
                   ramp_up = True,
                   ramp_down = True):
        """
        Sweeps the amplitude from **Ai** to **Af** (Volts) on oscillator **osc**. Steps through
        **samples** points and the frequency is **f** (Hz).
        
        Reads the data from **demods** (should be a list). The demodulators should be
        configured beforehand using ziLockin.configure_demodulator.
        
        For other parameters see manual.
        """
        
        sweeper = self.configure_sweeper(demods, auto_bw,
                                         settling_time, settling_inaccuracy,
                                         avg_samples, avg_tc,
                                         scan, sinc_filter)
        
        #configure the excitation
        self.confgure_oscillator(osc,f0)
        rng = best_range(max(Ai,Af))
        if not dont_change_output_state:
            self.output(output_id, output_on = False)
            time.sleep(1)
        self.output(output_id, output_range = rng)
        time.sleep(1)
        self.configure_output(output_id, output_ch, Ai/rng, enable=True)
        time.sleep(1)
        if not dont_change_output_state:
            self.output(output_id, output_on = True)
        
        #configure the sweep
        sweeper.set('sweep/gridnode', 'sigouts/{}/amplitudes/{}'.format(output_id,output_ch))
        sweeper.set('sweep/start', Ai/rng)
        sweeper.set('sweep/stop', Af/rng)
        sweeper.set('sweep/samplecount', samples)
        
        print("Sweeping ", Ai/rng, Af/rng, samples, "(range ", rng, ")")
        print(sweeper.get('sweep/*'),
              sweeper.get('sweep/stop'),
              sweeper.get('sweep/samplecount'))
        #
        # Ramp up
        #
        
        if ramp_up:
            #start measuring
            start = time.time()
            sweeper.execute()
            if verbose:
                print("Ramping up:")
            while not sweeper.finished():
                time.sleep(0.2)
                
                if verbose:
                    prog = sweeper.progress()
                    print("Sweeper progress: {:.0f}%".format(100*prog[0]), end='\r')
                
                now = time.time()
                if now - start > timeout:
                    sweeper.finish()
                    raise RuntimeError("Frequency sweeper timed out.")
    
        #
        # Ramp down
        #
        
        if ramp_down:
            sweeper.set('sweep/scan', 3) #scan in reverse
            start = time.time()
            sweeper.execute()
            if verbose:
                print("Ramping down:")
            while not sweeper.finished():
                time.sleep(0.2)
                
                if verbose:
                    prog = sweeper.progress()
                    print("Sweeper progress: {:.0f}%".format(100*prog[0]), end='\r')
                
                now = time.time()
                if now - start > timeout:
                    sweeper.finish()
                    raise RuntimeError("Frequency sweeper timed out.")
        
        #this should return both sweeps
        data = sweeper.read(True)
        
        if not dont_change_output_state:
            self.output(output_id, output_on = False)
        for path in self.sweeper_subscribed_paths:
            sweeper.unsubscribe(path)
        self.sweeper_subscribed_paths = []
        sweeper.clear()
        
        return data
    
    def daq_continuous(self, f0, tc, rate, samples, demod=0, osc=0, filter_order=4, input_channel=0):
        import time
        #def configure_demodulator(self, demod_id, rate, input_channel, filter_order,
        #                     tc, osc, harm=1, sinc=False, sync=True):
        self.configure_oscillator(osc, f0)
        self.configure_demodulator(demod, rate=rate, input_channel=input_channel, filter_order=filter_order,
                                   tc=tc, osc=osc)
        daq_module = self.daq.dataAcquisitionModule()
        daq_module.set("device", self.devid)
        daq_module.set("type", 0) # continuous acquisition
        daq_module.set("grid/mode", 4) # duration is fixed by sample rate and number
        daq_module.set("count", 1) # number of bursts
        daq_module.set("grid/cols", samples)
        signal_paths = [
            f'/{self.devid}/demods/{demod}/sample.x',
            f'/{self.devid}/demods/{demod}/sample.y'
            ]
        for path in signal_paths:
            daq_module.subscribe(path)

        time.sleep(1)
        daq_module.execute()
        data = {path: [] for path in signal_paths}
        while not daq_module.finished():
            pdata = daq_module.read(True)
            for path in signal_paths:
                if path in pdata.keys():
                    data[path].append(pdata[path][0]['value'][0])

        pdata = daq_module.read(True)
        for path in signal_paths:
            if path in pdata.keys():
                data[path].append(pdata[path][0]['value'][0])
        daq_module.unsubscribe(f'/{self.devid}/demods/{demod}/sample.x')
        daq_module.unsubscribe(f'/{self.devid}/demods/{demod}/sample.y')
        data['x'] = np.hstack(data[signal_paths[0]])
        data['y'] = np.hstack(data[signal_paths[1]])
        data['_f0'] = f0
        data['_tc'] = tc
        data['_rate'] = float(self.daq.getInt(f'/{self.devid}/demods/{demod}/rate'))
        data['_samples'] = samples
        data['_filter_order'] = filter_order
        return data
        
    
if __name__ == '__main__':
    import matplotlib.pyplot as plt
    import numpy.fft as fft
    plt.close('all')
    lockin = ziLockin('dev538')
    fftmean = 0
    for k in range(1):
        data = lockin.daq_continuous(f0=57.42e3, tc=1e-4, rate=5e3, samples=16384)
        x = data['x']
        y = data['y']
        s = x + 1j*y
        
        ffts = fft.fft(s)
        ffts = fft.fftshift(ffts)
        fftmean += ffts
    
    fig, ax = plt.subplots(1,1)
    ax.plot(np.abs(fftmean))