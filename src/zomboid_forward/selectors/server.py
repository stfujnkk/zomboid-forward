import socket
import abc
import struct
from typing import Type, Dict, Tuple
import selectors
import json
import logging
from .libs import (
    ServerEndpoint,
    unpack_addr,
    PortType,
    pack_addr,
    ClientEndpoint,
    SteppingSenderMixin,
    SteppingReceiverMixin,
    init_tcp_keep_alive_opt,
    Endpoint,
    BUFFER_SIZE,
    pack,
    unpack,
)
from zomboid_forward.utils import encrypt_token


class ForwardServer(ServerEndpoint):

    def __init__(self, transit_endpoint: 'TransitClientEndpoint', port: int, host: str = '0.0.0.0', **kwargs) -> None:
        super().__init__(selector=transit_endpoint._selector, port=port, host=host, **kwargs)
        self._transit_endpoint = transit_endpoint

    def transit(self, addr: 'socket._RetAddress', data: bytes, port_type: PortType) -> None:
        head = struct.pack('!HH', port_type, self.server_addr[1]) + pack_addr(addr)
        self._transit_endpoint.buffer.append(head + data)

    @classmethod
    def dispatch(cls, transit_endpoint: 'TransitClientEndpoint', data: bytes):
        port_type, port = struct.unpack('!HH', data[:4])
        server = transit_endpoint._port_mapping[(port_type, port)]
        remote_addr = unpack_addr(data[4:10])
        server._forward_to(data[10:], remote_addr)

    @abc.abstractmethod
    def _forward_to(self, data: bytes, addr: 'socket._RetAddress'):
        ...

    def register_server(self, selector: 'selectors.BaseSelector'):
        return selector.register(self._sock, selectors.EVENT_READ, self)


class ForwardTCPServerEndpoint(ForwardServer):

    def notify_read(self) -> None:
        sock, addr = self._sock.accept()
        logging.info(f'New TCP connection {self.server_addr}<==>{addr}')
        sock.setblocking(False)
        init_tcp_keep_alive_opt(sock)

        client = ForwardTCPClientEndpoint(self, sock, addr)
        self.register_client(client)
        self._selector.register(client._sock, selectors.EVENT_WRITE | selectors.EVENT_READ, client)

    def _forward_to(self, data: bytes, addr: 'socket._RetAddress'):
        if addr not in self._clients:
            logging.warning(f'No corresponding TCP connection {self.server_addr}<==>{addr}')
            self.transit(addr, b'', PortType.TCP)
            return
        client = self._clients[addr]
        if data == b'':
            # client.close()
            client._read_closed = True
            return
        client.buffer.append(data)


class ForwardTCPClientEndpoint(ClientEndpoint['ForwardTCPServerEndpoint'], SteppingSenderMixin):

    def notify_read(self) -> None:
        data = self._sock.recv(BUFFER_SIZE)
        if data == b'':
            self._read_closed = True
            # self.close()
            return
        self._server.transit(self._addr, data, PortType.TCP)

    def notify_write(self) -> None:
        next(self._stepping_sender)

    def close(self) -> None:
        logging.info(f'TCP client closed {self._addr}')
        self._server.transit(self._addr, b'', PortType.TCP)
        self._server.unregister_client(self._addr)
        return super().close()

    pass


class ForwardUDPServerEndpoint(ForwardServer, SteppingSenderMixin):
    """
    Note:
        notify_read 和 notify_write 不能并行执行
    """

    def __init__(self, transit_endpoint: 'TransitClientEndpoint', port: int, host: str = '0.0.0.0', **kwargs) -> None:
        super().__init__(transit_endpoint=transit_endpoint, port=port, host=host, **kwargs)
        self._latest_address = None

    def notify_read(self) -> None:
        try:
            data, addr = self._sock.recvfrom(BUFFER_SIZE)
            self.transit(addr, data, PortType.UDP)
        except ConnectionResetError:  # [WinError 10054]
            logging.info(f'UDP client closed {self._latest_address}')
            # Notify to close
            self.transit(self._latest_address, b'', PortType.UDP)

    def notify_write(self) -> None:
        next(self._stepping_sender)

    def _init_sock(self) -> socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setblocking(False)
        sock.bind(self.server_addr)
        return sock

    def register_server(self, selector: selectors.BaseSelector):
        return selector.register(self._sock, selectors.EVENT_READ | selectors.EVENT_WRITE, self)

    def _forward_to(self, data: bytes, addr: 'socket._RetAddress'):
        self.buffer.append((data, addr))

    def _send_to(self, data):
        # 65507
        self._latest_address = data[1]
        send_len = self._sock.sendto(*data)
        data = (data[0][send_len:], data[1])
        if data[0]:
            return data
        return False


