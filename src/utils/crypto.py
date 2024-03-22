import socket
from itertools import cycle

from noise.connection import NoiseConnection


# def noise_receive():
#     s = socket.socket()
#     s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#     s.bind(('localhost', 2000))
#     s.listen(1)
#
#     conn, addr = s.accept()
#     print('Accepted connection from', addr)
#
#     noise = NoiseConnection.from_name(b'Noise_NN_25519_ChaChaPoly_SHA256')
#     noise.set_as_responder()
#     noise.start_handshake()
#
#     # Perform handshake. Break when finished
#     for action in cycle(['receive', 'send']):
#         if noise.handshake_finished:
#             break
#         elif action == 'send':
#             ciphertext = noise.write_message()
#             conn.sendall(ciphertext)
#         elif action == 'receive':
#             data = conn.recv(2048)
#             plaintext = noise.read_message(data)
#
#     # Endless loop "echoing" received data
#     while True:
#         data = conn.recv(2048)
#         if not data:
#             break
#         received = noise.decrypt(data)
#         conn.sendall(noise.encrypt(received))
#
