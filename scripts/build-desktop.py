import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'
DESKTOP = ROOT / 'desktop'

def private_command(command, environment, secret):
    process = subprocess.Popen(command, cwd=DESKTOP, env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace')
    for line in process.stdout:
        print(line.replace(secret, '[redacted]').replace(secret.upper(), '[redacted]'), end='', flush=True)
    code = process.wait()
    if code:
        raise subprocess.CalledProcessError(code, command)

def sha256_file(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def toolchain_environment():
    vs_root = Path(os.environ.get('ONEGRAM_VS_ROOT', str(LOCAL / 'vs-buildtools')))
    candidate = vs_root / 'VC/Auxiliary/Build/vcvars64.bat'
    arguments = '-vcvars_ver=14.44'
    if not candidate.exists():
        candidate = vs_root / 'Common7/Tools/VsDevCmd.bat'
        arguments = '-arch=x64 -host_arch=x64 -vcvars_ver=14.44'
    if not candidate.exists():
        raise RuntimeError('Microsoft C++ Build Tools is not installed. Set ONEGRAM_VS_ROOT to the Visual Studio Build Tools directory.')
    command = f'cmd.exe /u /d /s /c ""{candidate}" {arguments} >nul && set"'
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-16-le', errors='replace')
    if result.returncode:
        raise RuntimeError('Cannot activate the MSVC toolchain: ' + result.stderr.strip()[:1200])
    env = os.environ.copy()
    for line in result.stdout.splitlines():
        if '=' in line and (not line.startswith('=')):
            key, value = line.split('=', 1)
            env[key.upper()] = value
    env['PLATFORM'] = 'x64'
    env['PATH'] = str(Path(sys.executable).parent) + os.pathsep + env['PATH']
    env['TEMP'] = env['TMP'] = str(LOCAL / 'tmp')
    cmake_tools = vs_root / 'Common7/IDE/CommonExtensions/Microsoft/CMake'
    for folder in (cmake_tools / 'CMake/bin', cmake_tools / 'Ninja'):
        if folder.exists():
            env['PATH'] = str(folder) + os.pathsep + env['PATH']
    env['CMAKE_BUILD_PARALLEL_LEVEL'] = '2'
    env['_CL_'] = (env.get('_CL_', '') + ' /MP1').strip()
    env['CARGO_BUILD_JOBS'] = '2'
    env['VSLANG'] = '1033'
    for key, relative in {'PIP_CACHE_DIR': 'pip-cache', 'XDG_CACHE_HOME': 'cache', 'NUGET_PACKAGES': 'cache/nuget', 'NUGET_HTTP_CACHE_PATH': 'cache/nuget-http'}.items():
        folder = LOCAL / relative
        folder.mkdir(parents=True, exist_ok=True)
        env[key] = str(folder)
    count = int(env.get('GIT_CONFIG_COUNT', '0'))
    for repository in (DESKTOP, DESKTOP / 'cmake', DESKTOP / 'Telegram/lib_base'):
        env[f'GIT_CONFIG_KEY_{count}'] = 'safe.directory'
        env[f'GIT_CONFIG_VALUE_{count}'] = repository.as_posix()
        count += 1
    env[f'GIT_CONFIG_KEY_{count}'] = 'http.version'
    env[f'GIT_CONFIG_VALUE_{count}'] = 'HTTP/1.1'
    count += 1
    env['GIT_CONFIG_COUNT'] = str(count)
    return env

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', default='Telegram', help='Optional native target for an incremental compile check')
    parser.add_argument('--prepare', action='store_true', help='Build pinned upstream libraries first')
    args = parser.parse_args()
    credentials = {'api_id': 30464785, 'api_hash': '7cdd4892831f5b192b1ca18f767c69e3'}
    api_id, api_hash = (int(credentials['api_id']), credentials['api_hash'])
    if api_id <= 0 or not re.fullmatch('[a-fA-F0-9]{32}', api_hash):
        raise RuntimeError('Invalid local Telegram API application credentials')
    environment = toolchain_environment()
    work = LOCAL / 'desktop-build'
    work.mkdir(parents=True, exist_ok=True)
    seed = work / 'api.cmake'
    seed.write_text('set(TDESKTOP_API_ID "$ENV{ONEGRAM_DESKTOP_API_ID}" CACHE STRING "" FORCE)\nset(TDESKTOP_API_HASH "$ENV{ONEGRAM_DESKTOP_API_HASH}" CACHE STRING "" FORCE)\n', encoding='utf-8')
    if args.prepare:
        for relative in ('ThirdParty', 'Libraries', 'Libraries/win64'):
            folder = ROOT / relative
            if folder.exists():
                if folder.is_symlink() or folder.is_junction() or (not folder.resolve().is_relative_to(ROOT.resolve())):
                    raise RuntimeError('Unexpected dependency directory: ' + str(folder))
                for child in folder.iterdir():
                    if child.is_symlink() or child.is_junction():
                        raise RuntimeError('Refusing to rebuild through a linked dependency directory: ' + str(child))
        subprocess.run([sys.executable, str(DESKTOP / 'Telegram/build/prepare/prepare.py'), 'skip-release', 'silent'], cwd=DESKTOP, env=environment, check=True)
    environment['ONEGRAM_DESKTOP_API_ID'] = str(api_id)
    environment['ONEGRAM_DESKTOP_API_HASH'] = api_hash
    subprocess.run([sys.executable, str(ROOT / 'scripts/prepare-desktop-branding.py')], check=True)
    cmake = shutil.which('cmake', path=environment['PATH'])
    if not cmake:
        raise RuntimeError('CMake is missing from the configured Microsoft toolchain')
    environment['QT'] = '6.11.2'
    build = DESKTOP / 'out/onegram-ninja'
    private_command([cmake, '-S', str(DESKTOP), '-B', str(build), '-G', 'Ninja Multi-Config', '-C', str(seed), '-DCMAKE_CONFIGURATION_TYPES=Debug', '-DCMAKE_BUILD_TYPE=Debug', '-DDESKTOP_APP_DISABLE_AUTOUPDATE=ON', '-Werror=dev', '-Werror=deprecated', '--warn-uninitialized'], environment, api_hash)
    private_command([cmake, '--build', str(build), '--config', 'Debug', '--target', args.target, '--parallel', os.environ.get('ONEGRAM_BUILD_JOBS', '2')], environment, api_hash)
    if args.target != 'Telegram':
        print('Native compile check completed:', args.target)
        return
    binary = build / 'Debug/Telegram.exe'
    if not binary.is_file():
        raise RuntimeError('Native client output is missing')
    sources = list((DESKTOP / 'Telegram/SourceFiles/data/components').glob('onegram_*'))
    sources += [DESKTOP / path for path in ('Telegram/SourceFiles/ui/unread_badge.cpp', 'Telegram/SourceFiles/history/view/history_view_top_bar_widget.cpp', 'Telegram/SourceFiles/dialogs/ui/dialogs_layout.cpp', 'Telegram/SourceFiles/dialogs/ui/dialogs_message_view.h', 'Telegram/SourceFiles/core/launcher.cpp', 'Telegram/SourceFiles/dialogs/dialogs_widget.cpp', 'Telegram/SourceFiles/data/components/onegram_streaks.h', 'Telegram/SourceFiles/window/window_session_controller.cpp', 'Telegram/SourceFiles/core/version.h', 'Telegram/Resources/langs/lang.strings')]
    sources += [DESKTOP / 'Telegram/SourceFiles' / relative for relative in ['apiwrap.cpp', 'api/api_sending.cpp', 'api/api_send_progress.cpp', 'data/data_histories.cpp', 'data/data_replies_list.cpp', 'history/history.cpp', 'history/history_widget.cpp', 'history/view/history_view_element.cpp', 'history/history_streamed_drafts.cpp', 'chat_helpers/emoji_interactions.cpp', 'menu/menu_send.cpp', 'window/notifications_manager.cpp', 'window/window_peer_menu.cpp', 'window/window_main_menu.cpp', 'settings/sections/settings_main.cpp', 'intro/intro_start.cpp', 'dialogs/ui/dialogs_message_view.cpp', 'ui/onegram/onegram_ui.cpp', 'ui/onegram/onegram_ui.h', 'ui/onegram/onegram_ignore_layout.h']]
    sources += [DESKTOP / 'Telegram/SourceFiles/lang/lang_instance.cpp']
    sources += [DESKTOP / 'Telegram/CMakeLists.txt']
    sources += [DESKTOP / 'Telegram/SourceFiles/window/main_window.cpp']
    manifest = {'binary': str(binary), 'binary_sha256': sha256_file(binary), 'configuration': 'Debug', 'debug_database_distributed': False, 'link_debug_information': 'FASTLINK', 'features': ['mutual_streaks_with_history', 'channel_subscription_after_login', 'active_today_streak_colors', 'mute_in_message_preview', 'local_ignore_direct_stop', 'onegram_settings', 'native_login_channel_open', 'paper_boat_icon'], 'source_commit': subprocess.check_output(['git', '-C', str(DESKTOP), 'rev-parse', 'HEAD'], env=environment, text=True).strip(), 'source_sha256': {path.relative_to(DESKTOP).as_posix(): sha256_file(path) for path in sources}}
    (work / 'Native-BUILD.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    print('Compiled client:', binary)
    print('This binary still requires OneGram branding and portable proxy packaging before distribution.')
if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, FileNotFoundError) as error:
        raise SystemExit(str(error))
