# zomboid-forward
Lightweight UDP forwarding service that can be used for forwarding Project Zomboid game servers

## Deployment Services (linux)

- Download Code

  ```bash
  git clone https://github.com/stfujnkk/zomboid-forward.git
  cd zomboid-forward
  ```

  

- Modify Configuration

  ```ini
  [server]
  host=xxx.xxx.xxx.xxx
  transit_port=18001
  port=16261
  [client]
  port=16261
  ```

  - Change the host field to the public address of the server

  - Change the `port` under the `client` section to the local port that needs to be forwarded

  - Configure the firewall and server so that traffic for ports `transit_port` and `port` can enter

    

- run

  ```bash
  nohup python3 server.py >> forward.log 2>&1 &
  ```

  When running the `tail -f forward.log` command to monitor the logs, the following information will be displayed upon client connection:

  ```bash
  ubuntu@VM-4-13-ubuntu:~/zomboid-forward$ tail -f forward.log
  nohup: ignoring input
  The data from ('117.136.113.171', 44133) was ignored because the destination address is empty
  ```
## Launch the client

- Configuration

  The configuration of the client is the same as that of the server

- run

  ```powershell
  python .\client.py
  ```
  
  Terminate the program with `Ctrl+C`




