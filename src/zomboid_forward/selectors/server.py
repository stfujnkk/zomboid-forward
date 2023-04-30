from zomboid_forward.selectors.libs import (
    BaseTCPServer,
    InputStream,
    OutputStream,
    SocketStatus,
    ForwardStream,
)
from zomboid_forward.utils import (
    unpack_addr,
    pack_addr,
    encrypt_token,
)
from zomboid_forward.config import ENCODING
import selectors
import struct
import json
import typing
import socket


class ForwardServer(BaseTCPServer):

    def __init__(self, conf: dict) -> None:
        super().__init__(
            host=conf['common']['bind_addr'],
            port=int(conf['common']['bind_port']),
        )

        self._token: bytes = conf['common']['token'].strip().encode(ENCODING)
        del conf['common']['token']
        self._conf = conf
        pass

    def handle_connection(
        self,
        input_stream: InputStream,
        output_stream: OutputStream,
        context: dict,
    ):
        address = context['address']
        t, f1, f2 = encrypt_token(self._token)
        output_stream.write(f1 + f2)
        t2 = input_stream.read(timeout=1)
        if t2 != t:
            self.log.info(f'Client token verification failed:{address}')
            output_stream.write(b'ko')
            return
        self.log.info(f'Client token verification successful:{address}')
        output_stream.write(b'ok')

        pkg = input_stream.read()
        client_config: dict = json.loads(pkg)
        port_mapping: typing.Dict[int, SocketStatus] = {}
        try:
            for k, v in client_config.items():
                if k == 'common' or k == 'DEFAULT':
                    continue
                remote_ports = [int(x) for x in v['remote_port'].split(',')]
                for remote_port in remote_ports:
                    port_mapping[remote_port] = self.start_udp_server(
                        remote_port,
                        output_stream,
                    )

            while not self._closed:
                pkg = input_stream.read()

                remote_port = struct.unpack('!H', pkg[:2])[0]
                socket_status = port_mapping[remote_port]

                remote_addr = unpack_addr(pkg[2:8])
                socket_status.output.write((pkg[8:], remote_addr))

                pass
        finally:
            for _, status in port_mapping.items():
                status.close()
            pass
        pass

    def start_udp_server(
        self,
        port: int,
        output_stream: OutputStream,
    ) -> SocketStatus:

        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.setblocking(False)
        server.bind(('0.0.0.0', port))
        return self._dispatcher.register(
            server,
            selectors.EVENT_READ | selectors.EVENT_WRITE,
            {'remote_port': port},
            input_stream=ForwardStream(lambda pkg, ctx: self.pull_data(output_stream, pkg, ctx)),
        )

    def pull_data(
        self,
        output_stream: OutputStream,
        pkg: bytes,
        context: dict,
    ):
        data, remote_addr = pkg
        remote_port = context['remote_port']
        head = struct.pack('!H', remote_port) + pack_addr(remote_addr)
        output_stream.write(head + data)
        pass

    pass
