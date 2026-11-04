from __future__ import annotations
import hashlib
import hmac
import json
import os
from pathlib import Path
import struct
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
VERSION = 7003003

def qbytes(value: bytes) -> bytes:
    return struct.pack('>I', len(value)) + value

def qstring(value: str) -> bytes:
    return qbytes(value.encode('utf-16-be'))

def read_qbytes(data: bytes, offset: int) -> tuple[bytes, int]:
    if offset + 4 > len(data):
        raise ValueError('Truncated settings field')
    size, = struct.unpack_from('>I', data, offset)
    offset += 4
    if size == 4294967295:
        return (b'', offset)
    if size > len(data) - offset:
        raise ValueError('Invalid settings field length')
    return (data[offset:offset + size], offset + size)

def local_aes(key: bytes, message_key: bytes) -> tuple[bytes, bytes]:
    x = 8
    a = hashlib.sha1(message_key + key[x:x + 32]).digest()
    b = hashlib.sha1(key[x + 32:x + 48] + message_key + key[x + 48:x + 64]).digest()
    c = hashlib.sha1(key[x + 64:x + 96] + message_key).digest()
    d = hashlib.sha1(message_key + key[x + 96:x + 128]).digest()
    return (a[:8] + b[8:20] + c[4:16], a[8:20] + b[:8] + c[16:20] + d[:8])

def xor(a: bytes, b: bytes) -> bytes:
    return bytes((x ^ y for x, y in zip(a, b)))

def ige(data: bytes, key: bytes, iv: bytes, *, decrypt: bool=False) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB())
    ctx = cipher.decryptor() if decrypt else cipher.encryptor()
    previous_cipher, previous_plain = (iv[:16], iv[16:])
    out = bytearray()
    for offset in range(0, len(data), 16):
        block = data[offset:offset + 16]
        if decrypt:
            result = xor(ctx.update(xor(block, previous_plain)), previous_cipher)
            previous_cipher, previous_plain = (block, result)
        else:
            result = xor(ctx.update(xor(block, previous_cipher)), previous_plain)
            previous_cipher, previous_plain = (result, block)
        out.extend(result)
    ctx.finalize()
    return bytes(out)

def settings_key(salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac('sha1', b'', salt, 4, 256)

def encode(payload: bytes, salt: bytes, version: int=VERSION) -> bytes:
    plain = struct.pack('<I', len(payload) + 4) + payload
    plain += os.urandom(-len(plain) % 16)
    message_key = hashlib.sha1(plain).digest()[:16]
    aes_key, iv = local_aes(settings_key(salt), message_key)
    encrypted = message_key + ige(plain, aes_key, iv)
    body = qbytes(salt) + qbytes(encrypted)
    version_bytes = struct.pack('<I', version)
    digest = hashlib.md5(body + struct.pack('<I', len(body)) + version_bytes + b'TDF$').digest()
    return b'TDF$' + version_bytes + body + digest

def decode(raw: bytes) -> tuple[bytes, bytes, int]:
    if len(raw) < 24 or raw[:4] != b'TDF$':
        raise ValueError('Unsupported settings file')
    body, digest = (raw[8:-16], raw[-16:])
    expected = hashlib.md5(body + struct.pack('<I', len(body)) + raw[4:8] + b'TDF$').digest()
    if not hmac.compare_digest(expected, digest):
        raise ValueError('Settings checksum mismatch; original file preserved')
    salt, offset = read_qbytes(body, 0)
    encrypted, offset = read_qbytes(body, offset)
    if offset != len(body) or len(salt) != 32 or len(encrypted) < 32 or len(encrypted) % 16:
        raise ValueError('Invalid encrypted settings')
    message_key = encrypted[:16]
    aes_key, iv = local_aes(settings_key(salt), message_key)
    plain = ige(encrypted[16:], aes_key, iv, decrypt=True)
    if not hmac.compare_digest(hashlib.sha1(plain).digest()[:16], message_key):
        raise ValueError('Settings authentication mismatch; original file preserved')
    length, = struct.unpack_from('<I', plain)
    if length < 4 or length > len(plain) or length <= len(plain) - 16:
        raise ValueError('Invalid settings payload')
    return (plain[4:length], salt, struct.unpack_from('<I', raw, 4)[0])

def proxy_block(port: int, secret: str, enabled: bool=True) -> bytes:
    if not 1 <= port <= 65535 or len(bytes.fromhex(secret)) != 16:
        raise ValueError('Invalid local proxy configuration')
    return struct.pack('>6i', 79, 5, 1, 1, 1 if enabled else 2, 0) + struct.pack('>i', 1027) + qstring('127.0.0.1') + struct.pack('>i', port) + qstring('') + qstring('dd' + secret) + struct.pack('>2i', 12, 0)

def configure(profile: Path, port: int, secret: str, enabled: bool=True) -> None:
    directory = profile / 'tdata'
    directory.mkdir(parents=True, exist_ok=True)
    experimental = directory / 'experimental_options.json'
    options = json.loads(experimental.read_text(encoding='utf-8')) if experimental.exists() else {}
    if not isinstance(options, dict):
        raise ValueError('Invalid experimental options; original file preserved')
    options['skip-url-scheme-register'] = True
    experimental.write_text(json.dumps(options, indent=2), encoding='utf-8')
    target = directory / 'settingss'
    payload, salt, version = (b'', os.urandom(32), VERSION)
    if target.exists():
        raw = target.read_bytes()
        payload, salt, version = decode(raw)
        (directory / 'settingss.onegram-backup').write_bytes(raw)
    elif any(((directory / name).exists() for name in ('settings0', 'settings1'))):
        raise ValueError('Legacy profile requires migration; original profile preserved')
    if not target.exists():
        downloads = profile.parent / 'downloads'
        downloads.mkdir(exist_ok=True)
        payload += struct.pack('>i', 21) + qstring(downloads.as_posix() + '/')
    from branding import ensure_language
    language_key = ensure_language(profile, payload, salt, version)
    result = encode(payload + proxy_block(port, secret, enabled) + language_key, salt, version)
    temporary = directory / 'settingss.onegram-new'
    temporary.write_bytes(result)
    os.replace(temporary, target)
