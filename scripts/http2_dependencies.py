import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile
ROOT = Path(__file__).resolve().parents[1]

def dependencies(platform='android'):
    folder = ROOT / '.local/downloads/http2'
    folder.mkdir(parents=True, exist_ok=True)
    result = []
    for item in json.loads((ROOT / 'android-module/http2-dependencies.json').read_text()):
        if item.get('platform', platform) != platform:
            continue
        path = folder / f'{item['name']}-{item['version']}.{item['extension']}'
        if not path.exists():
            pending = path.with_suffix(path.suffix + '.tmp')
            with urllib.request.urlopen(item['url'], timeout=45) as source:
                pending.write_bytes(source.read(8 * 1024 * 1024))
            if hashlib.sha256(pending.read_bytes()).hexdigest() != item['sha256']:
                raise RuntimeError('Dependency checksum mismatch: ' + path.name)
            pending.replace(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise RuntimeError('Dependency checksum mismatch: ' + path.name)
        if item['extension'] == 'aar':
            jar = path.with_suffix('.jar')
            with zipfile.ZipFile(path) as archive:
                jar.write_bytes(archive.read('classes.jar'))
        else:
            jar = path
        if platform == 'android':
            roots = list((ROOT / '.local/android-decoded').glob('smali*'))
            filtered = folder / (jar.stem + '-onegram.jar')
            with zipfile.ZipFile(jar) as source, zipfile.ZipFile(filtered, 'w', zipfile.ZIP_DEFLATED) as target:
                for entry in source.infolist():
                    if entry.filename.endswith('.class') and any(((root / (entry.filename[:-6] + '.smali')).is_file() for root in roots)):
                        continue
                    target.writestr(entry, source.read(entry))
            jar = filtered
        result.append(jar)
    return result
if __name__ == '__main__':
    for path in dependencies():
        print(path)
