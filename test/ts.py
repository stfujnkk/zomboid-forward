import socket
import threading, time
from utils import pack, unpack


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('127.0.0.1', 18001))
    server.listen(1)
    c, _ = server.accept()

    buf = b''

    for i in range(3):
        x = input().encode('gbk')
        data = b''
        if x.startswith(b'1'):
            data = pack('127.0.0.1', 11111, x)
        elif x.startswith(b'2'):
            data = pack('127.0.0.1', 22222, x)
        else:
            data = pack('127.0.0.1', 12778, x)
        c.sendall(data)
        #########
        data = c.recv(1024)
        buf += data
        while True:
            pkg, l = unpack(buf)
            if not l:
                break
            buf = buf[l:]
            ip, port, _, payload = pkg
            print(f'from: {ip}:{port}')
            print(payload)

        if not data:
            break
        pass


th = threading.Thread(
    target=main,
    daemon=True,
)
th.start()
while th.is_alive():
    time.sleep(0.4)
pass