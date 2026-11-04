import json
from pathlib import Path
import re
import sys
import uuid
from brand_client import make_icon
from io import BytesIO
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'windows'))
from branding import branded

def write_changed(path, data):
    if not path.exists() or path.read_bytes() != data:
        path.write_bytes(data)

def main():
    lang = ROOT / 'desktop/Telegram/Resources/langs/lang.strings'
    source = lang.read_text(encoding='utf-8')
    count = 0

    def replace(match):
        nonlocal count
        value = json.loads('"' + match[2] + '"')
        updated = {'lng_settings_faq': 'Telegram FAQ', 'lng_settings_features': 'Telegram Features', 'lng_telegram_features_url': 'https://t.me/TelegramTips'}.get(match[1], branded(value.encode('utf-8')).decode('utf-8'))
        if updated != value:
            count += 1
        return '"' + match[1] + '" = ' + json.dumps(updated, ensure_ascii=False) + ';'
    updated = re.sub('"([^"\\n]+)"\\s*=\\s*"((?:\\\\.|[^"\\\\])*)"\\s*;', replace, source)
    write_changed(lang, updated.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8'))
    version = ROOT / 'desktop/Telegram/SourceFiles/core/version.h'
    text = version.read_text(encoding='utf-8')
    app_id = '{' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'https://t.me/On3Gram/OneGram/windows')).upper() + '}'
    for key, value in [('AppNameOld', 'OneGram'), ('AppName', 'OneGram'), ('AppFile', 'OneGramClient'), ('AppId', app_id)]:
        text, changed = re.subn('(constexpr auto ' + key + ' = ")[^"]*("_cs;)', lambda match: match[1] + value + match[2], text)
        if changed != 1:
            raise RuntimeError('Missing native application identity: ' + key)
    write_changed(version, text.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8'))
    launcher = ROOT / 'desktop/Telegram/SourceFiles/core/launcher.cpp'
    text = launcher.read_text(encoding='utf-8').replace('QApplication::setApplicationName(u"TelegramDesktop"_q)', 'QApplication::setApplicationName(u"OneGram"_q)')
    write_changed(launcher, text.replace('\r\n', '\n').replace('\n', '\r\n').encode('utf-8'))
    for name, margin in [('logo_256.png', 8), ('logo_256_no_margin.png', 0)]:
        buffer = BytesIO()
        make_icon(256, margin).save(buffer, 'PNG', optimize=True)
        write_changed(ROOT / 'desktop/Telegram/Resources/art' / name, buffer.getvalue())
    print('Native OneGram branding prepared; changed default translations:', count)
if __name__ == '__main__':
    main()
