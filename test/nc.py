import argparse
import socket
import time, threading

parser = argparse.ArgumentParser(description='TCP/UDP tool')
parser.add_argument(
    '-s',
    '--site',
    default='localhost',
)
parser.add_argument(
    '-l',
    '--listen',
    action='store_true',
    default=False,
)
parser.add_argument(
    '-u',
    '--udp',
    action='store_true',
    default=False,
)
parser.add_argument(
    'port',
    type=int,
)
BUFFER_SIZE = 1024


def udp_server(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.site, args.port))
    while True:
        data, addr = sock.recvfrom(BUFFER_SIZE)
        print(data)
        msg = input().encode('gbk')
        sock.sendto(msg, addr)


def tcp_server(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((args.site, args.port))
    sock.listen(1)
    while True:
        client, _ = sock.accept()

        def read():
            while True:
                data = client.recv(BUFFER_SIZE)
                if not data:
                    break
                print(data)
            pass

        def write():
            while True:
                client.sendall(input().encode('gbk'))

        th1 = threading.Thread(target=read, daemon=True)
        th2 = threading.Thread(target=write, daemon=True)
        th1.start()
        th2.start()

        while th1.is_alive() and th2.start():
            time.sleep(0.4)
        pass


def tcp_client(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((args.site, args.port))
    while True:
        msg = input().encode('gbk')
        sock.sendall(msg)
        data = sock.recv(BUFFER_SIZE)
        if not data:
            break
        print(data)


def udp_client(args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    while True:
        msg = input().encode('gbk')
        sock.sendto(msg, (args.site, args.port))
        data, _ = sock.recvfrom(BUFFER_SIZE)
        print(data)


def main(args):
    choose = 0
    if args.udp:
        choose += 1
    if args.listen:
        choose += 2
    handlers = [tcp_client, udp_client, tcp_server, udp_server]
    handler = handlers[choose]
    print(f'{handler.__name__} running...')
    handler(args)


if __name__ == '__main__':
    th = threading.Thread(
        target=main,
        daemon=True,
        args=(parser.parse_args(), ),
    )
    th.start()
    while th.is_alive():
        time.sleep(0.4)
    pass
