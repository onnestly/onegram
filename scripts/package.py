from pathlib import Path
import json
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    stage = Path(json.loads((ROOT/'.local/build/latest-native-stage.json').read_text(encoding='utf-8'))['path']).resolve()
    if not stage.is_relative_to((ROOT/'.local/build').resolve()):
        raise RuntimeError('Unexpected stage directory')
    version = json.loads((stage/'BUILD.json').read_text(encoding='utf-8'))['version']
    target = ROOT/'dist'/('OneGram-Windows-x64-'+version+'.zip')
    target.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as output:
        for path in sorted(stage.rglob('*')):
            relative = path.relative_to(stage)
            if path.is_file() and relative.parts[0] != 'data': output.write(path,Path('OneGram')/relative)
    with zipfile.ZipFile(target) as archive:
        if archive.testzip() is not None: raise RuntimeError('ZIP integrity check failed')
    print(target)

if __name__ == '__main__':
    main()
