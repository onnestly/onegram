import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((ROOT / 'sources.lock.json').read_text(encoding='utf-8'))

def check():
    for name, expected in LOCK['desktop_overlay_sha256'].items():
        path = ROOT / 'overlays/desktop' / name
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise RuntimeError('Overlay checksum mismatch: ' + name)
    print('Overlay checksums OK')

def download(url, path, expected):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        pending = path.with_suffix(path.suffix + '.part')
        with urllib.request.urlopen(url, timeout=120) as response, pending.open('wb') as output:
            shutil.copyfileobj(response, output)
        with pending.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
                raise RuntimeError('Download checksum mismatch: ' + path.name)
        pending.replace(path)
    with path.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != expected:
            raise RuntimeError('File checksum mismatch: ' + path.name)

def desktop():
    destination = ROOT / 'desktop'
    if destination.exists():
        raise RuntimeError('desktop already exists; use a fresh checkout for bootstrap')
    subprocess.run(['git', 'init', str(destination)], check=True)
    subprocess.run(['git', '-C', str(destination), 'remote', 'add', 'origin', LOCK['desktop']['url']], check=True)
    subprocess.run(['git', '-C', str(destination), 'fetch', '--depth', '1', 'origin', LOCK['desktop']['commit']], check=True)
    subprocess.run(['git', '-C', str(destination), 'checkout', '--detach', 'FETCH_HEAD'], check=True)
    subprocess.run(['git', '-C', str(destination), 'submodule', 'update', '--init', '--recursive', '--depth', '1'], check=True)
    for source in (ROOT / 'overlays/desktop').rglob('*'):
        if source.is_file():
            target = destination / source.relative_to(ROOT / 'overlays/desktop')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

def android():
    downloads = ROOT / '.local/downloads'
    source = LOCK['android']
    download(source['url'], downloads / 'telegram-android.apk', source['sha256'])
    download(LOCK['apktool']['url'], downloads / 'apktool.jar', LOCK['apktool']['sha256'])
    (downloads / 'android-source.json').write_text(json.dumps(source, indent=2), encoding='utf-8')
    decoded = ROOT / '.local/android-decoded'
    if decoded.exists():
        raise RuntimeError('Android decoded directory already exists; refusing to overwrite it')
    import os
    java = Path(os.environ['JAVA_HOME']) / 'bin/java.exe'
    subprocess.run([str(java), '-Xmx1536m', '-jar', str(downloads/'apktool.jar'), 'd', str(downloads/'telegram-android.apk'), '-p', str(ROOT/'.local/apktool-framework'), '-o', str(decoded)], check=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--desktop', action='store_true')
    parser.add_argument('--android', action='store_true')
    args = parser.parse_args()
    check()
    if args.desktop: desktop()
    if args.android: android()
    if not (args.check or args.desktop or args.android): parser.print_help()

if __name__ == '__main__':
    main()
