from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys
from settings_codec import decode, encode, qbytes, qstring, read_qbytes

def tdf(body: bytes, version: int) -> bytes:
    stamp = struct.pack('<I', version)
    digest = hashlib.md5(body + struct.pack('<I', len(body)) + stamp + b'TDF$').digest()
    return b'TDF$' + stamp + body + digest

def unpack_tdf(raw: bytes) -> tuple[bytes, int]:
    if len(raw) < 24 or raw[:4] != b'TDF$':
        raise ValueError('Invalid language cache header')
    body = raw[8:-16]
    version, = struct.unpack_from('<I', raw, 4)
    if tdf(body, version) != raw:
        raise ValueError('Invalid language cache checksum')
    return (body, version)

def read_cache(raw: bytes, salt: bytes) -> tuple[bytes, int]:
    body, version = unpack_tdf(raw)
    encrypted, end = read_qbytes(body, 0)
    if end != len(body):
        raise ValueError('Unexpected language cache fields')
    payload, _, _ = decode(tdf(qbytes(salt) + qbytes(encrypted), version))
    serialized, end = read_qbytes(payload, 0)
    if end != len(payload):
        raise ValueError('Unexpected language cache payload')
    return (serialized, version)

def write_cache(serialized: bytes, salt: bytes, version: int) -> bytes:
    body, _ = unpack_tdf(encode(qbytes(serialized), salt, version))
    _, offset = read_qbytes(body, 0)
    encrypted, _ = read_qbytes(body, offset)
    return tdf(qbytes(encrypted), version)

def branded(value: bytes) -> bytes:
    text = value.decode('utf-8')
    services = []
    brand = '(?:Telegram|OneGram|Телеграм(?:м)?(?:е|а|у|ом)?)'
    products = '(?:Premium|Stars|Business|Passport|Gateway|Wallet|Gifts|FAQ|Features)'
    local_products = '(?:Зв[её]зд[а-яё]*|Премиум|Подар[а-яё]*|Бизнес[а-яё]*)'

    def protect(match):
        services.append(match[0].replace('OneGram', 'Telegram').replace('ONEGRAM', 'TELEGRAM'))
        return '\ue000' + str(len(services) - 1) + '\ue001'
    text = re.sub(brand + '\\s+' + products + '\\b|(?:' + products + '|' + local_products + ')\\s+' + brand, protect, text, flags=re.I)
    text = text.replace('Welcome to the official Telegram Desktop app.', 'Welcome to OneGram.')
    text = ''.join((part if re.match('(?:https?://|tg://|@)', part) else part.replace('Telegram Desktop', 'OneGram').replace('Telegram', 'OneGram').replace('TELEGRAM', 'ONEGRAM') for part in re.split('(https?://\\S+|tg://\\S+|@[A-Za-z0-9_]+)', text)))
    for index, service in enumerate(services):
        text = text.replace('\ue000' + str(index) + '\ue001', service)
    return text.encode('utf-8')

def brand_pack(data: bytes, directory: Path) -> bytes:
    offset = 0

    def field() -> bytes:
        nonlocal offset
        value, offset = read_qbytes(data, offset)
        return value

    def text() -> str:
        return field().decode('utf-16-be')

    def integer() -> int:
        nonlocal offset
        if offset + 4 > len(data):
            raise ValueError('Truncated language pack')
        value, = struct.unpack_from('>i', data, offset)
        offset += 4
        return value
    if text() != '#new' or integer() != 1:
        raise ValueError('Unsupported language pack version; original file preserved')
    identity, plural, name, native = [text() for _ in range(4)]
    integer()
    old_absolute, old_relative = (text(), text())
    field()
    count = integer()
    if not 0 <= count <= 100000:
        raise ValueError('Invalid language pack size')
    entries = []
    for _ in range(count):
        key, value = (field(), field())
        value = b'https://t.me/TelegramTips' if key == b'lng_telegram_features_url' else branded(value)
        entries.append((key, value))
    if not any((key == b'lng_telegram_features_url' for key, _ in entries)):
        entries.append((b'lng_telegram_features_url', b'https://t.me/TelegramTips'))
    base = field()
    if offset != len(data):
        raise ValueError('Unexpected language pack fields')
    if base:
        base = brand_pack(base, directory)
    code = (plural or identity).lstrip('#').split('_')[0].split('-')[0]
    code = code if re.fullmatch('[a-z]{2,3}', code) else 'en'
    locale = code + '_' + ('US' if code == 'en' else code.upper())
    path = directory / f'onegram_{locale}.strings'
    content = ('\n'.join((json.dumps(key.decode('utf-8')) + ' = ' + json.dumps(value.decode('utf-8'), ensure_ascii=False) + ';' for key, value in entries)) + '\n').encode('utf-8')
    result = qstring('#new') + struct.pack('>i', 1)
    result += b''.join((qstring(value) for value in ('#custom', locale, name, native)))
    result += struct.pack('>i', 0) + qstring(str(path)) + qstring(path.name) + qbytes(content)
    result += struct.pack('>i', len(entries))
    for key, value in entries:
        result += qbytes(key) + qbytes(value)
    result += qbytes(base)
    path.write_bytes(content)
    return result

def rebrand_language(profile: Path, settings_payload: bytes, salt: bytes) -> int:
    directory = profile / 'tdata'
    marker = struct.pack('>I', 78)
    offset = 0
    paths = set()
    changed = 0
    while (offset := settings_payload.find(marker, offset)) >= 0:
        start = offset + 4
        offset = start
        if start + 8 > len(settings_payload):
            continue
        number, = struct.unpack_from('>Q', settings_payload, start)
        stem = f'{number:016X}'[::-1]
        path = directory / (stem + 's')
        if path in paths or not path.is_file():
            continue
        paths.add(path)
        raw = path.read_bytes()
        try:
            serialized, version = read_cache(raw, salt)
        except ValueError:
            continue
        if not serialized.startswith(qstring('#new')):
            continue
        replacement = brand_pack(serialized, directory)
        backup = path.with_name(path.name + '.onegram-backup')
        if not backup.exists():
            backup.write_bytes(raw)
        temporary = path.with_name(path.name + '.onegram-new')
        temporary.write_bytes(write_cache(replacement, salt, version))
        os.replace(temporary, path)
        changed += 1
    return changed

def ensure_language(profile: Path, payload: bytes, salt: bytes, version: int) -> bytes:
    if rebrand_language(profile, payload, salt):
        return b''
    assets = Path(sys._MEIPASS) / 'assets' if getattr(sys, 'frozen', False) else Path(__file__).parent / 'assets'
    entries = json.loads((assets / 'branding-en.json').read_text(encoding='utf-8'))
    serialized = qstring('#new') + struct.pack('>i', 1)
    serialized += b''.join((qstring(value) for value in ('en', 'en', 'English', 'English')))
    serialized += struct.pack('>i', 0) + qstring('') + qstring('') + qbytes(b'')
    serialized += struct.pack('>i', len(entries))
    for key, value in entries.items():
        serialized += qbytes(key.encode('utf-8')) + qbytes(value.encode('utf-8'))
    serialized += qbytes(b'')
    directory = profile / 'tdata'
    result = brand_pack(serialized, directory)
    while True:
        number = int.from_bytes(os.urandom(8), 'little')
        path = directory / (f'{number:016X}'[::-1] + 's')
        if number and (not path.exists()):
            break
    path.write_bytes(write_cache(result, salt, version))
    return struct.pack('>IQ', 78, number)
