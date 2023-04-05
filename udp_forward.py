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
    EMPTY_DATA = b'A8FDDA39A4DBB26C525C24D0173B5B89'

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
                    if data == Pipeline.EMPTY_DATA:
                        continue
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