class TransitClientEndpoint(ClientEndpoint['ZomboidForwardServer'], SteppingSenderMixin, SteppingReceiverMixin):

    downstream_services: Dict[PortType, Type[ForwardServer]] = {
        PortType.TCP: ForwardTCPServerEndpoint,
        PortType.UDP: ForwardUDPServerEndpoint,
    }

    def __init__(self, server, sock, addr, **kwargs) -> None:
        super().__init__(server=server, sock=sock, addr=addr, **kwargs)
        self._port_mapping: Dict[Tuple[int, int], 'ForwardServer'] = {}

    def notify_write(self) -> None:
        if self._state == 0:
            self._token, f1, f2 = encrypt_token(self._server._token)
            self.buffer.append(f1 + f2)
            self._state = 1

        next(self._stepping_sender)

    def notify_read(self) -> None:
        if self._state == 0:
            return

        pkgs = next(self._stepping_receiver)

        if len(pkgs) == 0:
            return
        if self._state == 1:
            pkg = pkgs.pop(0)
            if self._token != pkg:
                raise Exception('VERIFICATION FAILED')
            self._state = 2

        if len(pkgs) == 0:
            return
        if self._state == 2:
            conf = json.loads(pkgs.pop(0))
            self._init_forward_server(conf)
            for s in self._port_mapping.values():
                s.register_server(self._selector)
            self._state = 3

        # if self._state < 3:
        #     return

        for pkg in pkgs:
            port_type = struct.unpack('!H', pkg[:2])[0]
            self.downstream_services[port_type].dispatch(self, pkg)

    def close(self) -> None:
        for s in self._port_mapping.values():
            s.close()
            self._server._used_ports.remove(s.server_addr[1])
        super().close()

    def _init_forward_server(self, client_config: Dict):
        ports = set()
        for k, v in client_config.items():
            if k == 'common' or k == 'DEFAULT':
                continue
            for x in v['remote_port'].split(','):
                x = int(x)
                if x in ports:
                    raise Exception(f'The port is already occupied:{x}')
                ports.add(x)
            pass

        duplicate_port = ports & self._server._used_ports
        if duplicate_port:
            raise Exception(f'The port is already occupied:{duplicate_port}')

        for k, v in client_config.items():
            if k == 'common' or k == 'DEFAULT':
                continue

            server_type = v.get('type') or 'udp'
            port_type = PortType[server_type.upper()]
            ServerClass = self.downstream_services[port_type]

            remote_ports = set(int(x) for x in v['remote_port'].split(','))

            for remote_port in remote_ports:
                self._port_mapping[(port_type, remote_port)] = ServerClass(self, remote_port)

            pass

        self._server._used_ports |= ports

    def _pack_for_send(self, data: bytes):
        return pack(data)

    def _unpack_for_receive(self, data: bytes) -> Tuple[bytes, int, bool]:
        return unpack(data)

    pass


class ZomboidForwardServer(ServerEndpoint):

    def __init__(self, conf: Dict) -> None:
        super().__init__(selector=selectors.DefaultSelector(), port=int(conf['common']['bind_port']), host=conf['common']['bind_addr'])
        self._used_ports = set()
        self._token: bytes = conf['common']['token'].strip().encode()
        del conf['common']['token']

    def notify_read(self) -> None:
        sock, addr = self._sock.accept()
        logging.info(f'Successfully connected to client {addr}')
        sock.setblocking(False)
        init_tcp_keep_alive_opt(sock)

        client = TransitClientEndpoint(self, sock, addr)
        self.register_client(client)
        self._selector.register(client._sock, selectors.EVENT_READ | selectors.EVENT_WRITE, client)

    def serve_forever(self):
        logging.info('Waiting for client connection...')
        logging.info(f'Listening for {self.server_addr}')
        try:
            self._selector.register(self._sock, selectors.EVENT_READ, self)
            while True:
                events = self._selector.select(0.5)
                for key, mask in events:
                    endpoint: Endpoint = key.data
                    if endpoint._closed:
                        continue
                    try:
                        if mask & selectors.EVENT_WRITE:
                            endpoint.notify_write()
                        if mask & selectors.EVENT_READ:
                            endpoint.notify_read()
                    except Exception as e:
                        logging.error(endpoint._sock, exc_info=e)
                        endpoint.close()
        finally:
            self.close()
            self._selector.close()
