from .libs import (
    ServerEndpoint,
    init_tcp_keep_alive_opt,
    Endpoint,
    SteppingReceiverMixin,
    SteppingSenderMixin,
    unpack_addr,
    PortType,
    pack_addr,
    BUFFER_SIZE,
    pack,
    unpack,
)
import socket
import selectors
import logging
import struct
import time
from typing import Type
import json
from zomboid_forward.utils import decrypt_token


class SteppingConnectMixin(ServerEndpoint):

    def __init__(self, selector: selectors.BaseSelector, port: int, host: str, timeout: float, **kwargs) -> None:
        super().__init__(selector, port, host, **kwargs)
        self._connected = False
        self._timeout = timeout
        self._stepping_connect = self._create_stepping_connect()
        next(self._stepping_connect)

    def _create_stepping_connect(self):
        deadline = time.time() + self._timeout
        while True:
            try:
                self._sock.connect(self.server_addr)
                self._connected = True
            except BlockingIOError:
                # [WinError 10035]
                yield False
            except OSError as e:
                # [WinError 10056]
                if e.errno == 10056:
                    self._connected = True
                else:
                    raise
            if self._connected:
                logging.info(f'Successfully connected to server {self.server_addr}')
            while self._connected:
                yield True
            if time.time() > deadline:
                raise socket.timeout()

    def _init_sock(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        init_tcp_keep_alive_opt(sock)
        sock.setblocking(False)
        return sock


class VirtualClient(ServerEndpoint):

    def __init__(
        self,
        server: 'ZomboidForwardClient',
        host: str,
        port: int,
        addr: 'socket._RetAddress',
        **kwargs,
    ) -> None:
        super().__init__(
            selector=server._selector,
            port=port,
            host=host,
            timeout=server._timeout,
            **kwargs,
        )
        self._server = server
        self._addr = addr

    def transit(self, data: bytes, addr: 'socket._RetAddress') -> None:
        port_type, port = self._server._local2remote[addr]
        head = struct.pack('!HH', port_type, port) + pack_addr(self._addr)
        self._server.buffer.append(head + data)

    def sendto_buffer(self, data: bytes, addr: 'socket._RetAddress'):
        self.buffer.append(data)

    pass


class VirtualTCPClient(VirtualClient, SteppingConnectMixin, SteppingSenderMixin):

    def notify_read(self) -> None:
        data = self._sock.recv(BUFFER_SIZE)
        self.transit(data, self.server_addr)

    def notify_write(self) -> None:
        if not next(self._stepping_connect):
            return
        next(self._stepping_sender)


class VirtualUDPClient(VirtualClient, SteppingSenderMixin):

    def notify_read(self) -> None:
        data, addr = self._sock.recvfrom(BUFFER_SIZE)
        self.transit(data, addr)

    def notify_write(self) -> None:
        next(self._stepping_sender)

    def sendto_buffer(self, data: bytes, addr: 'socket._RetAddress'):
        self.buffer.append((data, addr))

    def _send_to(self, data):
        self._latest_address = data[1]
        return self._sock.sendto(*data)

    def _init_sock(self) -> socket:
        self.server_addr = None
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        return sock


class ZomboidForwardClient(SteppingConnectMixin, SteppingReceiverMixin, SteppingSenderMixin):
    upstream: dict[PortType, Type[VirtualClient]] = {
        PortType.TCP: VirtualTCPClient,
        PortType.UDP: VirtualUDPClient,
    }

    def __init__(self, conf: dict, timeout: float) -> None:
        host = conf['common']['server_addr'].strip()
        port = int(conf['common']['server_port'])
        self._state = 0

        super().__init__(selector=selectors.DefaultSelector(), port=port, host=host, timeout=timeout)
        self._remote2local: dict[tuple[PortType, int], 'socket._RetAddress'] = {}
        self._local2remote: dict['socket._RetAddress', tuple[PortType, int]] = {}

        for k, v in conf.items():
            if k == 'common' or k == 'DEFAULT':
                continue
            local_ip = v['local_ip']

            server_type = v.get('type') or 'udp'
            port_type = PortType[server_type.upper()]

            local_ports = [int(x) for x in v['local_port'].split(',')]
            remote_ports = [int(x) for x in v['remote_port'].split(',')]

            for local_port, remote_port in zip(local_ports, remote_ports):
                self._remote2local[(port_type, remote_port)] = (local_ip, local_port)
                self._local2remote[(local_ip, local_port)] = (port_type, remote_port)

            pass

        self._token: bytes = conf['common']['token'].strip().encode()
        del conf['common']['token']
        self._conf = conf
        pass

    def notify_read(self) -> None:
        pkgs = next(self._stepping_receiver)
        if len(pkgs) == 0:
            return
        if self._state == 0:
            f = pkgs.pop(0)
            token = decrypt_token(self._token, f)
            self.buffer.append(token)
            self.buffer.append(json.dumps(self._conf).encode())
            self._state = 1

        for pkg in pkgs:
            port_type, port = struct.unpack('!HH', pkg[:4])
            remote_addr = unpack_addr(pkg[4:10])
            self._forward_to_client(port_type, remote_addr, port, pkg[10:])

    def notify_write(self) -> None:
        if not next(self._stepping_connect):
            return
        if self._state < 1:
            return
        next(self._stepping_sender)

    def connect(self):
        logging.info(f'Attempting to connect {self.server_addr}')
        self._selector.register(self._sock, selectors.EVENT_WRITE | selectors.EVENT_READ, self)
        try:
            while True:
                events = self._selector.select(0.5)
                for key, mask in events:
                    endpoint: Endpoint = key.data
                    try:
                        if mask & selectors.EVENT_READ:
                            endpoint.notify_read()
                        if mask & selectors.EVENT_WRITE:
                            endpoint.notify_write()
                    except Exception as e:
                        logging.error(endpoint._sock, exc_info=e)
                        endpoint.close()
        finally:
            self._selector.close()

    def unregister_client(self, client_id: tuple[PortType, 'socket._RetAddress']):
        port_type, remote_addr = client_id
        logging.warning(f'Close {PortType(port_type).name} connection {remote_addr}')
        self._clients[client_id].close()
        del self._clients[client_id]

    def _forward_to_client(self, port_type: PortType, remote_addr: 'socket._RetAddress', port: int, data: bytes):
        client_id = (port_type, remote_addr)
        if data == b'':
            self.unregister_client(client_id)
            return
        if client_id not in self._clients:
            self._init_virtual_client(port_type, remote_addr, port)
        client: VirtualClient = self._clients[client_id]
        local_addr = self._remote2local[port_type, port]
        client.sendto_buffer(data, local_addr)

    def _init_virtual_client(self, port_type: PortType, remote_addr: 'socket._RetAddress', port: int):
        logging.info(f'New {PortType(port_type).name} connection {remote_addr}')
        clientClass = self.upstream[port_type]
        local_addr = self._remote2local[(port_type, port)]
        client = clientClass(server=self, host=local_addr[0], port=local_addr[1], addr=remote_addr)
        self._selector.register(client._sock, selectors.EVENT_READ | selectors.EVENT_WRITE, client)
        self._clients[(port_type, remote_addr)] = client

    def _pack_for_send(self, data: bytes):
        return pack(data)

    def _unpack_for_receive(self, data: bytes) -> tuple[bytes, int, bool]:
        return unpack(data)
