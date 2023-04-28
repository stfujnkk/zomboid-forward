import typing
from queue import Queue, Empty
from concurrent.futures import ThreadPoolExecutor, Executor
import selectors
import socket
import struct
import logging

__author__ = 'stfujnkk'

MAX_LEN = 0xefff
BUFFER_SIZE = MAX_LEN * 2


class ClosedError(Exception):
    pass


class Pipeline(Queue):

    def __init__(self, maxsize=0):
        super().__init__(maxsize)
        self._closed = False

    def close(self):
        with self.not_full:
            self._closed = True
            self.not_empty.notify_all()
            self.not_full.notify_all()

    def _qsize(self) -> int:
        l = super()._qsize()
        if l == 0 and self._closed:
            raise ClosedError('The pipeline has been closed')
        return l

    def _put(self, item):
        if self._closed:
            raise ClosedError('The pipeline has been closed')
        return super()._put(item)

    pass


class InputStream:

    def __init__(self):
        self._closed = False
        self._queue = Pipeline()
        self._reason = ClosedError('the InputStream has been closed')

    def read(self, block=True, timeout=None) -> bytes:
        try:
            return self._queue.get(block, timeout)
        except ClosedError:
            raise ClosedError('Unable to read') from self._reason

    def close(self, reason: Exception = None):
        self._reason = reason or self._reason
        self._queue.close()

    def _write(self, data: bytes, context=None):
        """
        Note:
            这个方法不应该阻塞
        """
        try:
            self._queue.put(data, block=False)
        except ClosedError:
            raise ClosedError('Unable to write') from self._reason

    pass


class OutputStream:
    PACKET_TYPE = typing.Union[bytes, typing.Tuple[bytes, tuple]]

    def __init__(self):
        self._closed = False
        self._queue = Pipeline()
        self._reason = ClosedError('the OutputStream has been closed')

    def write(self, data: PACKET_TYPE):
        """
        Note:
            这个方法不应该阻塞
        """
        try:
            self._queue.put(data, block=False)
        except ClosedError:
            raise ClosedError('Unable to write') from self._reason

    def close(self, reason: Exception = None):
        self._reason = reason or self._reason
        self._queue.close()
        # 确保所有写入操作已经停止,数据不会再增长
        self._closed = True

    def _read(self) -> PACKET_TYPE:
        """
        Note:
            这个方法不应该阻塞
        """
        try:
            return self._queue.get(block=False)
        except ClosedError:
            raise ClosedError('Unable to read') from self._reason

    def __len__(self) -> int:
        """
        Note:
            这个是无锁的
        """
        return self._queue._qsize()

    pass


class SocketStatus:

    def __init__(
        self,
        data,
        input_stream: InputStream = None,
        output_stream: OutputStream = None,
    ) -> None:
        # region: Buffer
        self._buf = b''
        self._pkg = b''
        # endregion
        # region: Used to control the number of threads
        self._is_writing = False
        self._is_closed = False
        # endregion
        self._err: Exception = None

        self.input = input_stream or InputStream()
        self.output = output_stream or OutputStream()
        self.data = data
        pass

    def close(self, err: Exception = None):
        if err:
            self._err = err
        self.output.close(self._err)
        self.input.close(self._err)
        pass

    pass


class Dispatcher:
    log = logging.getLogger()

    def __init__(
        self,
        selector: selectors.BaseSelector,
        executor: Executor,
    ):
        super().__init__()
        self._selector: selectors.BaseSelector = selector
        self._executor: Executor = executor

    def dispatch(
        self,
        key: selectors.SelectorKey,
        mask: int,
    ):
        socket_status: SocketStatus = key.data
        sock: socket.socket = key.fileobj
        try:
            if socket_status._is_closed:
                return
            if socket_status._err:
                raise socket_status._err

            if mask & selectors.EVENT_READ:
                if sock.type == socket.SOCK_STREAM:
                    data = sock.recv(BUFFER_SIZE)
                    if not data:
                        self.start_close_thread(key)
                        return
                    self.flush_buffer(socket_status, data)
                else:
                    data, addr = sock.recvfrom(MAX_LEN)
                    socket_status.input._write((data, addr),context=socket_status.data)
                pass

            if mask & selectors.EVENT_WRITE:
                self.start_write_thread(key)
        except Exception as e:
            self.log.exception('Error occurred during dispatch')
            self.start_close_thread(key, e)
        pass

    def flush_buffer(
        self,
        socket_status: SocketStatus,
        data: bytes,
    ):
        buf, pkg = socket_status._buf + data, socket_status._pkg
        input_stream = socket_status.input
        while True:
            chunk, l, finish = self.unpack(buf)
            if l == 0:
                break
            pkg += chunk
            buf = buf[l:]
            if not finish:
                continue
            input_stream._write(pkg, context=socket_status.data)
            pkg = b''
        socket_status._buf, socket_status._pkg = buf, pkg

    def start_close_thread(
        self,
        key: selectors.SelectorKey,
        err: Exception = None,
    ):
        socket_status: SocketStatus = key.data
        sock: socket.socket = key.fileobj
        if socket_status._is_closed:
            return
        socket_status._is_closed = True

        def _close_connection():
            socket_status.close(err)
            self._selector.unregister(sock)
            sock.close()

        self._executor.submit(_close_connection)

    def start_write_thread(self, key: selectors.SelectorKey):
        socket_status: SocketStatus = key.data
        sock: socket.socket = key.fileobj
        if socket_status._is_writing:
            return
        output = socket_status.output

        try:
            if len(output) == 0:
                return

            def _write_thread():
                try:
                    while True:
                        self.send_pkg(sock, output)
                except Empty:
                    pass
                finally:
                    socket_status._is_writing = False

            socket_status._is_writing = True
            self._executor.submit(_write_thread)
        except ClosedError:
            self.start_close_thread(key)

    @classmethod
    def send_pkg(cls, sock: socket.socket, output: OutputStream):
        if sock.type == socket.SOCK_STREAM:
            sock.sendall(cls.pack(output._read()))
        else:
            sock.sendto(*output._read())
        pass

    def register(
        self,
        fileobj: socket.socket,
        events: int,
        data,
        input_stream: InputStream = None,
        output_stream: OutputStream = None,
    ):
        socket_status = SocketStatus(data, input_stream, output_stream)
        self._selector.register(fileobj, events, socket_status)
        return socket_status

    def unregister(self, fileobj: socket.socket):
        self._selector.unregister(fileobj)

    @classmethod
    def unpack(cls, data: bytes) -> typing.Tuple[bytes, int, bool]:
        L = len(data)
        if L < 2:
            return b'', 0, False
        l = struct.unpack('!H', data[:2])[0]
        if L < 2 + l:
            return b'', 0, False
        return data[2:2 + l], 2 + l, l != MAX_LEN

    @classmethod
    def pack(cls, data: bytes) -> bytes:
        pkg = b''
        for i in range(0, len(data) + 1, MAX_LEN):
            chunk = data[i:i + MAX_LEN]
            pkg += (struct.pack('!H', len(chunk)) + chunk)
        return pkg

    pass


