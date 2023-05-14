import logging
import hashlib
import secrets
import os
import configparser
from logging.handlers import RotatingFileHandler
from zomboid_forward.config import (
    ENCRYPTION_SIZE,
    LOG_FORMAT,
    LOG_LEVEL,
    ENCODING,
    BASE_PATH,
)


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
        handlers.append(RotatingFileHandler(
            maxBytes=1024 * 1024,
            backupCount=8,
            filename=log_file,
            encoding=ENCODING,
        ))
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
    config.read(config_path, encoding=ENCODING)
    conf = {s: dict(config.items(s)) for s in config.sections()}

    if 'log_file' in conf['common']:
        conf['common']['log_file'] = get_absolute_path(
            conf['common']['log_file'],
            base_path,
        )
    return conf
