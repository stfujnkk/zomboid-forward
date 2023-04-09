from utils import (
    pack,
    unpack,
    MAX_PACKAGE_SIZE,
    PACKAGE_HEAD_SIZE,
    udp_cache,
    send_pkg,
)
import threading
import socket
import time

BUFFER_SIZE = MAX_PACKAGE_SIZE + PACKAGE_HEAD_SIZE
TIME_OUT = 3
server_addr = ('124.222.127.130', 18001)
# server_addr = ('127.0.0.1', 18001)
local_addr = ('127.0.0.1', 16261)


def main():
    tcp_pipeline = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp_pipeline.connect(server_addr)
    print(f'Successfully connected to server:{server_addr}')
    print(f'Local services to be forwarded:{local_addr}')
    distribute_data(tcp_pipeline)
    pass


def distribute_data(pipeline: socket.socket):
    buf = b''
    while True:
        data = pipeline.recv(BUFFER_SIZE)
        buf += data
        while True:
            pkg, l = unpack(buf)
            if not l:
                break

            buf = buf[l:]
            ip, port, _, payload = pkg
            print((ip, port), '>', payload)

            key = (ip, port)
            udp_client: socket.socket = udp_cache.get(key)

            if udp_client:
                # if not payload:
                #     # 关闭udp
                #     udp_client.close()
                #     udp_cache.pop(key, None)
                #     continue
                send_pkg(udp_client, pkg, addr=local_addr)
            else:
                # 开启udp
                udp_client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp_client.settimeout(TIME_OUT)
                udp_cache[key] = udp_client
                # 先发送建立连接
                send_pkg(udp_client, pkg, addr=local_addr)
                # TODO use thread pool
                threading.Thread(
                    target=forward_data,
                    args=(udp_client, ip, port, pipeline),
                    daemon=True,
                ).start()

            pass
        pass
        if not data:
            # 关闭tcp
            print('TCP connection closed')
            break
    pass


def forward_data(
    udp_client: socket.socket,
    ip: str,
    port: int,
    tcp_pipeline: socket.socket,
):
    try:
        while True:
            try:
                data, _ = udp_client.recvfrom(MAX_PACKAGE_SIZE)
                print((ip, port), '<', data)
                udp_client = udp_cache[(ip, port)]
                tcp_pipeline.sendall(pack(ip, port, data))
            except socket.timeout:
                # 检测udp是否已经关闭
                if (ip, port) not in udp_cache:
                    # TODO 通知服务端该udp客户端很可能关闭了
                    return
    finally:
        udp_cache.pop((ip, port), None)
        udp_client.close()
    pass


if __name__ == '__main__':
    th = threading.Thread(target=main, daemon=True)
    th.start()
    while th.is_alive():
        time.sleep(0.4)
    pass
