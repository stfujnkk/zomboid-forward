#!/usr/bin/env python
# -*- coding: utf-8 -*

import socket
import threading, time
import weakref
from utils import (
    MAX_PACKAGE_SIZE,
    pack,
    unpack,
    PACKAGE_HEAD_SIZE,
    send_pkg,
)
import traceback

server_addr = ('0.0.0.0', 18003)
transit_addr = ('0.0.0.0', 18001)

BUFFER_SIZE = MAX_PACKAGE_SIZE + PACKAGE_HEAD_SIZE

shutdown_infos = weakref.WeakKeyDictionary()
TCP_CLOSED = 1


def push_data(pipeline: socket.socket, udp_server: socket.socket):
    global shutdown_infos
    try:
        while True:
            try:
                data, addr = udp_server.recvfrom(MAX_PACKAGE_SIZE)
                ip, port = addr
                print((ip, port), '>', data)
                pipeline.sendall(pack(ip, port, data))
            except Exception:
                info = shutdown_infos.get(udp_server)
                if info and info['code'] == TCP_CLOSED:
                    print(info['reason'])
                    return
                # 其他错误可能是udp客户端关闭了，不予处理
                # TODO 查出是哪个udp客户端关闭
                pass
    finally:
        pipeline.close()
        udp_server.close()
        pass


def run_transit_server(transit_server: socket.socket):
    transit_client, server = None, None
    try:
        # 连接tcp客户端
        transit_client, addr = transit_server.accept()
        print(f'Successfully connected to client:{addr}')
        # 开启udp
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.settimeout(3)
        server.bind(server_addr)

        threading.Thread(
            target=push_data,
            args=(transit_client, server),
            daemon=True,
        ).start()
        # TODO udp心跳机制

        buf = b''
        while True:
            data = transit_client.recv(BUFFER_SIZE)
            buf += data
            while True:
                pkg, l = unpack(buf)
                if not l:
                    break
                buf = buf[l:]
                ip, port, _, payload = pkg
                print((ip, port), '<', payload)
                send_pkg(server, pkg)
                pass
            if not data:
                # 关闭tcp
                shutdown_infos[server] = {
                    'code': TCP_CLOSED,
                    'reason': f'The client closed the connection:{addr}',
                }
                break
    except Exception as e:
        # 关闭tcp
        shutdown_infos[server] = {
            'code': TCP_CLOSED,
            'reason': e,
        }
    finally:
        if transit_client:
            transit_client.close()
        if server:
            server.close()
    pass


def main():
    global shutdown_infos

    print('Waiting for client connection...')
    print(f'Data transmission address:{transit_addr}')
    print(f'Expose address to the public:{server_addr}\n')
    # 开启tcp服务
    transit_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    transit_server.bind(transit_addr)
    transit_server.listen(1)
    while True:
        run_transit_server(transit_server)


if __name__ == '__main__':
    th = threading.Thread(
        target=main,
        daemon=True,
    )
    th.start()
    while th.is_alive():
        time.sleep(0.4)
    pass
