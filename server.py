#!/usr/bin/env python
# -*- coding: utf-8 -*

from udp_forward import Pipeline
import threading
import time
import logging


def main(conf, log: logging.Logger):
    log.info('Port forwarding service is starting')

    transit_port = int(conf['server']['transit_port'])
    port = int(conf['server']['port'])

    pp = Pipeline(transit_port, port)
    Pipeline.log = log
    t = threading.Thread(target=pp.run, daemon=True)

    t.start()
    while t.is_alive():
        time.sleep(0.4)
        pass
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
    logging.basicConfig(level=logging.INFO)
    main(conf, logging.getLogger())
