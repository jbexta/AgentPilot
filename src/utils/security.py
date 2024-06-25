import base64
import os

# import keyring as kr
from Crypto.Cipher import AES
from Crypto.Hash import SHA3_512
from Crypto.Protocol.KDF import scrypt
from Crypto.Random import get_random_bytes
from tqdm.auto import tqdm

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import padding
import os


def encrypt_string(plain_text, key):
    key = key.ljust(32)[:32].encode('utf-8')
    iv = os.urandom(16)

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    encryptor = cipher.encryptor()

    padder = padding.PKCS7(algorithms.AES.block_size).padder()
    padded_data = padder.update(plain_text.encode('utf-8')) + padder.finalize()

    encrypted_text = encryptor.update(padded_data) + encryptor.finalize()

    result = iv + encrypted_text
    return base64.b64encode(result).decode('utf-8')


def decrypt_string(encrypted_text, key):
    key = key.ljust(32)[:32].encode('utf-8')

    encrypted_text = base64.b64decode(encrypted_text)

    iv = encrypted_text[:16]
    encrypted_data = encrypted_text[16:]

    cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
    decryptor = cipher.decryptor()

    decrypted_padded_data = decryptor.update(encrypted_data) + decryptor.finalize()

    unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
    decrypted_data = unpadder.update(decrypted_padded_data) + unpadder.finalize()

    return decrypted_data.decode('utf-8')


# def test_keyring():
#     # encrypt("AgentPilot", "/home/jb/PycharmProjects/AgentPilot/data.db.old")
#     decrypt("AgentPilot", "/home/jb/PycharmProjects/AgentPilot/data.db.old.aes")
#     # # kr.set_password("AgentPilot","usr","Geeks@123")
#     # pw = kr.get_password("AgentPilot","usr")
#     # print(pw)
#     # return pw


buffer_size = 65536  # 64Kb


def generate_salt():
    return get_random_bytes(32)


def get_salt_from_file(input_file_path):
    input_file = open(input_file_path, "rb")
    return input_file.read(32)


def generate_AES256_key(passwd, salt):
    return scrypt(passwd, salt, 32, N=2**20, r=8, p=1)


def check_password(passwd, input_file_path):
    input_file = open(input_file_path, "rb")
    bytes_temp = input_file.read(112)
    hashed_pwd = bytes_temp[48:112]
    salt = get_salt_from_file(input_file_path)

    return SHA3_512.new(data=passwd.encode("utf-8")).update(salt).digest() == hashed_pwd


def encrypt_file(key, passwd, salt, input_file_path):
    hashed_passwd = SHA3_512.new(data=passwd.encode("utf-8"))
    hashed_passwd.update(salt)
    hashed_passwd = hashed_passwd.digest()

    input_file = open(input_file_path, "rb")
    output_file = open(input_file_path + ".aes", "wb")

    cipher_encrypt = AES.new(key, AES.MODE_CFB)

    output_file.write(salt)  # 32 bytes
    output_file.write(cipher_encrypt.iv)  # 16 bytes
    output_file.write(hashed_passwd)  # 64 bytes

    # Progress bar
    file_size = os.path.getsize(input_file_path)
    pbar = tqdm(total=file_size, unit="B", unit_scale=True, desc="Encrypting")

    buffer = input_file.read(buffer_size)
    pbar.update(len(buffer))
    while len(buffer) > 0:
        ciphered_bytes = cipher_encrypt.encrypt(buffer)
        output_file.write(ciphered_bytes)
        buffer = input_file.read(buffer_size)
        pbar.update(len(buffer))

    input_file.close()
    output_file.close()
    # shred_file(input_file_path)
    os.remove(input_file_path)


def encrypt(passwd, input_file_path):
    print("Generating key from password...")
    salt = generate_salt()
    key = generate_AES256_key(passwd, salt)

    print(f"Encrypting {input_file_path}")
    encrypt_file(key, passwd, salt, input_file_path)
    return True


def decrypt_key(key, input_file_path):
    input_file = open(input_file_path, "rb")

    bytes_temp = input_file.read(112)
    iv = bytes_temp[32:48]

    output_file = open(input_file_path[:-4], "wb")

    cipher_decrypt = AES.new(key, AES.MODE_CFB, iv=iv)

    # Progress bar
    file_size = os.path.getsize(input_file_path) - 112
    pbar = tqdm(total=file_size, unit="B", unit_scale=True, desc="Decrypting")

    buffer = input_file.read(buffer_size)
    pbar.update(len(buffer))
    while len(buffer) > 0:
        decrypted_bytes = cipher_decrypt.decrypt(buffer)
        output_file.write(decrypted_bytes)
        buffer = input_file.read(buffer_size)
        pbar.update(len(buffer))

    input_file.close()
    output_file.close()
    os.remove(input_file_path)


def decrypt(passwd, input_file_path):
    print("Checking password...")
    if not check_password(passwd, input_file_path):
        return False

    print("Generating key from password...")
    salt = get_salt_from_file(input_file_path)
    key = generate_AES256_key(passwd, salt)

    print(f"Decrypting {input_file_path}")
    decrypt_key(key, input_file_path)
    return True
