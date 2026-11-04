import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw
from PyInstaller.utils.win32.icon import CopyIcons_FromIco
from PyInstaller.compat import win32api
from PyInstaller.utils.win32.versioninfo import load_version_info_from_text_file, write_version_info_to_executable

def make_icon(size=256, margin=8):
    source = Path(__file__).resolve().parents[1] / 'windows/assets/onegram-icon.svg'
    image = Image.new('RGBA', (size, size), '#238CE6')
    draw = ImageDraw.Draw(image)
    for node in ET.parse(source).getroot():
        if node.tag.endswith('path'):
            values = [float(x) for x in re.findall(r'-?\d+(?:\.\d+)?', node.get('d'))]
            draw.polygon([(values[i]*size/128, values[i+1]*size/128) for i in range(0,len(values),2)], fill=node.get('fill'))
    return image

def prepare_language(root: Path):
    path = root / 'desktop/Telegram/Resources/langs/lang.strings'
    if not path.exists(): path = root / 'overlays/desktop/Telegram/Resources/langs/lang.strings'
    source = path.read_text(encoding='utf-8')
    entries = {}
    for key, literal in re.findall('"([^"\\n]+)"\\s*=\\s*"((?:\\\\.|[^"\\\\])*)"\\s*;', source):
        value = json.loads('"' + literal + '"')
        entries[key] = value
    if len(entries) < 5000:
        raise RuntimeError('Incomplete baseline localization')
    entries['lng_intro_about'] = "Welcome to OneGram.\nIt's fast and secure."
    entries['lng_telegram_features_url'] = 'https://t.me/TelegramTips'
    directory = root / 'windows' / 'assets'
    directory.mkdir(exist_ok=True)
    (directory / 'branding-en.json').write_text(json.dumps(entries, ensure_ascii=False), encoding='utf-8')

def clear_presentation_resources(executable: Path):
    module = win32api.LoadLibraryEx(str(executable), 0, 2)
    entries = []
    try:
        for resource_type in win32api.EnumResourceTypes(module):
            if resource_type not in (3, 14, 16):
                continue
            for name in win32api.EnumResourceNames(module, resource_type):
                for language in win32api.EnumResourceLanguages(module, resource_type, name):
                    entries.append((resource_type, name, language))
    finally:
        win32api.FreeLibrary(module)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.BeginUpdateResourceW.argtypes = [wintypes.LPCWSTR, wintypes.BOOL]
    kernel.BeginUpdateResourceW.restype = wintypes.HANDLE
    kernel.UpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.WORD, ctypes.c_void_p, wintypes.DWORD]
    kernel.EndUpdateResourceW.argtypes = [wintypes.HANDLE, wintypes.BOOL]
    handle = kernel.BeginUpdateResourceW(str(executable), False)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    discard = True
    try:
        for resource_type, name, language in entries:
            pointer = lambda value: ctypes.cast(ctypes.c_void_p(value), wintypes.LPCWSTR) if isinstance(value, int) else value
            if not kernel.UpdateResourceW(handle, pointer(resource_type), pointer(name), language, None, 0):
                raise ctypes.WinError(ctypes.get_last_error())
        discard = False
    finally:
        if not kernel.EndUpdateResourceW(handle, discard):
            raise ctypes.WinError(ctypes.get_last_error())
