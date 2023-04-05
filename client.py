#!/usr/bin/env python
# -*- coding: utf-8 -*

from udp_forward import Pipeline
import threading, time
import logging
import configparser

log = logging.getLogger()
conf = configparser.ConfigParser()
log = logging.getLogger()
conf.read('forward.ini')

if __name__ == '__main__':
    pp = Pipeline(0, 0)

    port = int(conf['client']['port'])
    transit_port = int(conf['server']['transit_port'])
    host = conf['server']['host']

    pp.end_point1.addr = ('127.0.0.1', port)
    pp.end_point2.addr = (host, transit_port)
    pp.end_point2.sock.sendto(b'hello', pp.end_point2.addr)

    t = threading.Thread(target=pp.run, daemon=True)
    log.info('Client started successfully')
    t.start()
    while t.is_alive():
        time.sleep(0.4)
        pass