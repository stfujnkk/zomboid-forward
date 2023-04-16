# udp 服务端

设置bind表示这是udp服务端，先 recvfrom 后 sendto

客户端宕机，服务端

客户端超时导致的宕机,可能导致recvfrom时`ConnectionResetError: [WinError 10054] 远程主机强迫关闭了一个现有的连接。`
准确来说是因为在UDP通信过程中，客户端中途断开。
# udp 客户端

需要先sendto后recvfrom
不设置超时直接 recvfrom 会报错 `OSError: [WinError 10022] 提供了一个无效的参数`

客户端往服务端发送不会报错，即使服务器宕机。
udp第一次交互成功后即使服务器宕机，使用recvfrom也会一直阻塞。
settimeout 可以避免这种情况


若是第一次sendto前服务器宕机, recvfrom 会报错`ConnectionResetError: [WinError 10054] 远程主机强迫关闭了一个现有的连接。`，否则recvfrom会一直阻塞等待。
是等待还是报错和连接的是本地还是远程也有关系，连接本地会报错，远程则会等待。

刚刚sendto后的第一个recvfrom,如果没设置超时客户端可能会过一会继续执行下面代码，其他recvfrom依然阻塞

sendto 会触发ConnectionResetError,但最终抛出异常的地方在recvfrom。如果未往无效地址发送消息，则不会抛出异常
https://stackoverflow.com/questions/34242622/windows-udp-sockets-recvfrom-fails-with-error-10054
# 超时设置
settimeout 设置连接超时 