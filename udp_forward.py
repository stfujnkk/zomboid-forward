import socket
import threading
import typing
import logging
import time


class UdpEndPoint:

    def __init__(self, port: int) -> None:
        self.addr: typing.Tuple[str, int] = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.sock.bind(("0.0.0.0", port))
        pass

    pass


class Pipeline:
    log = logging.getLogger()

    def __init__(self, port1, port2) -> None:
        self.end_point1 = UdpEndPoint(port1)
        self.end_point2 = UdpEndPoint(port2)
        self.stop_event = threading.Event()
        pass

    def pull_data(self, reverse):
        point1, point2 = self.end_point1, self.end_point2
        if reverse:
            point1, point2 = point2, point1
        try:
            while not self.stop_event.is_set():
                try:
                    errno = 1
                    data, addr1 = point1.sock.recvfrom(1024)
                    errno = 2
                    Pipeline.log.debug(f'from: {addr1}')
                    Pipeline.log.debug(data)
                    point1.addr = addr1
                    if point2.addr is None:
                        Pipeline.log.warning(
                            f'The data from {addr1} was ignored because the destination address is empty'
                        )
                        continue
                    errno = 3
                    point2.sock.sendto(data, point2.addr)
                    errno = 4
                except BlockingIOError:
                    time.sleep(0.4)
                    continue
                except Exception as e:
                    Pipeline.log.error(f'errno {errno}:{e.__class__}:{e}')
                    if errno == 1:
                        point1.addr = None
                    elif errno == 3:
                        point2.addr = None
                pass
        finally:
            self.stop_event.set()
        pass

    def run(self):
        t1 = threading.Thread(
            target=self.pull_data,
            args=(True, ),
            daemon=True,
        )
        t2 = threading.Thread(
            target=self.pull_data,
            args=(False, ),
            daemon=True,
        )
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        pass

    pass


secret_signal = [
    '宫廷玉液酒'.encode('utf8'),
    '一百八一杯'.encode('utf8'),
    '这酒怎么样'.encode('utf8'),
]


def three_messages_handshake(
    host: str,
    port: int,
    is_server: bool,
    timeout: float,
    log: logging.Logger,
    stop_event: threading.Event = None,
):
    if is_server:
        return server_handshake(host, port, timeout)
    return client_handshake(host, port, timeout, log, stop_event)


def client_handshake(
    host: str,
    port: int,
    timeout: float,
    log: logging.Logger,
    stop_event: threading.Event,
):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    addr = (host, port)
    status = 0
    while status < 2 and (not stop_event or not stop_event.is_set()):
        try:
            sock.sendto(secret_signal[status], addr)
            status = 1
            data, _ = sock.recvfrom(15)
            if data != secret_signal[status]:
                status = 0
                continue
            status = 2
            sock.sendto(secret_signal[status], addr)
        except socket.timeout as e:
            status = 0
            log.warning(e)
        except ConnectionResetError as e:
            status = 0
            log.error(e)
            time.sleep(1)
    sock.close()
    return addr


def server_handshake(host: str, port: int, timeout: float):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    client = None
    status = 0
    while status < 2:
        sock.settimeout(None)
        data, client = sock.recvfrom(15)
        if data != secret_signal[status]:
            status = 0
            continue
        status = 1
        sock.sendto(secret_signal[status], client)
        status = 2
        t = timeout
        try:
            while True:
                if t <= 0:
                    raise socket.timeout()
                sock.settimeout(t)
                start = time.time()
                data, client2 = sock.recvfrom(15)
                t -= (time.time() - start)
                if client2 != client:
                    continue
                if data != secret_signal[status]:
                    status = 0
                break
        except socket.timeout:
            status = 0
        pass
    sock.close()
    return client