from collections import deque
import socket
import abc
import struct
from typing import TypeVar, Generic, Tuple, Dict, List
import selectors
from enum import IntEnum

BUFFER_SIZE = 4096
MAX_PACKAGE_SIZE = BUFFER_SIZE


class PortType(IntEnum):
    UDP = 1
    TCP = 2


def pack_addr(addr: 'socket._RetAddress'):
    return socket.inet_aton(addr[0]) + struct.pack('!H', addr[1])


def unpack_addr(data: bytes) -> 'socket._RetAddress':
    return socket.inet_ntoa(data[:4]), struct.unpack('!H', data[4:])[0]


def pack(data: bytes):
    pkg = b''
    for i in range(0, len(data) + 1, MAX_PACKAGE_SIZE):
        chunk = data[i:i + MAX_PACKAGE_SIZE]
        pkg += (struct.pack('!H', len(chunk)) + chunk)
    return pkg


def unpack(data: bytes) -> Tuple[bytes, int, bool]:
    data_len = len(data)
    if data_len < 2:
        return b'', 0, False
    pkg_len = struct.unpack('!H', data[:2])[0]
    if data_len < 2 + pkg_len:
        return b'', 0, False
    return data[2:2 + pkg_len], 2 + pkg_len, pkg_len != MAX_PACKAGE_SIZE


def init_tcp_keep_alive_opt(sock: socket.socket):
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    # 35s~305s
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 35)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 30)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 10)
    pass


class Endpoint(abc.ABC):

    def __init__(self, sock: socket.socket, selector: 'selectors.BaseSelector', **kwargs) -> None:
        self.buffer = deque()
        self._sock = sock
        self._selector = selector
        self._state = 0
        self._closed = False
        # self._read_closed = False

    @abc.abstractmethod
    def notify_read(self) -> None:
        """
        Notify endpoint of `read` event.
        """
        ...

    @abc.abstractmethod
    def notify_write(self) -> None:
        """
        Notify endpoint of `write` event.
        """
        ...

    def close(self) -> None:
        """
        Close endpoint related resources.
        """
        if self._closed:
            return
        self._closed = True
        self._selector.unregister(self._sock)
        self._sock.close()

    pass


TS = TypeVar("TS", bound='ServerEndpoint')


class ClientEndpoint(Endpoint, Generic[TS]):

    def __init__(self, server: TS, sock: 'socket.socket', addr: 'socket._RetAddress', **kwargs) -> None:
        super().__init__(sock=sock, selector=server._selector, **kwargs)
        self._server = server
        self._addr = addr

    pass


class ServerEndpoint(Endpoint):

    def __init__(self, selector: 'selectors.BaseSelector', port: int, host: str = '0.0.0.0', **kwargs) -> None:
        self.server_addr = (host, port)
        self._clients: Dict['socket._RetAddress', 'ClientEndpoint'] = {}
        super().__init__(sock=self._init_sock(), selector=selector, **kwargs)

    def _init_sock(self) -> socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setblocking(False)
        sock.bind(self.server_addr)
        sock.listen()
        return sock

    def notify_write(self) -> None:
        raise NotImplementedError()

    def close(self) -> None:
        clients = set(self._clients.values())
        for client in clients:
            client.close()
        super().close()

    def register_client(self, client: 'ClientEndpoint'):
        self._clients[client._addr] = client

    def unregister_client(self, addr: 'socket._RetAddress'):
        self._clients.pop(addr, None)

    pass


class SteppingReceiverMixin(Endpoint):

    def __init__(self, sock: socket.socket, selector: 'selectors.BaseSelector', **kwargs) -> None:
        super().__init__(sock=sock, selector=selector, **kwargs)
        self._stepping_receiver = self._create_receiver()

    def _unpack_for_receive(self, data: bytes) -> Tuple[bytes, int, bool]:
        return data, len(data), True

    def _create_receiver(self):
        pkg_buf, data_buf = b'', b''
        while True:
            # [WinError 10054]
            data = self._sock.recv(BUFFER_SIZE)
            if not data:
                break
            pkgs: List[bytes] = []
            data_buf += data
            while True:
                pkg, length, is_finish = self._unpack_for_receive(data_buf)
                if length == 0:
                    break
                pkg_buf += pkg
                data_buf = data_buf[length:]
                if is_finish:
                    pkgs.append(pkg_buf)
                    pkg_buf = b''
            yield pkgs


class SteppingSenderMixin(Endpoint):

    def __init__(self, sock: socket.socket, selector: 'selectors.BaseSelector', **kwargs) -> None:
        super().__init__(sock=sock, selector=selector, **kwargs)
        self._stepping_sender = self._create_sender()

    def _pack_for_send(self, data):
        return data

    def _create_sender(self):
        while True:
            try:
                data = self.buffer.popleft()
                data = self._pack_for_send(data)
                while data:
                    sended_len = self._send_to(data)
                    data = data[sended_len:]
                    yield
            except IndexError:
                yield

    def _send_to(self, data):
        return self._sock.send(data)
