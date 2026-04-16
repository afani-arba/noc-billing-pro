import socket
msg = b"<14>Mar 17 00:00:00 nocsentinel dns,packet query: www.google.com IN A"
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.sendto(msg, ("10.254.254.241", 5142))
print("Packet sent to 10.254.254.241:5142")
