import asyncio
import hashlib
import logging
import os
from pathlib import Path
import socket
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'upstream' / 'tg-ws-proxy'))
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from network import Network
from settings_codec import configure, decode, encode

class SettingsTest(unittest.TestCase):

    def test_preserves_existing_payload_and_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory) / 'profile'
            settings = profile / 'tdata' / 'settingss'
            settings.parent.mkdir(parents=True)
            payload = struct.pack('>ii', 6, 0)
            original = encode(payload, os.urandom(32))
            settings.write_bytes(original)
            configure(profile, 1443, 'ab' * 16)
            updated, _, _ = decode(settings.read_bytes())
            self.assertTrue(updated.startswith(payload))
            self.assertIn(('dd' + 'ab' * 16).encode('utf-16-be'), updated)
            self.assertEqual(settings.with_name('settingss.onegram-backup').read_bytes(), original)

    def test_corrupt_settings_remain_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            settings = profile / 'tdata' / 'settingss'
            settings.parent.mkdir()
            damaged = bytearray(encode(b'original', os.urandom(32)))
            damaged[30] ^= 1
            settings.write_bytes(damaged)
            with self.assertRaises(ValueError):
                configure(profile, 1443, 'ab' * 16)
            self.assertEqual(settings.read_bytes(), bytes(damaged))

class NetworkTest(unittest.TestCase):

    def test_start_authenticated_roundtrip_and_stop(self):
        from proxy.pool import ws_pool
        from proxy.stats import stats
        secret = os.urandom(16)
        payload = b'OneGram transport test'

        class Remote:

            def __init__(self):
                self.queue = asyncio.Queue()
                self.received = None

            async def send(self, data):
                if self.received is None:
                    material = data[8:56]
                    self.decoder = Cipher(algorithms.AES(material[:32]), modes.CTR(material[32:])).decryptor()
                    self.decoder.update(bytes(64))
                    reverse = material[::-1]
                    self.encoder = Cipher(algorithms.AES(reverse[:32]), modes.CTR(reverse[32:])).encryptor()
                    self.received = b''
                else:
                    self.received += self.decoder.update(data)
                    await self.queue.put(self.encoder.update(data=b'remote reply'))

            async def recv(self):
                return await self.queue.get()

            async def close(self):
                pass
        remote = Remote()

        async def get_remote(*args, **kwargs):
            return remote
        network = Network(0, secret.hex())
        with patch.object(ws_pool, 'warmup', new=lambda: asyncio.sleep(0)), patch.object(ws_pool, 'get', new=get_remote):
            network.start()
            try:
                init = bytearray(os.urandom(64))
                init[56:60] = b'\xee' * 4
                init[60:62] = struct.pack('<h', 2)
                material = bytes(init[8:56])
                outbound = Cipher(algorithms.AES(hashlib.sha256(material[:32] + secret).digest()), modes.CTR(material[32:])).encryptor()
                encrypted_init = outbound.update(bytes(init))
                init[56:] = encrypted_init[56:]
                reverse = material[::-1]
                inbound = Cipher(algorithms.AES(hashlib.sha256(reverse[:32] + secret).digest()), modes.CTR(reverse[32:])).decryptor()
                packet = struct.pack('<I', len(payload)) + payload
                with socket.create_connection(('127.0.0.1', network.port), timeout=10) as client:
                    client.sendall(bytes(init) + outbound.update(packet))
                    response = client.recv(64)
                    self.assertEqual(inbound.update(response), b'remote reply')
                    self.assertEqual(remote.received, packet)
                self.assertGreater(stats.connections_ws, 0)
            finally:
                network.stop()
            self.assertTrue(network.finished.is_set())
            self.assertIsNone(network.error)
            with socket.socket() as check:
                self.assertNotEqual(check.connect_ex(('127.0.0.1', network.port)), 0)
if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR)
    unittest.main()
