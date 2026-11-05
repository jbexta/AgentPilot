"""A local HTTPS front for a Website project's plain HTTP server.

Dev servers such as ``php -S`` only speak HTTP, while sites that check
their origin or set secure cookies expect HTTPS. The proxy terminates TLS
with a self-signed certificate for the local hosts and forwards the raw
bytes, so the Host header and everything else arrive unchanged.
"""

import asyncio
import datetime
import ipaddress
import os
import socket
import ssl
from functools import partial

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from utils.filesystem import get_application_path

LOCAL_HOSTS = ('127.0.0.1', 'localhost')


def free_port():
    """A local port nothing is listening on."""
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def local_certificate():
    """Paths of the certificate and key for the local hosts, made once."""
    folder = os.path.join(get_application_path(), 'certs')
    cert_path = os.path.join(folder, 'localhost.pem')
    key_path = os.path.join(folder, 'localhost-key.pem')
    if os.path.isfile(cert_path) and os.path.isfile(key_path):
        return cert_path, key_path

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'localhost')])
    now = datetime.datetime.now(datetime.timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=3650))
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName('localhost'),
            x509.IPAddress(ipaddress.ip_address('127.0.0.1')),
        ]), critical=False)
        .sign(key, hashes.SHA256())
    )

    os.makedirs(folder, exist_ok=True)
    with open(key_path, 'wb') as file:
        file.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
    with open(cert_path, 'wb') as file:
        file.write(certificate.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


async def serve_https(port, target_port):
    """Serve HTTPS on *port*, forwarding to HTTP on *target_port*.

    Open connections end when the target server stops, so closing the
    returned server is all the cleanup needed.
    """
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(*local_certificate())
    return await asyncio.start_server(
        partial(_forward, target_port), '127.0.0.1', port, ssl=context,
    )


async def _forward(target_port, client_reader, client_writer):
    try:
        server_reader, server_writer = await asyncio.open_connection(
            '127.0.0.1', target_port,
        )
    except OSError:
        client_writer.close()
        return
    await asyncio.gather(
        _pipe(client_reader, server_writer),
        _pipe(server_reader, client_writer),
    )


async def _pipe(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except OSError:
        pass  # either side hanging up mid-stream is routine
    finally:
        writer.close()