class BaseTCPServer:
    log = logging.getLogger()

    def __init__(self, port: int, host: str = '0.0.0.0') -> None:
        super().__init__()
        self._server_socket: socket.socket = None
        self._selector: selectors.BaseSelector = None
        self._executor: Executor = None
        self._dispatcher: Dispatcher = None
        self.server_addr = (host, port)

    def start_service_thread(self):
        connection, address = self._server_socket.accept()
        connection.setblocking(False)

        connection.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # 35s~305s
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 35)
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 30)
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 10)

        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        socket_status = self._dispatcher.register(
            connection,
            events,
            data={},
        )

        def _handle_connection():
            try:
                self.handle_connection(
                    socket_status.input,
                    socket_status.output,
                )
                socket_status.close()
            except Exception as e:
                self.log.error(
                    f"Forced shutdown of client with address {address}, caused by {e.__class__}:{e}"
                )
                socket_status.close(e)

        self._executor.submit(_handle_connection)
        pass

    def handle_connection(
        self,
        input_stream: InputStream,
        output_stream: OutputStream,
    ):
        raise NotImplementedError()

    def serve_forever(self, poll_interval: float = 0.5):
        self._closed = False
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )
        self._server_socket.setblocking(False)
        self._server_socket.bind(self.server_addr)
        self._server_socket.listen()
        try:
            with selectors.DefaultSelector() as selector, ThreadPoolExecutor(
            ) as executor:

                self._selector = selector
                self._executor = executor
                dispatcher = Dispatcher(selector, executor)
                self._dispatcher = dispatcher
                selector.register(
                    self._server_socket,
                    selectors.EVENT_READ,
                    data=None,
                )
                while not self._closed:
                    events = selector.select(poll_interval)
                    if self._closed:
                        break
                    for key, mask in events:
                        if key.data is None:
                            self.start_service_thread()
                            continue
                        dispatcher.dispatch(key, mask)
                    pass
        except KeyboardInterrupt:
            pass
        finally:
            self._closed = True
            self._server_socket.close()

    pass


class BaseTCPClient:

    def __init__(self, host: str, port: int) -> None:
        super().__init__()
        self._sock: socket.socket = None
        self._selector: selectors.BaseSelector = None
        self._executor: Executor = None
        self._dispatcher: Dispatcher = None
        self.server_addr = (host, port)
        self._closed = False

    def connect(self):
        self._closed = False
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock = self._socket
        sock.connect(self.server_addr)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 35)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 30)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 10)

        try:
            with selectors.DefaultSelector() as selector, ThreadPoolExecutor(
            ) as executor:
                self._selector = selector
                self._executor = executor
                dispatcher = Dispatcher(selector, executor)
                self._dispatcher = dispatcher
                socket_status = dispatcher.register(
                    self._sock,
                    selectors.EVENT_READ | selectors.EVENT_WRITE,
                    data=None,
                )
                executor.submit(
                    self.handle_connection,
                    socket_status.input,
                    socket_status.output,
                )
                while not self._closed:
                    events = selector.select(0.5)
                    if self._closed:
                        break
                    for key, mask in events:
                        dispatcher.dispatch(key, mask)
                    pass
                pass
        finally:
            self._closed = True

    def handle_connection(
        self,
        input_stream: InputStream,
        output_stream: OutputStream,
    ):
        raise NotImplementedError()

    pass


class ForwardStream(InputStream):

    def __init__(self, forward: typing.Callable):
        super().__init__()
        self._forward = forward

    def _write(self, data: bytes, context=None):
        return self._forward(data, context)

    pass