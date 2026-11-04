import os
from pathlib import Path
import struct
import tempfile
import unittest
from branding import brand_pack, branded, read_cache, rebrand_language, write_cache
from settings_codec import qbytes, qstring

def sample_pack() -> bytes:
    entries = [(b'lng_language_name', 'Русский'.encode()), (b'lng_intro_about', 'Добро пожаловать в Telegram Desktop.'.encode()), (b'lng_help', b'Open Telegram https://t.me/TelegramTips @Telegram')]
    value = qstring('#new') + struct.pack('>i', 1)
    value += b''.join((qstring(item) for item in ('ru', 'ru', 'Russian', 'Русский')))
    value += struct.pack('>i', 123) + qstring('') + qstring('') + qbytes(b'')
    value += struct.pack('>i', len(entries))
    for key, text in entries:
        value += qbytes(key) + qbytes(text)
    return value + qbytes(b'')

class BrandingTest(unittest.TestCase):

    def test_official_products_keep_telegram_names(self):
        value = 'Telegram: Telegram Premium, OneGram Premium, Звёзды Telegram и Звёзды OneGram'
        expected = 'OneGram: Telegram Premium, Telegram Premium, Звёзды Telegram и Звёзды Telegram'
        self.assertEqual(branded(value.encode()).decode(), expected)

    def test_official_help_labels(self):
        self.assertEqual(branded(b'OneGram FAQ / OneGram Features'), b'Telegram FAQ / Telegram Features')

    def test_links_and_handles_are_preserved(self):
        self.assertEqual(branded(b'Telegram Desktop https://t.me/TelegramTips @Telegram'), b'OneGram https://t.me/TelegramTips @Telegram')

    def test_russian_pack_retains_language_and_plural_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            result = brand_pack(sample_pack(), Path(directory))
            self.assertIn(qstring('#custom'), result)
            self.assertIn(qstring('ru_RU'), result)
            self.assertIn('Добро пожаловать в OneGram.'.encode(), result)
            self.assertIn('Русский'.encode('utf-16-be'), result)
            source = Path(directory, 'onegram_ru_RU.strings').read_text(encoding='utf-8')
            self.assertIn('https://t.me/TelegramTips', source)

    def test_cache_migration_preserves_original_backup(self):
        with tempfile.TemporaryDirectory() as directory:
            profile = Path(directory)
            cache_dir = profile / 'tdata'
            cache_dir.mkdir()
            salt = os.urandom(32)
            number = 1311768467463790320
            path = cache_dir / (f'{number:016X}'[::-1] + 's')
            original = write_cache(sample_pack(), salt, 7003003)
            path.write_bytes(original)
            payload = struct.pack('>IQ', 78, number)
            self.assertEqual(rebrand_language(profile, payload, salt), 1)
            result, version = read_cache(path.read_bytes(), salt)
            self.assertIn('Добро пожаловать в OneGram.'.encode(), result)
            self.assertEqual(version, 7003003)
            self.assertIn(b'https://t.me/TelegramTips', result)
            self.assertEqual(path.with_name(path.name + '.onegram-backup').read_bytes(), original)
            self.assertEqual(rebrand_language(profile, payload, salt), 1)
            self.assertEqual(path.with_name(path.name + '.onegram-backup').read_bytes(), original)
if __name__ == '__main__':
    unittest.main()
