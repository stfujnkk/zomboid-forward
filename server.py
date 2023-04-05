#!/usr/bin/env python
# -*- coding: utf-8 -*

from udp_forward import Pipeline
import threading, time
import logging
import configparser

conf = configparser.ConfigParser()
log = logging.getLogger()
conf.read('forward.ini')

if __name__ == '__main__':
    transit_port = int(conf['server']['transit_port'])
    port = int(conf['server']['port'])
    pp = Pipeline(transit_port, port)
    t = threading.Thread(target=pp.run, daemon=True)
    log.info('Port forwarding service is starting')
    t.start()
    while t.is_alive():
        time.sleep(0.4)
        pass