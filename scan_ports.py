import socket, json

print('Scanning for MongoDB port 27017...')
for i in range(2, 20):
    ip = f'172.18.0.{i}'
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        result = s.connect_ex((ip, 27017))
        if result == 0:
            print(f'MongoDB OPEN at {ip}:27017')
    except:
        pass
    finally:
        s.close()

# Juga cek port lainnya
print()
for ip in ['172.18.0.2', '172.18.0.3', '172.18.0.4', '172.18.0.5', '172.18.0.6', '172.18.0.7', '172.18.0.8', '172.18.0.9']:
    for port in [27017, 7557, 7547, 7567, 8002, 3000, 8000]:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        result = s.connect_ex((ip, port))
        if result == 0:
            print(f'  OPEN: {ip}:{port}')
        s.close()
