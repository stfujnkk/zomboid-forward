import typing
from queue import Queue
from collections import deque
from concurrent.futures import ThreadPoolExecutor, Executor
import selectors
import socket
import struct
import logging

__author__ = 'stfujnkk'
BUFFER_SIZE = 0xffff * 2
MAX_LEN = 0xffff


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
        self.reason = ClosedError('the InputStream has been closed')

    def read(self, block=True, timeout=None):
        try:
            return self._queue.get(block, timeout)
        except ClosedError:
            raise ClosedError('Unable to read') from self.reason

    def close(self, reason: Exception = None):
        self.reason = reason or self.reason
        self._queue.close()

    def _write(self, data: bytes):
        try:
            self._queue.put(data, block=False)
        except ClosedError:
            raise ClosedError('Unable to write') from self.reason

    pass


class OutputStream:

    def __init__(self):
        self._closed = False
        self._queue = deque[bytes]()
        self.reason = ClosedError('the OutputStream has been closed')

    def write(self, data: bytes):
        if self._closed:
            raise ClosedError('Unable to write') from self.reason
        self._queue.append(data)

    def close(self, reason: Exception = None):
        self._closed = True
        self.reason = reason or self.reason

    def _read(self):
        try:
            return self._queue.popleft()
        except IndexError:
            if self._closed:
                raise ClosedError('Unable to read') from self.reason
            raise

    def __len__(self):
        return len(self._queue)

    pass


class BaseTCPServer:
    log = logging.getLogger()

    def __init__(self, port: int) -> None:
        super().__init__()
        self._server_socket: socket.socket = None
        self._selector: selectors.BaseSelector = None
        self._executor: Executor = None
        self.server_addr = ('0.0.0.0', port)

    def dispatch(
        self,
        key: selectors.SelectorKey,
        mask: int,
    ):
        if key.data is None:
            self.start_service_thread()
            return
        sock: socket.socket = key.fileobj
        try:
            if key.data['is_closed']:
                return

            if mask & selectors.EVENT_WRITE:
                self.start_write_thread(key)

            if mask & selectors.EVENT_READ:
                data = sock.recv(BUFFER_SIZE)
                if not data:
                    self.start_close_thread(key)
                    return
                key.data['buf'], key.data['pkg'] = self.flush_buffer(
                    key.data['buf'] + data,
                    key.data['pkg'],
                    key.data['input'],
                )
        except Exception as e:
            self.start_close_thread(key, e)
        pass

    def flush_buffer(
        self,
        buf: bytes,
        pkg: bytes,
        input_stream: InputStream,
    ):
        while True:
            chunk, l, finish = self.unpack(buf)
            if l == 0:
                break
            pkg += chunk
            buf = buf[l:]
            if not finish:
                continue
            input_stream._write(pkg)
            pkg = b''
        return buf, pkg

    def start_close_thread(
        self,
        key: selectors.SelectorKey,
        err: Exception = None,
    ):
        if key.data['is_closed']:
            return
        key.data['is_closed'] = True

        def _close_connection():
            key.data['input'].close(err)
            key.data['output'].close(err)
            self._selector.unregister(key.fileobj)
            key.fileobj.close()

        self._executor.submit(_close_connection)

    def start_write_thread(self, key: selectors.SelectorKey):
        if key.data['is_writing']:
            return
        output: OutputStream = key.data['output']
        if key.data['request_close']:
            if len(output) == 0:
                self.start_close_thread(key)
        if len(output) == 0:
            return
        key.data['is_writing'] = True

        def _send_pkgs():
            try:
                while True:
                    key.fileobj.sendall(self.pack(output._read()))
            except IndexError:
                pass
            finally:
                key.data['is_writing'] = False

        self._executor.submit(_send_pkgs)

    def start_service_thread(self):
        connection, address = self._server_socket.accept()
        connection.setblocking(False)

        connection.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        # 35s~305s
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 35)
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 30)
        connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 10)

        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        input_stream, output_stream = InputStream(), OutputStream()
        key = self._selector.register(
            connection,
            events,
            data={
                # region: Readonly
                'addr': address,
                # endregion
                # region: Only used by dispatch
                'buf': b'',
                'pkg': b'',
                # endregion
                # region: Used to control the number of threads
                'is_writing': False,
                'is_closed': False,
                # endregion
                # Should only be modified once at the end of work
                'request_close': False,
                'input': input_stream,
                'output': output_stream,
            },
        )

        def _handle_connection():
            try:
                self.handle_connection(input_stream, output_stream)
                input_stream.close()
                output_stream.close()
                key.data['request_close'] = True
            except Exception as e:
                BaseTCPServer.log.error(
                    f"Forced shutdown of client with address {address}, caused by {e.__class__}:{e}"
                )
                self.start_close_thread(key, e)

        self._executor.submit(_handle_connection)
        pass

    def handle_connection(
        self,
        input_stream: InputStream,
        output_stream: OutputStream,
    ):
        ...

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
                        self.dispatch(key, mask)
                    pass
        except KeyboardInterrupt:
            pass
        finally:
            self._closed = True
            self._server_socket.close()

    @staticmethod
    def unpack(data: bytes) -> typing.Tuple[bytes, int, bool]:
        L = len(data)
        if L < 2:
            return b'', 0, False
        l = struct.unpack('!H', data[:2])[0]
        if L < 2 + l:
            return b'', 0, False
        return data[2:2 + l], 2 + l, l != MAX_LEN

    @staticmethod
    def pack(data: bytes) -> bytes:
        pkg = b''
        for i in range(0, len(data) + 1, MAX_LEN):
            chunk = data[i:i + MAX_LEN]
            pkg += (struct.pack('!H', len(chunk)) + chunk)
        return pkg

    pass
