#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Mon Jan  1 21:23:17 2024

@author: emil
"""

from multiprocessing.connection import Client
import time
import os
import tempfile
import logging as log
import pickle

class InstrumentClient:
    def __init__(self, visa_addr, remote_address='localhost', port=None, port_filename='instrument_server_port.txt'):
        self.visa_addr = visa_addr

        if port is None:
            with open(os.path.join(tempfile.gettempdir(), port_filename), 'r') as port_file:
                port = int(port_file.readline())
        self.address = (remote_address, port)
        self.connection = Client(self.address) #open conncetion to the server
        self.open() #open the instrument on the server
    
    def disconnect(self):
        "Close the connection to the server."
        self.connection.close()
    
    def send_and_recv(self, msg):
        log.debug(f'{self.visa_addr} sending {msg}')
        self.connection.send(msg)
        resp = self.connection.recv()
        log.debug(f'{self.visa_addr} recvd {resp}')
        return resp
    
    @staticmethod
    def handle_error(msg):
        toks = msg.split(' ')
        if toks[0] == 'ERROR':
            raise RuntimeError(' '.join(toks[1:]))
        else:
            raise RuntimeError(f"Unknown Error: {msg}")
    
    def open(self):
        "Open the instrument on the server."
        resp = self.send_and_recv(f"OPEN {self.visa_addr}")
        if resp != "OPEN OK":
            self.handle_error(resp)
    
    def close(self):
        resp = self.send_and_recv(f"CLOSE {self.visa_addr}")
        if resp != "CLOSE OK":
            self.handle_error(resp)
    
    def read(self):
        resp = self.send_and_recv(f'READ {self.visa_addr}')
        self.disconnect()
        toks = resp.split(' ')
        if toks[0] == 'READ':
            return ' '.join(toks[1:])
        else:
            self.handle_error(resp)            
    
    def write(self, msg):
        resp = self.send_and_recv(f'WRITE {self.visa_addr} {msg}')
        if resp != "WRITE OK":
            self.handle_error(resp)
    
    def query(self, msg):
        resp = self.send_and_recv(f'QUERY {self.visa_addr} {msg}')
        toks = resp.split(' ')
        if toks[0] == 'READ':
            return ' '.join(toks[1:])
        else:
            self.handle_error(resp)
    
    def configure(self, conf):
        """
        Configure the instrument with the options in the conf dictionary.
        The dict is serialized and sent over the socket.

        Parameters
        ----------
        conf : dict
            Configuration of the VISA resource. Keys should be the names
            of the attributes of the pyvisa Resource.

        Returns
        -------
        None.

        """
        conf_msg = f"CONF {self.visa_addr} {pickle.dumps(conf).hex()}"
        resp = self.send_and_recv(conf_msg)
        if resp != "CONF OK":
           self.handle_error(resp)
    
    def lock(self):
        #TODO
        pass
    def unlock(self):
        #TODO
        pass
    def clear(self):
        #TODO
        pass