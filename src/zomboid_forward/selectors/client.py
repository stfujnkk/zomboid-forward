from zomboid_forward.selectors.libs import (
    BaseTCPClient,
    InputStream,
    OutputStream,
    SocketStatus,
    ForwardStream,
)
from zomboid_forward.utils import (
    unpack_addr,
    pack_addr,
)
import json
import struct
import socket
import selectors
import typing
from zomboid_forward.config import (
    # MAX_PACKAGE_SIZE,
    # TIME_OUT,
    # ENCODEING,
    # EMPTY_ADDR,
    Addr, )


class ForwardClient(BaseTCPClient):

    def __init__(self, conf: dict) -> None:
        super().__init__(
            conf['common']['server_addr'].strip(),
            int(conf['common']['server_port']),
        )
        self.conf = conf
        self.clients: typing.Dict[Addr, SocketStatus] = {}
        self._remote2local: typing.Dict[int, Addr] = {}
        self._local2remote: typing.Dict[Addr, int] = {}
        for k, v in conf.items():
            if k == 'common' or k == 'DEFAULT':
                continue
            local_ip = v['local_ip']

            local_ports = [int(x) for x in v['local_port'].split(',')]
            remote_ports = [int(x) for x in v['remote_port'].split(',')]

            for local_port, remote_port in zip(local_ports, remote_ports):
                self._remote2local[remote_port] = (local_ip, local_port)
                self._local2remote[(local_ip, local_port)] = remote_port
                pass

            pass

    def handle_connection(
        self,
        input_stream: InputStream,
        output_stream: OutputStream,
    ):
        self._output_stream = output_stream
        conf = self.conf.copy()
        conf.pop('common', None)
        output_stream.write(json.dumps(self.conf).encode())

        while not self._closed:
            pkg = input_stream.read()
            remote_port = struct.unpack('!H', pkg[:2])[0]
            remote_addr = unpack_addr(pkg[2:8])

            if remote_addr not in self.clients:
                self.clients[remote_addr] = self.start_udp_client(remote_addr)

            socket_status = self.clients[remote_addr]

            local_addr = self._remote2local[remote_port]
            socket_status.output.write((pkg[8:], local_addr))

        pass

    def start_udp_client(self, remote_addr):
        udp_client = socket.socket(
            socket.AF_INET,
            socket.SOCK_DGRAM,
        )
        udp_client.settimeout(300)
        return self._dispatcher.register(
            udp_client,
            selectors.EVENT_READ | selectors.EVENT_WRITE,
            {'remote_addr': remote_addr},
            input_stream=ForwardStream(self.push_data),
        )

    def push_data(self, pkg, ctx: dict = None):
        data, local_addr = pkg
        remote_port = self._local2remote[local_addr]
        head = struct.pack('!H', remote_port) + pack_addr(ctx['remote_addr'])
        self._output_stream.write(head + data)
        pass

    pass