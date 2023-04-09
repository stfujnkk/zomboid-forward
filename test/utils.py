import struct
import socket
import logging
from cachetools import LRUCache
import typing

log = logging.getLogger()
Addr = typing.Tuple[str, int]
MAX_PACKAGE_SIZE = 65535
IP_HEAD_SIZE = 4
PORT_HEAD_SIZE = 2
LENGTH_HEAD_SIZE = 2
PACKAGE_HEAD_SIZE = IP_HEAD_SIZE + PORT_HEAD_SIZE + LENGTH_HEAD_SIZE
MAX_UDP_CONNECTION = 64


def pack(ip: str, port: int, data: bytes):
    IP32Bit = socket.inet_aton(ip)
    return IP32Bit + struct.pack('!HH', port, len(data)) + data


def unpack(data: bytes):
    if len(data) < PACKAGE_HEAD_SIZE:
        return None, 0
    port, length = struct.unpack(
        '!HH',
        data[IP_HEAD_SIZE:IP_HEAD_SIZE + PORT_HEAD_SIZE + LENGTH_HEAD_SIZE])
    if len(data) < PACKAGE_HEAD_SIZE + length:
        return None, 0
    ip = socket.inet_ntoa(data[:IP_HEAD_SIZE])
    return (
        ip,
        port,
        length,
        data[PACKAGE_HEAD_SIZE:PACKAGE_HEAD_SIZE + length],
    ), PACKAGE_HEAD_SIZE + length


# TODO 多线程并发问题
udp_cache = LRUCache(maxsize=MAX_UDP_CONNECTION)


def send_pkg(sock: socket.socket, pkg: tuple, addr: Addr = None):
    if not sock:
        return
    ip, port, pkg_len, payload = pkg
    if not addr:
        addr = (ip, port)
    while pkg_len > 0:
        send_len = sock.sendto(payload, addr)
        pkg_len -= send_len
        payload = payload[send_len:]
    pass


# sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
# sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, True)
# sock.ioctl(socket.SIO_KEEPALIVE_VALS, (1, 60 * 1000, 30 * 1000))
