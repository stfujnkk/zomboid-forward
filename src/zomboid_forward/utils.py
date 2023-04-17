import struct
import socket
import typing
import logging
import hashlib
import secrets
import os
import configparser
from logging.handlers import RotatingFileHandler
from zomboid_forward.config import (
    ENCRYPTION_SIZE,
    IP_HEAD_SIZE,
    PACKAGE_HEAD_SIZE,
    LENGTH_HEAD_SIZE,
    ADDR_SIZE,
    BUFFER_SIZE,
    Addr,
    PKG,
    LOG_FORMAT,
    LOG_LEVEL,
    ENCODEING,
    BASE_PATH,
)


def pack(src: Addr, dst: Addr, data: bytes):
    # yapf: disable
    return pack_addr(src) + pack_addr(dst) + struct.pack('!H', len(data)) + data
    # yapf: enable


def pack_addr(addr: Addr):
    return socket.inet_aton(addr[0]) + struct.pack('!H', addr[1])


def unpack_addr(data: bytes) -> Addr:
    # yapf: disable
    return socket.inet_ntoa(data[:IP_HEAD_SIZE]), struct.unpack('!H', data[IP_HEAD_SIZE:])[0]
    # yapf: enable


def unpack(data: bytes) -> typing.Tuple[PKG, int]:
    if len(data) < PACKAGE_HEAD_SIZE:
        return None, 0
    length = struct.unpack(
        '!H',
        data[PACKAGE_HEAD_SIZE - LENGTH_HEAD_SIZE:PACKAGE_HEAD_SIZE],
    )[0]
    pkg_len = PACKAGE_HEAD_SIZE + length
    if len(data) < pkg_len:
        return None, 0
    return (
        unpack_addr(data[:ADDR_SIZE]),
        unpack_addr(data[ADDR_SIZE:ADDR_SIZE * 2]),
        length,
        data[PACKAGE_HEAD_SIZE:pkg_len],
    ), pkg_len


def recv_pkg(sock: socket.socket, buf: bytes = b''):
    data = 1
    while data:
        data = sock.recv(BUFFER_SIZE)
        buf += data
        pkg, l = unpack(buf)
        if l == 0:
            continue
        buf = buf[l:]
        return pkg, buf
    return None, buf


def send_pkg(sock: socket.socket, pkg: PKG, addr: Addr = None):
    if not sock:
        return
    _, dst, pkg_len, payload = pkg
    addr = addr or dst
    while pkg_len > 0:
        send_len = sock.sendto(payload, addr)
        pkg_len -= send_len
        payload = payload[send_len:]
    pass


def encrypt_token(token: bytes):
    t, f = token, secrets.token_bytes(ENCRYPTION_SIZE * 2)
    f1, f2 = f[:ENCRYPTION_SIZE], f[ENCRYPTION_SIZE:]
    t = hashlib.sha256(t + f1).digest()
    t = hashlib.sha256(t + f2).digest()
    return t, f1, f2


def decrypt_token(token: bytes, factors: bytes):
    f1, f2 = factors[:ENCRYPTION_SIZE], factors[ENCRYPTION_SIZE:]
    if len(f2) != ENCRYPTION_SIZE:
        raise ValueError('The length of the factor is incorrect')
    t = hashlib.sha256(token + f1).digest()
    t = hashlib.sha256(t + f2).digest()
    return t


def init_log(log_file: str = None, log_level: str = None):
    handlers = []
    if log_file:
        handlers.append(
            RotatingFileHandler(
                maxBytes=1024 * 1024,
                backupCount=8,
                filename=log_file,
                encoding=ENCODEING,
            ))
    else:
        handlers.append(logging.StreamHandler())
    if log_level:
        log_level = log_level.lower()
    logging.basicConfig(
        format=LOG_FORMAT,
        level=LOG_LEVEL[log_level],
        handlers=handlers,
    )


def get_absolute_path(path: str, base: str = BASE_PATH):
    if not path:
        return path
    if os.path.isabs(path):
        return path
    return os.path.realpath(os.path.join(base, path))


def load_config(filename: str):
    config_path = get_absolute_path(filename)
    if not os.path.isfile(config_path):
        raise ValueError(f'File does not exist:{config_path}')
    base_path = os.path.dirname(config_path)
    config = configparser.ConfigParser()
    config.read(config_path, encoding=ENCODEING)
    conf = {s: dict(config.items(s)) for s in config.sections()}

    if 'log_file' in config['common']:
        config['common']['log_file'] = get_absolute_path(
            config['common']['log_file'],
            base_path,
        )
    return conf