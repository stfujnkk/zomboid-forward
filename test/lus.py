import socket
import time
import threading

running = False
server_addr = ('0.0.0.0', 18006)


def keep_alive(server: socket.socket, addr):
    global running
    while running:
        time.sleep(0.4)
        server.sendto(b'', addr)
    pass


def receive_data(server: socket.socket):
    global running
    try:
        while running:
            data, _ = server.recvfrom(1024)
            print(data.decode('gbk'))
    finally:
        running = False
        server.close()
        pass
    pass


def main():
    global running
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(server_addr)
    data, addr = server.recvfrom(1024)
    print(addr)
    running = True
    print(data.decode('gbk'))
    server.sendto(b'hi', addr)

    # th1 = threading.Thread(target=keep_alive, args=(server, addr), daemon=True)
    # th1.start()

    th2 = threading.Thread(target=receive_data, args=(server, ), daemon=True)
    th2.start()

    while running:
        msg = input()
        server.sendto(msg.encode('gbk'), addr)

    pass


if __name__ == '__main__':
    th = threading.Thread(target=main, daemon=True)
    th.start()
    while th.is_alive():
        time.sleep(0.4)