import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime
from brand_client import make_icon, prepare_language, clear_presentation_resources, CopyIcons_FromIco, write_version_info_to_executable, load_version_info_from_text_file
ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / '.local' / 'build' / ('native-1.0.3-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
DIST = BUILD / 'output'
OUTPUT = DIST / 'OneGram'

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def main():
    native = json.loads((ROOT / '.local/desktop-build/Native-BUILD.json').read_text(encoding='utf-8'))
    binary = Path(native['binary']).resolve()
    if not binary.is_relative_to((ROOT / 'desktop/out').resolve()) or digest(binary) != native['binary_sha256']:
        raise RuntimeError('Source-built client is missing or changed; rebuild it first')
    if not {'mutual_streaks_with_history', 'channel_subscription_after_login', 'local_ignore_direct_stop', 'onegram_settings', 'native_login_channel_open', 'paper_boat_icon'}.issubset(native['features']):
        raise RuntimeError('Native client features are incomplete')
    for relative, expected in native['source_sha256'].items():
        source = (ROOT / 'desktop' / relative).resolve()
        if not source.is_relative_to((ROOT / 'desktop').resolve()) or digest(source) != expected:
            raise RuntimeError('Client source changed since compilation: ' + relative)
    BUILD.mkdir(parents=True, exist_ok=True)
    prepare_language(ROOT)
    icon = make_icon()
    icon_path = BUILD / 'onegram.ico'
    icon.save(icon_path, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    version = BUILD / 'version.txt'
    version.write_text("VSVersionInfo(ffi=FixedFileInfo(filevers=(1,0,3,0), prodvers=(1,0,3,0), mask=0x3f, flags=0, OS=0x40004, fileType=0x1, subtype=0, date=(0,0)), kids=[StringFileInfo([StringTable('040904B0',[StringStruct('CompanyName','OneGram'),StringStruct('FileDescription','OneGram'),StringStruct('FileVersion','1.0.3'),StringStruct('InternalName','OneGram'),StringStruct('OriginalFilename','OneGram.exe'),StringStruct('ProductName','OneGram'),StringStruct('ProductVersion','1.0.3'),StringStruct('LegalCopyright','Telegram Desktop contributors; OneGram modifications')])]),VarFileInfo([VarStruct('Translation',[1033,1200])])])", encoding='utf-8')
    environment = os.environ.copy()
    environment['PYTHONUSERBASE'] = str(ROOT / '.local/python-userbase')
    environment['PYTHONNOUSERSITE'] = '1'
    (ROOT / '.local/python-userbase').mkdir(exist_ok=True)
    environment['PYINSTALLER_CONFIG_DIR'] = str(ROOT / '.local' / 'cache' / 'pyinstaller')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--windowed', '--name', 'OneGram', '--icon', str(icon_path), '--version-file', str(version), '--paths', str(ROOT / 'upstream' / 'tg-ws-proxy'), '--collect-submodules', 'proxy', '--collect-data', 'certifi', '--add-data', str(ROOT / 'windows' / 'assets') + ';assets', '--workpath', str(BUILD / 'pyinstaller'), '--specpath', str(BUILD), '--distpath', str(DIST), str(ROOT / 'windows' / 'app.py')], cwd=ROOT, env=environment, check=True)
    shutil.copytree(ROOT / 'windows/assets', OUTPUT / 'assets')
    client = OUTPUT / 'client'
    client.mkdir(exist_ok=True)
    for path in binary.parent.rglob('*'):
        relative = path.relative_to(binary.parent)
        if any((part.casefold() in {'data', 'tdata', 'profile'} for part in relative.parts)):
            raise RuntimeError('Native build directory unexpectedly contains account data')
        if path.is_file() and path.suffix.lower() in {'.exe', '.dll', '.rcc', '.pak', '.bin', '.dat'}:
            destination = client / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    executable = client / 'OneGramClient.exe'
    os.replace(client / binary.name, executable)
    clear_presentation_resources(executable)
    CopyIcons_FromIco(str(executable), [str(icon_path)])
    write_version_info_to_executable(str(executable), load_version_info_from_text_file(str(version)))
    branding_report = {'native_source_branding': True, 'boat_pe_icons': True, 'binary_sha256': digest(executable)}
    (OUTPUT / 'BRANDING.json').write_text(json.dumps(branding_report, indent=2), encoding='utf-8')
    licenses = OUTPUT / 'licenses'
    licenses.mkdir(exist_ok=True)
    shutil.copy2(ROOT / 'desktop' / 'LICENSE', licenses / 'Telegram-Desktop-LICENSE.txt')
    shutil.copy2(ROOT / 'upstream' / 'tg-ws-proxy' / 'LICENSE', licenses / 'tg-ws-proxy-LICENSE.txt')
    subprocess.run([sys.executable, '-m', 'pip', 'freeze'], stdout=(BUILD / 'dependencies.txt').open('w'), check=True)
    shutil.copy2(BUILD / 'dependencies.txt', licenses / 'python-dependencies.txt')
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get('Name', 'unknown')
        for item in distribution.files or []:
            if any((part.lower().startswith(('license', 'copying', 'notice')) for part in item.parts)):
                path = Path(distribution.locate_file(item))
                if path.is_file() and path.suffix.lower() not in {'.py', '.pyc', '.pyd', '.dll', '.exe'} and path.resolve().is_relative_to(Path(distribution.locate_file('')).resolve()):
                    target = licenses / 'python' / name / Path(*item.parts[1:])
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target)
    for record in (OUTPUT / '_internal').rglob('RECORD'):
        if record.parent.name.endswith('.dist-info'): record.unlink()
    native_public = {key: value for key, value in native.items() if key != 'binary'}
    manifest = {'name': 'OneGram', 'version': '1.0.3', 'native_client': True, 'client': 'OneGram source-built Telegram Desktop', 'client_corresponding_source': 'https://github.com/telegramdesktop/tdesktop/tree/' + native['source_commit'], 'native_build': native_public, 'proxy_upstream_commit': subprocess.check_output(['git', '-c', 'safe.directory=' + (ROOT / 'upstream/tg-ws-proxy').as_posix(), '-C', str(ROOT / 'upstream/tg-ws-proxy'), 'rev-parse', 'HEAD'], text=True).strip(), 'proxy_changes': ['Reserve Cloudflare WSS routes enabled', 'Prefer HTTP2 /api for media', 'DC2 forced redirect removed'], 'behavior': 'Single entry point, in-process proxy, isolated portable profile, automatic local proxy settings'}
    (OUTPUT / 'BUILD.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (ROOT / '.local/build/latest-native-stage.json').write_text(json.dumps({'path': str(OUTPUT)}), encoding='utf-8')
    print(OUTPUT / 'OneGram.exe')
if __name__ == '__main__':
    main()
