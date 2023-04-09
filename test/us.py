import socket
import threading, time
import time
import requests
import typing

lock = threading.RLock()
ENCODING = 'gbk'

tokens = [b'Connection Request', b'Server allowed', b'Client normal']

Addr = typing.Tuple[str, int]


class UdpServer:

    def __init__(self, port: int) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(('0.0.0.0', port))

        self.server = server
        self.addr = None
        self.banner = 'UDP service running ...'
        self.client_status: typing.Dict[Addr, int] = {}
        self.cid_to_addr: typing.Dict[int, Addr] = {}
        self.addr_to_cid: typing.Dict[Addr, int] = {}
        self.last_sent_addr: Addr = None

    def worker(self):
        while True:
            msg = input()
            i = msg.rfind('>')
            if i == -1 and self.last_sent_addr:
                addr = self.last_sent_addr
                msg = msg.encode(ENCODING)
            else:
                try:
                    cid = int(msg[i + 1:])
                except:
                    print(f'\nError: The client id must be a number')
                    continue
                addr = self.cid_to_addr.get(cid)
                if not addr:
                    print(f'\nWran: No corresponding client: {cid}')
                    continue
                msg = msg[:i].encode(ENCODING)
            self.server.sendto(msg, addr)
            with lock:
                self.last_sent_addr = addr

    def run(self):
        threading.Thread(target=self.keep_alive, daemon=True).start()
        cur_cid = 0
        try:

            print(self.banner)
            local_addr = self.server.getsockname()
            print(f'listening for {local_addr}')
            host_name = socket.gethostname()
            print(f'Host name : {host_name}')
            lan_ip = socket.gethostbyname(host_name)
            print(f'LAN address : {lan_ip}')
            public_ip = requests.get('http://ifconfig.me').text
            print(f'Public address : {public_ip}\n')

            threading.Thread(target=self.worker, daemon=True).start()

            while True:
                try:

                    data, addr = self.server.recvfrom(1024)
                    if addr not in self.client_status:
                        self.client_status[addr] = 1
                        pass

                    n = self.client_status[addr]

                    if n < len(tokens):
                        # Confirm Connection
                        if n % 2:
                            self.server.sendto(tokens[n], addr)
                            self.client_status[addr] = n + 1
                        else:
                            if tokens[n] != data:
                                del self.client_status[addr]
                            else:
                                self.client_status[addr] = n + 1
                                cur_cid += 1
                                self.addr_to_cid[addr] = cur_cid
                                self.cid_to_addr[cur_cid] = addr
                                print(
                                    f'\nInfo: Client {cur_cid} successfully connected\n'
                                )
                                pass
                            pass
                        pass
                    else:
                        cid = self.addr_to_cid[addr]
                        msg = data.decode(ENCODING)
                        print(f'\n#{cid} {msg}\n')
                except ConnectionResetError as e:
                    print(f"{self.addr_to_cid[self.server.getpeername()]} error")
                    
                    # 多线程无法一定保证这个就是出错的地址
                    # 但因为屏幕输入很慢，可以忽略极端情况
                    # with lock:
                    #     error_addr = self.last_sent_addr
                    # cid = self.addr_to_cid.pop(error_addr, None)
                    # print(f'\nClient {cid} is no longer valid')
                    # self.client_status.pop(error_addr, None)
                    # self.cid_to_addr.pop(cid, None)
                    pass

        finally:
            self.server.close()

    def run_server(self):
        th = threading.Thread(target=self.run, daemon=True)
        th.start()
        while th.is_alive():
            time.sleep(0.4)
        pass

    def keep_alive(self):
        while True:
            addrs = set(self.addr_to_cid.keys())
            for addr in addrs:
                with lock:
                    self.last_sent_addr = addr
                self.server.sendto(b'', addr)
                # data, addr1 = self.server.recvfrom(0)
                # if data:
                #     print(data)
                # if addr1 != addr:
                #     print(addr, addr1)
            time.sleep(0.4)
        pass

    pass


if __name__ == '__main__':
    server = UdpServer(16261)
    server.run_server()

