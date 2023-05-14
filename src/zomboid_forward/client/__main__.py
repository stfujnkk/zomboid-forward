#!/usr/bin/env python
# -*- coding: utf-8 -*

from zomboid_forward.selectors.client import ZomboidForwardClient
from zomboid_forward.utils import init_log, load_config, get_absolute_path
from zomboid_forward import __version__
import os


def main(config_path, timeout: float = None, level: str = None):
    config = load_config(config_path)
    client = ZomboidForwardClient(config, timeout or 3)
    init_log(
        config['common'].get('log_file'),
        level or config['common'].get('log_level'),
    )
    client.connect()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=f'Zomboid Forward Client {__version__}')
    parser.add_argument(
        "-c",
        "--config",
        help="configuration file path",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        help="connection survival time when there is no data transmission",
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
        config_path or 'client.ini',
        timeout=args.timeout,
        level=args.level,
    )
