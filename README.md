# Zomboid-Forward
Lightweight forwarding service that can be used for forwarding [Project Zomboid](https://pzwiki.net/wiki/Main_Page) game servers

## NOTE

新项目地址 ：https://github.com/stfujnkk/pzrp
New project address : https://github.com/stfujnkk/pzrp

## Start server

- Install

  ```bash
  git clone https://github.com/stfujnkk/zomboid-forward.git
  cd zomboid-forward
  pip install .
  ```

  

- Modify [Configuration](./server.ini)

  Server Configuration Example

  ```ini
  [common]
  bind_addr = 0.0.0.0
  bind_port = 18001
  log_file = ./ZFS.log
  log_level = debug
  token = 12345678
  ```

- run

  ```bash
  python -m zomboid_forward.server
  ```

- Using `systemctl` management

  Besides manual execution, you can also start it through `systemctl`.

  ```bash
  vim /usr/lib/systemd/system/zomboid_forward.service
  ```

  Write the [following content](./systemd/zomboid_forward.service) after opening the file .
  
  ```ini
  [Unit]
  Description=Zomboid Forward Service
  After=network.target
  
  [Service]
  Type=simple
  Restart=on-failure
  RestartSec=5s
  ExecStart=python -m zomboid_forward.server
  
  [Install]
  WantedBy=multi-user.target
  ```
  
  Execute the following command to start the service
  
  ```bash
  chmod 754 /usr/lib/systemd/system/zomboid_forward.service
  systemctl enable zomboid_forward.service
  systemctl start zomboid_forward.service
  systemctl status zomboid_forward.service
  ```
  
  view log
  
  ```bash
  journalctl -r -u zomboid_forward
  tail -f ~/.zomboid_forward/ZFS.log
  ```

## Launch the client

- Install

  Installing the client is the same as installing the server

- Modify [Configuration](./client.ini)

  ```ini
  [common]
  server_addr = 192.168.45.154
  server_port = 18001
  log_file = ./ZFC.log
  log_level = debug
  token = 12345678
  [ProjectZomboid]
  ; type = udp
  local_ip = 127.0.0.1
  local_port = 16261,16262
  remote_port = 16261,16262
  ```

  Change `server_addr` to your server's IP and ensure that the server and client tokens are the same.

- run

  ```bash
  python -m zomboid_forward.client
  ```
  
  Terminate the program with `Ctrl+C`




