#!/usr/bin/env python
# -*- coding: utf-8 -*

from zomboid_forward.selectors.server import ZomboidForwardServer
from zomboid_forward.utils import init_log, load_config, get_absolute_path
from zomboid_forward import __version__
import os


def main(config_path, level: str = None):
    config = load_config(config_path)
    server = ZomboidForwardServer(config)
    init_log(
        config['common'].get('log_file'),
        level or config['common'].get('log_level'),
    )
    server.serve_forever()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=f'Zomboid Forward Server {__version__}')
    parser.add_argument(
        "-c",
        "--config",
        help="configuration file path",
    )
    parser.add_argument(
        "-l",
        "--level",
        help="log level",
    )
    args = parser.parse_args()
    config_path = args.config
    if config_path:
        config_path = get_absolute_path(config_path, os.getcwd())
    main(
        config_path or 'server.ini',
        level=args.level,
    )
