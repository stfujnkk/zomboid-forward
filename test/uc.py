import socket
import threading, time

ENCODING = 'gbk'

tokens = [b'Connection Request', b'Server allowed', b'Client normal']


class UdpClient:

    def __init__(self, port: int, ip: str = '127.0.0.1'):
        self.addr = (ip, port)
        self.client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        pass

    def read(self):
        while True:
            data, _ = self.client.recvfrom(1024)
            msg = data.decode(ENCODING)
            if msg:
                print(f'\n>>> {msg}\n')
        pass

    def run(self):
        status = 0
        print(f'Try to connect to {self.addr}...')

        while status < len(tokens):
            if status % 2 == 0:
                self.client.sendto(tokens[status], self.addr)
                status += 1
            else:
                data, _ = self.client.recvfrom(1024)
                if data != tokens[status]:
                    print('connection failed')
                    return
                status += 1
                pass
            pass

        print('Successfully connected\n')

        th = threading.Thread(target=self.read, daemon=True)
        th.start()

        while th.is_alive():
            msg = input().encode(ENCODING)
            self.client.sendto(msg, self.addr)
        pass


if __name__ == '__main__':
    # client = UdpClient(18003, '124.222.127.130')
    client = UdpClient(16261)
    client.run()