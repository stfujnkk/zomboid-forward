import socket
import threading
import time
import json
import logging
import typing
from zomboid_forward.config import (
    MAX_PACKAGE_SIZE,
    BUFFER_SIZE,
    TIME_OUT,
    ENCODEING,
    EMPTY_ADDR,
    Addr,
)
from zomboid_forward.utils import (
    pack,
    unpack,
    recv_pkg,
    send_pkg,
    encrypt_token,
    decrypt_token,
)


class UDPForwardServer:
    log = logging.getLogger('UDPForwardServer')

    def __init__(self, conf: dict):
        self.transit_addr = (
            conf['common']['bind_addr'],
            int(conf['common']['bind_port']),
        )
        self._token: bytes = conf['common']['token'].strip().encode(ENCODEING)
        del conf['common']['token']

    def pull_data(
        self,
        server_addr: Addr,
        udp_server: socket.socket,
        transit_client: socket.socket,
    ):
        server_name = f'The service on Port {server_addr[1]}'
        try:
            while True:
                try:
                    data, src_addr = udp_server.recvfrom(MAX_PACKAGE_SIZE)
                    self.log.debug(f'{src_addr} >>> {server_addr} {data}')
                    transit_client.sendall(pack(src_addr, server_addr, data))
                except Exception as e:
                    if transit_client._closed:
                        return
                    if isinstance(e, ConnectionResetError):
                        if hasattr(e, 'winerror') and e.winerror == 10054:
                            self.log.warning(
                                f'{server_name} sent data to an unreachable address'
                            )
                            continue
                    self.log.error(
                        f'{server_name} has been shut down due to {e.__class__}{e}'
                    )
                    pass
        finally:
            udp_server.close()
            pass

    def handle(
        self,
        transit_client: socket.socket,
        addr: Addr,
    ):
        try:
            transit_client.settimeout(3)
            t, f1, f2 = encrypt_token(self._token)
            transit_client.sendall(pack(EMPTY_ADDR, EMPTY_ADDR, f1 + f2))
            pkg, buf = recv_pkg(transit_client)
            if not pkg or t != pkg[-1]:
                self.log.debug(f'Client token verification failed:{addr}')
                transit_client.close()
                return
            transit_client.settimeout(None)
            self.log.info(f'Successfully connected to client:{addr}')
            pkg, buf = recv_pkg(transit_client, buf)
            if not pkg:
                raise Exception(f'Failed to read client configuration:{addr}')
            threading.Thread(
                target=self.forwarding_service,
                daemon=True,
                args=(transit_client, json.loads(pkg[-1]), addr, buf),
            ).start()
        except Exception as e:
            self.log.error(
                f'Client Address:{addr}:Error initializing service,caused by {e.__class__}:{e}'
            )
            transit_client.close()

    def forwarding_service(
        self,
        transit_client: socket.socket,
        client_config: dict,
        client_addr: Addr,
        buf: bytes = b'',
    ):
        port_mapping = {}
        try:
            for k, v in client_config.items():
                if k == 'common' or k == 'DEFAULT':
                    continue
                remote_ports = [int(x) for x in v['remote_port'].split(',')]
                for remote_port in remote_ports:
                    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    server.setblocking(True)
                    server.bind(('0.0.0.0', remote_port))
                    port_mapping[remote_port] = {
                        'server_addr': ('0.0.0.0', remote_port),
                        'client': transit_client,
                        'server': server,
                    }
                    conf = port_mapping[remote_port]
                    threading.Thread(
                        target=self.pull_data,
                        daemon=True,
                        args=(
                            conf['server_addr'],
                            conf['server'],
                            conf['client'],
                        ),
                    ).start()
            self.log.debug(
                f'Successfully loaded client configuration with address {client_addr}:{client_config}'
            )
            while True:
                data = transit_client.recv(BUFFER_SIZE)
                buf += data
                while True:
                    pkg, l = unpack(buf)
                    if not l:
                        break
                    buf = buf[l:]
                    src_addr, dst_addr, _, payload = pkg
                    self.log.debug(f"{dst_addr} <<< {src_addr} {payload}")
                    server = port_mapping[src_addr[1]]['server']
                    send_pkg(server, pkg)
                    pass
                if not data:
                    self.log.info(f'Client closed:{client_addr}')
                    break
        except Exception as e:
            self.log.error(
                f'The client with address {client_addr} has been forcibly shut down, caused by {e.__class__}:{e}'
            )
        finally:
            transit_client.close()
            for k, v in port_mapping.items():
                v['server'].close()
        pass

    def _run_server(self):
        self.transit_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.transit_server.bind(self.transit_addr)
        self.transit_server.listen(1)
        while True:
            transit_client, addr = self.transit_server.accept()
            threading.Thread(
                target=self.handle,
                daemon=True,
                args=(transit_client, addr),
            ).start()

    def serve_forever(self):
        self.log.info('Waiting for client connection...')
        self.log.info(f'Listening for {self.transit_addr}')

        th = threading.Thread(
            target=self._run_server,
            daemon=True,
        )
        th.start()
        while th.is_alive():
            time.sleep(0.4)
        pass

    pass


