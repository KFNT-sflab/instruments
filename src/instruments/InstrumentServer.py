#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sat Dec 16 20:11:24 2023

@author: emil
"""

from multiprocessing.connection import Listener

import os
import threading as thr
from queue import Queue
import tempfile
import logging as log
import pyvisa as visa
import pickle

class InstrumentClientListener:
    """
    Class for establishing connections to clients and starting client handler threads.
    """
    def __init__(self, instruments, port=0, address=None, port_filename='instrument_server_port.txt'):
        if address is None:
            address = 'localhost'
        
        self.instruments = instruments
        self.port = port
        self.port_filename = os.path.join(tempfile.gettempdir(), port_filename)
        
        self.address = (address, self.port)
        self.handlers = {} # running handlers
        self.end_event = thr.Event() # for signaling running handlers
        self.handler_id = 0 # id of the next handler
        self.finished_handlers = Queue() # handler threads which should be joined            
    def start(self):
        """
        Opens the listener and saves the port number to a temporary file. Connections
        are accepted by the blocking accept() method.

        """
        self.listener = Listener(self.address)
        self.address = self.listener.address
        if self.port == 0: #port 0 means that the port was assigned automatically by the OS
            self.port = self.listener.address[1] #save the actual port
        with open(self.port_filename, 'w') as port_file:
            port_file.write(f"{self.port}\n")
            port_file.write(f"{self.address[0]}\n")
        
    def accept(self):
        """
        Accepts a connection and starts its handler in a separate thread.

        """
        conn = self.listener.accept()
        log.info(f"Accepted {self.listener.last_accepted}")
        handler_name = f"handler {self.handler_id}"
        c = InstrumentClientHandler(conn, self.end_event, name=handler_name,
                                    finished=self.finished_handlers, 
                                    visa_instruments=self.instruments)
        self.handlers[handler_name] = c
        self.handlers[handler_name].start()
        self.handler_id += 1
    
    def join_finished_handlers(self):
        while not self.finished_handlers.empty():
            name = self.finished_handlers.get()
            log.info(f"Joining {name}")
            self.handlers.pop(name).join()
    
    def close_server(self):
        log.info("Joining remaining handlers.")
        self.end_event.set()
        for c in self.handlers.values():
            c.join()
        log.info(f"Removing {self.port_filename}")
        os.remove(self.port_filename)
        log.info("Instrument server shutting down.")
    
    def loop(self):
        while True:
            self.accept() #blocking
            self.join_finished_handlers()
    
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_value, traceback):
        self.close_server()
        if exc_type is None:
            return True
        else: #propagate whatever exception happened
            return False

class RefCountedInstrument:
    "Simple wrapper for VISA resources that counts how many clients are open to it."
    def __init__(self, dev):
        self.dev = dev
        self.ref_counter = 1
    def inc(self):
        self.ref_counter += 1
    def refclose(self):
        self.ref_counter -= 1
        if self.ref_counter == 0:
            self.dev.close()
        return self.ref_counter

class VISAInstruments:
    "Manager for all VISA communications, to be shared by all client handlers"
    def __init__(self):
        self.global_visa_lock = thr.Lock()
        self.instruments = {}
        self.rm = visa.ResourceManager()
    
    def open_instrument(self, addr, conf=None):
        if addr not in self.instruments:
            log.info(f"Opening new instrument at {addr}")
            self.instruments[addr] = RefCountedInstrument(self.rm.open_resource(addr))
        else:
            self.instruments[addr].inc()
            log.info(f"Using already opened instrument at {addr}")
        
        if conf is not None:
            self.configure_instrument(addr, conf)
    
    def close_instrument(self, addr):
        count = self.instruments[addr].refclose()
        if count == 0:
            self.instruments.pop(addr)
        
    
    def configure_instrument(self, addr: str, conf: dict) -> str:
        """
        Configure an already opened instruments

        Parameters
        ----------
        addr : string
            The address of the instrument.
        conf : dict
            Dictionary of configuration options. The keys should be the attributes
            of the pyvisa resource that are meant to bet set

        Returns
        -------
        None.

        """
        for attr in conf:
            setattr(self.instruments[addr].dev, attr, conf[attr])
        
    def write(self, addr: str, msg: str):
        with self.global_visa_lock:
            self.instruments[addr].dev.write(msg)
    
    def read(self, addr: str) -> str:
        with self.global_visa_lock:
            resp = self.instruments[addr].dev.read()
        return resp
    
    def query(self, addr:str, msg: str) -> str:
        with self.global_visa_lock:
            resp =  self.instruments[addr].dev.query(msg)
        return resp
    
    def close(self):
        for inst in self.instruments.values():
            inst.dev.close()
        self.rm.close()
    
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_value, exc_bt):
        self.close()
        if exc_type is None:
            return True
        else:
            return False

class InstrumentClientHandler(thr.Thread):
    def __init__(self, conn, end_event, name, finished, visa_instruments):
        super().__init__()
        self.conn = conn
        self.end_event = end_event
        self.name = name
        self.finished = finished
        self.visa_instruments = visa_instruments
    
    @staticmethod
    def parse_msg(msg):
        toks = msg.split(' ')
        task = toks[0].upper()
        addr = toks[1]
        if len(toks) > 2:
            cmd = ' '.join(toks[2:])
        else:
            cmd = ''
        return task, addr, cmd
    
    def run(self):
        try:
            while True:
                log.debug(f"{self.name} waiting for message")
                msg = self.conn.recv()
                task, addr, cmd = self.parse_msg(msg)
                log.debug(f"{self.name} recv'd: task={task}, addr={addr}, cmd={cmd}")
                try:
                    match task:
                        case "OPEN":
                            self.visa_instruments.open_instrument(addr)
                            reply = "OPEN OK"
                        case "CONF":
                            conf = pickle.loads(bytes.fromhex(cmd))
                            self.visa_instruments.configure_instrument(addr, conf)
                            reply = "CONF OK"
                        case "WRITE":
                            self.visa_instruments.write(addr, cmd)
                            reply = "WRITE OK"
                        case "READ":
                            resp = self.visa_instruments.read(addr)
                            reply = f"READ {resp}"
                        case "QUERY":
                            resp = self.visa_instruments.query(addr, cmd)
                            reply = f"READ {resp}"
                        case "CLOSE":
                            self.visa_instruments.close_instrument(addr)
                            reply = "CLOSE OK"
                        case _:
                            raise ValueError(f"Unknown task {task}")
                except Exception as e:
                    log.debug(f"{self.name} Error {e}")
                    reply = f"ERROR {type(e)} {e}"
                self.conn.send(reply)
        except EOFError:
            pass
        except:
            log.error(f"problem with {self.name}")
            raise
        finally:
            log.info(f"quitting {self.name}")
            self.conn.close()
            self.finished.put(self.name)

if __name__ == '__main__':
    log.basicConfig(filename="instrument_server_log.txt",
                    format="%(asctime)s %(levelname)s:%(message)s",
                    level=log.INFO)
    with (VISAInstruments() as instruments, 
          InstrumentClientListener(instruments, address='') as server
          ):
        server.start()
        server.loop()
    
