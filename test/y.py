from urllib.request import urlopen
from json import load
ip = load(urlopen('https://api.ipify.org/?format=json'))['ip']
print(ip)