class UDPForwardClient:
    log = logging.getLogger('UDPForwardClient')

    def __init__(self, conf: dict):
        self.conf = conf
        self.udp_client_pool: typing.Dict[int, socket.socket] = {}
        self.server_addr: Addr = (
            conf['common']['server_addr'].strip(),
            int(conf['common']['server_port']),
        )
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
        self._lock = threading.RLock()
        self._token: bytes = conf['common']['token'].strip().encode(ENCODEING)
        del conf['common']['token']
        self.stop = False

    def _connect(self, timeout: float):
        self.log.info('Attempting to connect ...')
        tcp_pipeline = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            tcp_pipeline.connect(self.server_addr)
            pkg, buf = recv_pkg(tcp_pipeline)
            if not pkg:
                raise Exception(
                    f'The service has been shut down: {self.server_addr}')
            tcp_pipeline.sendall(
                pack(
                    EMPTY_ADDR,
                    EMPTY_ADDR,
                    decrypt_token(self._token, pkg[-1]),
                ))
            conf = self.conf.copy()
            conf.pop('common', None)
            tcp_pipeline.sendall(
                pack(
                    EMPTY_ADDR,
                    EMPTY_ADDR,
                    json.dumps(conf).encode(),
                ))
            self.log.info(
                f'Successfully connected to server:{self.server_addr}')
            self.distribute_data(
                pipeline=tcp_pipeline,
                timeout=timeout,
                buf=buf,
            )
        except Exception as e:
            self.log.error(
                f'Exception connecting to server, caused by {e.__class__}:{e}')
            tcp_pipeline.close()
        pass

    def connect(self, timeout: float = TIME_OUT):
        th = threading.Thread(
            target=self._connect,
            args=(timeout, ),
            daemon=True,
        )
        th.start()
        while th.is_alive() and not self.stop:
            time.sleep(0.4)
        pass

    def distribute_data(
        self,
        pipeline: socket.socket,
        timeout: float,
        buf=b'',
    ):
        while True:
            data = pipeline.recv(BUFFER_SIZE)
            buf += data
            while True:
                pkg, l = unpack(buf)
                if not l:
                    break
                buf = buf[l:]
                src_addr, dst_addr, _, payload = pkg
                self.log.debug(f"{src_addr} >>> {dst_addr} {payload}")
                with self._lock:
                    udp_client = self.udp_client_pool.get(src_addr)
                local_addr = self._remote2local[dst_addr[1]]
                if udp_client:
                    send_pkg(udp_client, pkg, addr=local_addr)
                else:
                    # 开启udp
                    udp_client = socket.socket(
                        socket.AF_INET,
                        socket.SOCK_DGRAM,
                    )
                    udp_client.settimeout(timeout)
                    with self._lock:
                        self.udp_client_pool[src_addr] = udp_client
                    # 先发送建立连接
                    send_pkg(udp_client, pkg, addr=local_addr)
                    # TODO use thread pool
                    threading.Thread(
                        target=self.push_data,
                        args=(src_addr, pipeline, udp_client),
                        daemon=True,
                    ).start()
                pass
            pass
            if not data:
                self.log.info(
                    f'TCP connection closed:{pipeline.getsockname()}')
                break
        pass

    def push_data(
        self,
        remote_addr: Addr,
        pipeline: socket.socket,
        udp_client: socket.socket,
    ):
        client_name = f'The remote client with address {remote_addr}'
        try:
            while True:
                data, src_addr = udp_client.recvfrom(MAX_PACKAGE_SIZE)
                l_ip, l_port = src_addr
                server_addr = (
                    '0.0.0.0',
                    self._local2remote[(l_ip, l_port)],
                )
                self.log.debug(f"{remote_addr} <<< {server_addr} {data}")
                pipeline.sendall(pack(server_addr, remote_addr, data))
        except socket.timeout:
            self.log.warn(f'{client_name} has timed out')
        except Exception as e:
            self.log.error(
                f'{client_name} has been shut down due to {e.__class__}:{e}')
        finally:
            with self._lock:
                self.udp_client_pool.pop(remote_addr, None)
            udp_client.close()

    pass
