import os
from pathlib import Path
import shutil
ROOT = Path(__file__).resolve().parents[1]

def main():
    cwd = Path.cwd().resolve()
    expected = (ROOT / 'Libraries/win64/breakpad/src').resolve()
    if cwd != expected:
        raise RuntimeError('Unexpected Breakpad environment directory')
    compiler = shutil.which('cl.exe')
    if not compiler or '/hostx64/x64/' not in Path(compiler).as_posix().lower():
        raise RuntimeError('An active x64 MSVC environment is required')
    names = {'INCLUDE', 'LIB', 'LIBPATH', 'PATH', 'PATHEXT', 'SYSTEMROOT', 'TEMP', 'TMP', 'VSLANG', 'PYTHONUTF8'}
    environment = {key.upper(): value for key, value in os.environ.items() if key.upper() in names}
    for key in ('INCLUDE', 'LIB', 'PATH', 'SYSTEMROOT', 'TEMP', 'TMP'):
        if not environment.get(key):
            raise RuntimeError('Missing MSVC environment variable: ' + key)
    block = ''.join((key + '=' + value + '\x00' for key, value in sorted(environment.items()))) + '\x00'
    for configuration in ('Debug_x64', 'Release_x64'):
        output = cwd / 'out' / configuration
        output.mkdir(parents=True, exist_ok=True)
        (output / 'environment.x64').write_text(block, encoding='utf-8')
    print('Breakpad custom x64 compiler environment prepared')
if __name__ == '__main__':
    main()
