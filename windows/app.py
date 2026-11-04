from __future__ import annotations
import ctypes
from ctypes import wintypes
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import subprocess
import sys
import time
if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'upstream' / 'tg-ws-proxy'))
from network import Network
from settings_codec import configure
from preferences import proxy_enabled

def root_path() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1] / 'dist' / 'OneGram'

def show_error(text: str):
    ctypes.windll.user32.MessageBoxW(None, text, 'OneGram', 16)

class PrivateLog(logging.Filter):

    def filter(self, record):
        text = record.getMessage()
        text = re.sub('(?i)(secret[=: ]+)(?:dd)?[0-9a-f]{32,}', '\\1[hidden]', text)
        text = re.sub('tg://proxy\\?\\S+', '[local proxy link]', text)
        record.msg, record.args = (text, ())
        return True

def setup_logging(data: Path):
    logs = data / 'logs'
    logs.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(logs / 'onegram.log', maxBytes=2 * 1024 * 1024, backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    handler.addFilter(PrivateLog())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger('httpx').setLevel(logging.WARNING)

def load_config(data: Path) -> dict:
    path = data / 'onegram.json'
    if path.exists():
        config = json.loads(path.read_text(encoding='utf-8'))
        secret = config['secret']
        if not isinstance(secret, str) or len(secret) != 32 or len(bytes.fromhex(secret)) != 16:
            raise ValueError('Invalid local configuration')
        port = config['port']
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError('Invalid local proxy port')
        return config
    return {'secret': os.urandom(16).hex(), 'port': 0}

def save_config(data: Path, config: dict):
    temporary = data / 'onegram.json.new'
    temporary.write_text(json.dumps(config, indent=2), encoding='utf-8')
    os.replace(temporary, data / 'onegram.json')

def client_command(root: Path, profile: Path, *extra: str) -> list[str]:
    return [str(root / 'client' / 'OneGramClient.exe'), '-workdir', str(profile), '-noupdate', *extra]

def client_environment(data: Path) -> dict:
    environment = os.environ.copy()
    for name, directory in [('APPDATA', 'appdata'), ('LOCALAPPDATA', 'localappdata'), ('TEMP', 'tmp'), ('TMP', 'tmp')]:
        path = data / directory
        path.mkdir(exist_ok=True)
        environment[name] = str(path)
    environment['ONEGRAM_PROXY_MANAGED'] = '1'
    return environment

def forwarded_arguments(arguments: list[str]) -> tuple[str, ...]:
    flags = [value for value in arguments if value in ('-autostart', '-startintray', '-tosettings')]
    link = next((value for value in arguments if value.lower().startswith(('tg://', 'tonsite://', 'https://t.me/', 'https://telegram.me/'))), None)
    return tuple(flags + (['--', link] if link else []))

def own_client_pid(root: Path, profile: Path) -> int | None:
    import psutil
    expected = os.path.normcase(str(root / 'client' / 'OneGramClient.exe'))
    for process in psutil.process_iter(['pid', 'exe', 'cmdline']):
        try:
            if not process.info['exe'] or os.path.normcase(process.info['exe']) != expected:
                continue
            args = process.info['cmdline'] or []
            if '-workdir' in args and Path(args[args.index('-workdir') + 1]).resolve() == profile:
                return process.info['pid']
        except (psutil.Error, OSError, ValueError, IndexError):
            continue
    return None

def update_titles(pid: int):
    user32 = ctypes.WinDLL('user32', use_last_error=True)
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    @callback_type
    def visit(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid:
            title = ctypes.create_unicode_buffer(1024)
            user32.GetWindowTextW(hwnd, title, len(title))
            if 'Telegram' in title.value:
                user32.SetWindowTextW(hwnd, title.value.replace('Telegram Desktop', 'OneGram').replace('Telegram', 'OneGram'))
        return True
    user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
    user32.EnumWindows(visit, 0)

def main() -> int:
    root = root_path()
    forwarded = forwarded_arguments(sys.argv[1:])
    data = root / 'data'
    profile = data / 'profile'
    data.mkdir(parents=True, exist_ok=True)
    profile.mkdir(parents=True, exist_ok=True)
    if not Path(client_command(root, profile)[0]).is_file():
        show_error('Не найден клиент OneGram. Распакуй всю папку из архива и запускай OneGram.exe из неё.')
        return 1
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    identity = hashlib.sha256(str(root).casefold().encode()).hexdigest()[:24]
    mutex = kernel.CreateMutexW(None, False, 'Local\\OneGram-' + identity)
    if not mutex:
        show_error('Не удалось запустить OneGram: ошибка блокировки процесса.')
        return 1
    already_running = ctypes.get_last_error() == 183
    if already_running:
        try:
            deadline = time.monotonic() + 25
            while time.monotonic() < deadline:
                if own_client_pid(root, profile):
                    subprocess.Popen(client_command(root, profile, *forwarded), cwd=root / 'client', env=client_environment(data))
                    return 0
                time.sleep(0.2)
            show_error('OneGram ещё запускается. Повтори запуск через несколько секунд.')
            return 1
        finally:
            kernel.CloseHandle(mutex)
    setup_logging(data)
    network = None
    try:
        manifest_path = root / 'BUILD.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
        existing = own_client_pid(root, profile)
        config = load_config(data)
        if existing and (not config['port']):
            raise RuntimeError('Выйди из клиента через меню в трее и запусти OneGram.exe заново.')
        if proxy_enabled(data):
            network = Network(config['port'], config['secret'])
            try:
                network.start()
            except RuntimeError:
                if existing or not isinstance(network.error, OSError):
                    raise
                logging.warning('Previous local port unavailable; selecting a new local port')
                network = Network(0, config['secret'])
                network.start()
            config['port'] = network.port
        elif not config['port']:
            import socket
            with socket.socket() as temporary_socket:
                temporary_socket.bind(('127.0.0.1', 0))
                config['port'] = temporary_socket.getsockname()[1]
        save_config(data, config)
        import psutil
        if existing:
            tracked = psutil.Process(existing)
            client = None
            subprocess.Popen(client_command(root, profile, *forwarded), cwd=root / 'client', env=client_environment(data))
            logging.info('Restored background proxy for running OneGram client')
        else:
            configure(profile, config['port'], config['secret'], proxy_enabled(data))
            logging.info('Starting OneGram client; built-in proxy enabled=%s', proxy_enabled(data))
            first_channel = not manifest.get('native_onboarding', False) and (not config.get('on3gram_opened', False))
            extra = forwarded or (('--', 'tg://resolve?domain=On3Gram') if first_channel else ())
            client = subprocess.Popen(client_command(root, profile, *extra), cwd=root / 'client', env=client_environment(data))
            tracked = psutil.Process(client.pid)
            if first_channel:
                config['on3gram_opened'] = True
                save_config(data, config)
        restart_count = 0
        while True:
            if not tracked.is_running() or (client is not None and client.poll() is not None):
                replacement = None
                for _ in range(10):
                    time.sleep(0.2)
                    replacement = own_client_pid(root, profile)
                    if replacement and replacement != tracked.pid:
                        break
                    replacement = None
                if not replacement:
                    break
                tracked = psutil.Process(replacement)
                client = None
                logging.info('Client restarted; background proxy retained')
            if not manifest.get('native_client', False):
                update_titles(tracked.pid)
            desired = proxy_enabled(data)
            if not desired and network is not None:
                network.stop()
                network = None
                restart_count = 0
                logging.info('Built-in proxy disabled in OneGram settings')
            elif desired and (network is None or network.finished.is_set()):
                if network is not None:
                    restart_count += 1
                    if restart_count > 3:
                        raise RuntimeError('Фоновый модуль подключения остановился. Перезапусти OneGram; журнал находится в data/logs.')
                    logging.warning('Restarting local network module (%d)', restart_count)
                    time.sleep(min(2 ** restart_count, 8))
                network = Network(config['port'], config['secret'])
                try:
                    network.start()
                except RuntimeError:
                    if not isinstance(network.error, OSError):
                        raise
                    network = Network(0, config['secret'])
                    network.start()
                config['port'] = network.port
                save_config(data, config)
            time.sleep(0.5)
        code = client.wait() if client else 0
        logging.info('Client exited (%s); stopping background proxy', code)
        return code or 0
    except Exception as exc:
        logging.exception('OneGram startup/runtime error')
        show_error(f'Не удалось запустить OneGram.\n\n{exc}\n\nЖурнал: {data / 'logs' / 'onegram.log'}')
        return 1
    finally:
        if network:
            network.stop()
        kernel.CloseHandle(mutex)
if __name__ == '__main__':
    raise SystemExit(main())
