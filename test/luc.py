import socket
import time
import threading

server_addr = ('127.0.0.1', 18007)
# server_addr = ('124.222.127.130', 18006)


def receive_data(server: socket.socket):
    while True:
        data, _ = server.recvfrom(1024)
        print(data.decode('gbk'))
    pass


def main():
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    client.sendto(b'hello', server_addr)
    th = threading.Thread(target=receive_data, args=(client, ), daemon=True)
    th.start()
    while True:
        msg = input()
        client.sendto(msg.encode('gbk'), server_addr)


if __name__ == '__main__':
    th = threading.Thread(target=main, daemon=True)
    th.start()
    while th.is_alive():
        time.sleep(0.4)
''' 
在python中使用udp socket时报如下错误时，如何获取对应错误的客户端网络地址。 ConnectionResetError: [WinError 10054]

使用'socket'的'recvfrom'方法报如下错误时，如何获取客户端的'_RetAddress'。
ConnectionResetError: [WinError 10054]

How to obtain the _RetAddress from udp client in python when using the recvfrom method of socket, the following error is reported.
ConnectionResetError: [WinError 10054]

'''
