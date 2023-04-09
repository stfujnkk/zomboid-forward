import socketserver
import socket


class MyUDPHandler(socketserver.BaseRequestHandler):
    """
    This class works similar to the TCP handler class, except that
    self.request consists of a pair of data and client socket, and since
    there is no connection the client address must be given explicitly
    when sending data back via sendto().
    """

    def handle(self):
        data: bytes = self.request[0]
        sock: socket.socket = self.request[1]
        print("{} wrote: {}".format(self.client_address[0], data))
        sock.sendto(input().encode('gbk'), self.client_address)


if __name__ == "__main__":
    HOST, PORT = "0.0.0.0", 18007
    with socketserver.ThreadingUDPServer((HOST, PORT), MyUDPHandler) as server:
        server.serve_forever()