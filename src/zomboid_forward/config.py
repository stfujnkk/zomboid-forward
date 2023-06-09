import typing
import logging
import os

LOG_LEVEL = {
    'info': logging.INFO,
    'error': logging.ERROR,
    'warn': logging.WARNING,
    'debug': logging.DEBUG,
    'critical': logging.CRITICAL,
    None: logging.INFO,
}
BASE_PATH = os.path.join(os.path.expanduser('~'), '.zomboid_forward')
ENCODING = 'UTF8'
MAX_PACKAGE_SIZE = 0x7fff
IP_HEAD_SIZE = 4
PORT_HEAD_SIZE = 2
ADDR_SIZE = IP_HEAD_SIZE + PORT_HEAD_SIZE
LENGTH_HEAD_SIZE = 2
PACKAGE_HEAD_SIZE = 2 * ADDR_SIZE + LENGTH_HEAD_SIZE
TIME_OUT = 300
LOG_FORMAT = "%(asctime)s %(levelname)7s %(thread)d --- [%(threadName)15.15s] %(pathname)s:%(lineno)s : %(message)s"
BUFFER_SIZE = MAX_PACKAGE_SIZE * 2
ENCRYPTION_SIZE = 256
EMPTY_ADDR = ('0.0.0.0', 0)
Addr = typing.Tuple[str, int]
PKG = typing.Tuple[Addr, Addr, int, bytes]
