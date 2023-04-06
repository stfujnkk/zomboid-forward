#!/usr/bin/env python
# -*- coding: utf-8 -*

from udp_forward import Pipeline
import threading
import time
import logging


def main(conf, log: logging.Logger, stop_event=None):
    port = int(conf['client']['port'])
    transit_port = int(conf['server']['transit_port'])
    host = conf['server']['host']

    pp = Pipeline(0, 0)
    if stop_event:
        pp.stop_event = stop_event
    Pipeline.log = log

    pp.end_point1.addr = ('127.0.0.1', port)
    pp.end_point2.addr = (host, transit_port)

    pp.end_point2.sock.sendto(Pipeline.EMPTY_DATA, pp.end_point2.addr)

    t = threading.Thread(target=pp.run, daemon=True)
    log.info(f'Client started successfully')
    t.start()
    while t.is_alive():
        time.sleep(0.4)
        pass


if __name__ == '__main__':
    import os
    import configparser
    import sys
    os.chdir(os.path.dirname(__file__))
    conf = configparser.ConfigParser()
    conf_path = 'forward.ini'
    if len(sys.argv) == 2:
        conf_path = sys.argv[1]
    conf.read(conf_path)
    logging.basicConfig(level=logging.DEBUG)
    main(conf, logging.getLogger())
