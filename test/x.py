import socket
import time

server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
server.bind(('0.0.0.0', 12314))


def main():
    data, addr = server.recvfrom(1024)
    print(data)
    time.sleep(4)
    server.sendto(b'yyyy', addr)
    try:
        data, addr = server.recvfrom(1024)
        print(addr)
    except:
        print('NO')
        pass


main()