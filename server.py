#!/usr/bin/env python
# -*- coding: utf-8 -*

from udp_forward import Pipeline, three_messages_handshake
import threading
import time
import logging


def main(conf, log):
    transit_port = int(conf['server']['transit_port'])
    port = int(conf['server']['port'])

    client = three_messages_handshake('0.0.0.0', transit_port, True, 6, log)

    pp = Pipeline(transit_port, port)
    pp.end_point1.addr = client
    Pipeline.log = log
    t = threading.Thread(target=pp.run, daemon=True)
    log.info('Port forwarding service is starting')
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
    main(conf, logging.getLogger())
