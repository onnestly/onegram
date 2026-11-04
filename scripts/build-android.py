import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from brand_client import make_icon
from http2_dependencies import dependencies
from android_ignore_hooks import patch_ignore_sources
from android_presentation import apply_presentation
ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'
DECODED = LOCAL / 'android-decoded'
WORK = LOCAL / 'android-module'
SDK = Path(os.environ.get('ANDROID_SDK_ROOT', str(LOCAL / 'android-sdk')))
JAVA_HOME = Path(os.environ.get('JAVA_HOME', str(LOCAL / 'jdk')))
JAVA = JAVA_HOME / 'bin/java.exe'
APKTOOL_JAVA = Path(os.environ.get('ONEGRAM_APKTOOL_JAVA', str(JAVA)))
TOOLS = Path(os.environ.get('ONEGRAM_ANDROID_BUILD_TOOLS', str(SDK / 'build-tools/36.0.0')))
ANDROID = '{http://schemas.android.com/apk/res/android}'
PACKAGE = 'org.onegram.messenger'

def run(arguments, **kwargs):
    subprocess.run([str(value) for value in arguments], check=True, cwd=ROOT, **kwargs)

def patch_sources():
    sys.path.insert(0, str(ROOT / 'windows'))
    from branding import branded
    manifest = DECODED / 'AndroidManifest.xml'
    ET.register_namespace('android', ANDROID[1:-1])
    tree = ET.parse(manifest)
    root = tree.getroot()
    old_package = 'org.telegram.messenger.web'
    root.set('package', PACKAGE)
    for node in root.iter():
        for name, value in list(node.attrib.items()):
            if old_package != PACKAGE and old_package in value:
                node.set(name, value.replace(old_package, PACKAGE))
            if name in (ANDROID + 'icon', ANDROID + 'roundIcon'):
                node.set(name, '@mipmap/onegram_icon')
    app = root.find('application')
    app.set(ANDROID + 'label', 'OneGram')
    app.set(ANDROID + 'extractNativeLibs', 'false')
    if not any((item.get(ANDROID + 'name') == 'org.onegram.OneGramActivity' for item in app.findall('activity'))):
        ET.SubElement(app, 'activity', {ANDROID + 'name': 'org.onegram.OneGramActivity', ANDROID + 'exported': 'false', ANDROID + 'theme': '@android:style/Theme.Material.NoActionBar', ANDROID + 'windowSoftInputMode': 'adjustResize'})
    permission = 'android.permission.FOREGROUND_SERVICE_SPECIAL_USE'
    if not any((item.get(ANDROID + 'name') == permission for item in root.findall('uses-permission'))):
        ET.SubElement(root, 'uses-permission', {ANDROID + 'name': permission})
    if not any((item.get(ANDROID + 'name') == 'org.onegram.OneGramService' for item in app.findall('service'))):
        service = ET.SubElement(app, 'service', {ANDROID + 'name': 'org.onegram.OneGramService', ANDROID + 'exported': 'false', ANDROID + 'foregroundServiceType': 'specialUse'})
        ET.SubElement(service, 'property', {ANDROID + 'name': 'android.app.PROPERTY_SPECIAL_USE_FGS_SUBTYPE', ANDROID + 'value': 'Maintains the user-visible OneGram Telegram WebSocket connection in the background'})
    tree.write(manifest, encoding='utf-8', xml_declaration=True)
    for path in (DECODED / 'res').glob('values*/*.xml'):
        resources = ET.parse(path)
        for item in resources.getroot().iter():
            if item.text and any((name in item.text for name in ('Telegram', 'TELEGRAM', 'OneGram', 'ONEGRAM'))):
                if not item.text.strip().startswith(('http://', 'https://', 'tg://')):
                    item.text = branded(item.text.encode('utf-8')).decode('utf-8')
        resources.write(path, encoding='utf-8', xml_declaration=True)
    drawables = DECODED / 'res/drawable-nodpi'
    drawables.mkdir(exist_ok=True)
    make_icon(192).save(drawables / 'onegram_icon.png')
    drawable = DECODED / 'res/drawable'
    drawable.mkdir(exist_ok=True)
    (drawable / 'onegram_status.xml').write_text('<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="24dp" android:height="24dp" android:viewportWidth="24" android:viewportHeight="24"><path android:fillColor="#FFFFFFFF" android:fillType="evenOdd" android:pathData="M2,12L7,21L19,19L23,8L15,11L12,3L8,13ZM4,13L9,14L12,5L13,15L21,10L18,18L7,20Z"/></vector>', encoding='utf-8')
    activity = next(DECODED.glob('smali*/org/telegram/ui/LaunchActivity.smali'))
    text = activity.read_text(encoding='utf-8')
    match = re.search('(\\.method[^\\n]* onCreate\\(Landroid/os/Bundle;\\)V\\n)(.*?)(\\.end method)', text, re.S)
    if not match:
        raise RuntimeError('LaunchActivity hook not found')
    body = match.group(2)
    body = re.sub('(?m)^    invoke-static/range[^\\n]*Lorg/onegram/OneGramBoot;->start[^\\n]*\\n', '', body)
    registers = re.search('(?m)^    \\.(?:locals|registers) \\d+\\n', body)
    if not registers:
        raise RuntimeError('No activity register declaration')
    point = registers.end()
    body = body[:point] + '\n    invoke-static/range {p0 .. p0}, Lorg/onegram/OneGramBoot;->start(Landroid/app/Activity;)V\n' + body[point:]
    text = text[:match.start(2)] + body + text[match.end(2):]
    for name, callback in [('onResume', 'resume'), ('onPause', 'pause')]:
        lifecycle = re.search('(\\.method[^\\n]* ' + name + '\\(\\)V\\n)(.*?)(\\.end method)', text, re.S)
        if not lifecycle:
            raise RuntimeError('Activity lifecycle hook missing: ' + name)
        body = lifecycle.group(2)
        body = re.sub('(?m)^    invoke-static/range[^\\n]*Lorg/onegram/OneGramBoot;->' + callback + '[^\\n]*\\n', '', body)
        registers = re.search('(?m)^    \\.(?:locals|registers) \\d+\\n', body)
        if not registers:
            raise RuntimeError('No lifecycle register declaration')
        point = registers.end()
        body = body[:point] + '\n    invoke-static/range {p0 .. p0}, Lorg/onegram/OneGramBoot;->' + callback + '(Landroid/app/Activity;)V\n' + body[point:]
        text = text[:lifecycle.start(2)] + body + text[lifecycle.end(2):]
    activity.write_text(text, encoding='utf-8')
    locale = next(DECODED.glob('smali*/org/telegram/messenger/LocaleController.smali'))
    text = locale.read_text(encoding='utf-8')

    def hook(match):
        header, body = (match.group(1), match.group(2))
        if 'Lorg/onegram/OneGramBoot;->brand' in body:
            return match.group(0)
        body = re.sub('(?m)^    return-object ([vp]\\d+)$', lambda item: '    invoke-static/range {' + item[1] + ' .. ' + item[1] + '}, Lorg/onegram/OneGramBoot;->brand(Ljava/lang/String;)Ljava/lang/String;\n\n    move-result-object ' + item[1] + '\n\n    return-object ' + item[1], body)
        return header + body + '.end method'
    text = re.sub('(\\.method[^\\n]* (?:getString|getStringInternal|getStringV2)\\([^\\n]*\\)Ljava/lang/String;\\n)(.*?)\\.end method', hook, text, flags=re.S)
    locale.write_text(text, encoding='utf-8')
    provider_name = re.search('localizationExternal:L([^;]+);', text)
    if not provider_name:
        raise RuntimeError('External localization provider not found')
    provider = next(DECODED.glob('smali*/' + provider_name[1] + '.smali'))
    provider_text = provider.read_text(encoding='utf-8')
    provider_text = re.sub('(\\.method[^\\n]* (?:b|c)\\([^\\n]*\\)Ljava/lang/String;\\n)(.*?)\\.end method', hook, provider_text, flags=re.S)
    provider.write_text(provider_text, encoding='utf-8')
    for relative, method, callback in [('org/telegram/ui/Cells/s2.smali', 'onDraw', 'prepareDialog'), ('org/telegram/ui/Components/vo.smali', 'dispatchDraw', 'prepareHeader')]:
        path = next(DECODED.glob('smali*/' + relative))
        content = path.read_text(encoding='utf-8')
        if 'Lorg/onegram/streak/StreakUi;' not in content:
            owner = re.search('(?m)^\\.class[^\\n]* (L[^;]+;)', content)[1]
            pattern = '\\.method public ' + method + '\\(Landroid/graphics/Canvas;\\)V'
            if not re.search(pattern, content):
                raise RuntimeError('Streak draw entry missing: ' + relative)
            original = 'onegramOriginal' + method
            content = re.sub(pattern, '.method private ' + original + '(Landroid/graphics/Canvas;)V', content, count=1)
            content += '\n.method public ' + method + '(Landroid/graphics/Canvas;)V\n    .locals 0\n    invoke-static {p0}, Lorg/onegram/streak/StreakUi;->' + callback + '(Landroid/view/View;)V\n    invoke-direct {p0, p1}, ' + owner + '->' + original + '(Landroid/graphics/Canvas;)V\n    return-void\n.end method\n'
            path.write_text(content, encoding='utf-8')
    dialog = next(DECODED.glob('smali*/org/telegram/ui/Cells/s2.smali'))
    content = dialog.read_text(encoding='utf-8')
    for field in ('y2:Landroid/text/StaticLayout;', 'd3:Landroid/text/StaticLayout;', 'a3:I', 'Z2:I'):
        if not re.search('(?m)^\\.field[^\\n]* ' + re.escape(field) + '$', content):
            raise RuntimeError('Unsupported dialog layout for OneGram: ' + field)
    if 'StreakUi;->prepareMessage' not in content:
        entry = '    invoke-static {p0}, Lorg/onegram/streak/StreakUi;->prepareDialog(Landroid/view/View;)V'
        if content.count(entry) != 1:
            raise RuntimeError('Missing dialog draw wrapper')
        content = content.replace(entry, '    invoke-static {p0}, Lorg/onegram/streak/StreakUi;->prepareMessage(Landroid/view/View;)V\n' + entry)
    if 'StreakUi;->moveMute' not in content:
        pattern = '(sget-object (v\\d+), Lorg/telegram/ui/ActionBar/n6;->d1:Landroid/graphics/drawable/Drawable;\\s*(?:\\.line \\d+\\s*)*invoke-static \\{\\2, v\\d+, v\\d+\\}, Lorg/telegram/ui/Cells/c0;->q\\(Landroid/graphics/drawable/Drawable;FF\\)V)'
        start = content.index('.method private onegramOriginalonDraw(')
        end = content.index('.end method', start)
        body, count = re.subn(pattern, lambda match: match[0] + '\n    invoke-static/range {p0 .. p0}, Lorg/onegram/streak/StreakUi;->moveMute(Landroid/view/View;)V', content[start:end], count=1)
        if count != 1:
            raise RuntimeError('Mute icon draw hook was not found')
        content = content[:start] + body + content[end:]
    dialog.write_text(content, encoding='utf-8')
    selection = subprocess.run(['rg', '-l', 'org\\.telegram\\.messenger\\.web|https://t.me/TelegramTips', str(DECODED), '-g', '*.smali'], check=False, capture_output=True, text=True)
    if selection.returncode not in (0, 1):
        raise RuntimeError(selection.stderr)
    for filename in selection.stdout.splitlines():
        path = Path(filename)
        if path.is_file():
            text = path.read_text(encoding='utf-8')
            replacement = text.replace('https://t.me/TelegramTips', 'https://t.me/On3Gram')
            if old_package != PACKAGE:
                replacement = replacement.replace('"' + old_package, '"' + PACKAGE)
            if replacement != text:
                path.write_text(replacement, encoding='utf-8')
    patch_ignore_sources(DECODED)
    apply_presentation(DECODED)
    yaml = DECODED / 'apktool.yml'
    value = yaml.read_text(encoding='utf-8')
    value = re.sub('(?m)^  minSdkVersion:.*$', '  minSdkVersion: 26', value)
    value = re.sub('(?m)^  versionName:.*$', "  versionName: '1.0.3 (13.1.1)'", value)
    value = re.sub('(?m)^  versionCode:.*$', '  versionCode: 10003', value)
    yaml.write_text(value, encoding='utf-8')

def main():
    WORK.mkdir(parents=True, exist_ok=True)
    dex = WORK / 'dex'
    base = WORK / 'base-unsigned.apk'
    files = sorted((ROOT / 'android-module/src').rglob('*.java'))
    module_only = sys.argv[1:] == ['--module-only']
    if sys.argv[1:] == ['--package-only']:
        info = subprocess.check_output([str(TOOLS / 'aapt2.exe'), 'dump', 'badging', str(base)], text=True)
        if "versionCode='10003'" not in info or not (dex / 'classes.dex').exists():
            raise RuntimeError('A completed 1.0.3 base and module are required for --package-only')
        if (dex / 'classes.dex').stat().st_mtime < max((path.stat().st_mtime for path in files)):
            raise RuntimeError('Java source changed after module compilation')
    else:
        if sys.argv[1:] and (not module_only):
            raise RuntimeError('Unknown build option')
        if module_only:
            info = subprocess.check_output([str(TOOLS / 'aapt2.exe'), 'dump', 'badging', str(base)], text=True)
            if "versionCode='10003'" not in info:
                raise RuntimeError('Build the current Android base first')
            native = list(DECODED.glob('smali*/org/telegram/ui/Cells/s2.smali')) + [DECODED / 'apktool.yml']
            if max((path.stat().st_mtime for path in native)) > base.stat().st_mtime:
                raise RuntimeError('Native Android hooks changed; a full base build is required')
        else:
            print('Patching Android branding, entry point and proxy integration', flush=True)
            patch_sources()
        print('Compiling the Java foreground service and network module', flush=True)
        classes = WORK / ('production-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        classes.mkdir(exist_ok=False)
        http2 = dependencies()
        classpath = os.pathsep.join((str(path) for path in [SDK / 'platforms/android-34/android.jar', *http2]))
        run([JAVA_HOME / 'bin/javac.exe', '-J-Xmx384m', '--release', '8', '-encoding', 'UTF-8', '-cp', classpath, '-d', classes, *files])
        module = WORK / 'onegram-module.jar'
        run([JAVA_HOME / 'bin/jar.exe', 'cf', module, '-C', classes, '.'])
        dex.mkdir(exist_ok=True)
        run([JAVA, '-Xmx1024m', '-XX:+UseSerialGC', '-cp', TOOLS / 'lib/d8.jar', 'com.android.tools.r8.D8', '--release', '--min-api', '26', '--lib', SDK / 'platforms/android-34/android.jar', '--output', dex, module, *http2])
        if (dex / 'classes2.dex').exists():
            raise RuntimeError('Unexpected multi-dex HTTP2 module; update injection mapping first')
        if not module_only:
            run([APKTOOL_JAVA, '-Xmx1536m', '-XX:+UseSerialGC', '-jar', LOCAL / 'downloads/apktool.jar', 'b', DECODED, '-j', '2', '-p', LOCAL / 'apktool-framework', '-o', base])
    alignment = TOOLS / 'zipalign.exe'
    if not alignment.exists():
        alignment = TOOLS / 'zipalign.exe'
    signing = LOCAL / 'signing'
    signing.mkdir(exist_ok=True)
    password_file = signing / 'password.txt'
    if not password_file.exists():
        password_file.write_text(secrets.token_urlsafe(32), encoding='utf-8')
    environment = os.environ.copy()
    environment['ONEGRAM_SIGNING_PASSWORD'] = password_file.read_text(encoding='utf-8')
    key = signing / 'onegram-release.p12'
    if not key.exists():
        run([JAVA_HOME / 'bin/keytool.exe', '-genkeypair', '-noprompt', '-keystore', key, '-storetype', 'PKCS12', '-alias', 'onegram', '-keyalg', 'RSA', '-keysize', '3072', '-validity', '10001', '-dname', 'CN=OneGram,OU=Local Development', '-storepass:env', 'ONEGRAM_SIGNING_PASSWORD'], env=environment)
    signer = TOOLS / 'lib/apksigner.jar'
    variants = {}
    for variant, abi, filename in [('universal', None, 'OneGram-Android.apk'), ('arm64', 'arm64-v8a', 'OneGram-Android-arm64.apk')]:
        injected = WORK / f'injected-{variant}.apk'
        with zipfile.ZipFile(base) as source, zipfile.ZipFile(injected, 'w') as output:
            names = source.namelist()
            for info in source.infolist():
                if info.filename in ('assets/dexopt/baseline.prof', 'assets/dexopt/baseline.profm'):
                    continue
                if abi and info.filename.startswith('lib/') and (info.filename.split('/')[1] != abi):
                    continue
                payload = source.read(info)
                if info.filename.startswith('lib/'):
                    info.compress_type = zipfile.ZIP_STORED
                elif info.filename.endswith('.dex'):
                    info.compress_type = zipfile.ZIP_STORED
                output.writestr(info, payload)
            index = 2
            while f'classes{index}.dex' in names:
                index += 1
            output.write(dex / 'classes.dex', f'classes{index}.dex', compress_type=zipfile.ZIP_STORED)
            for license in sorted((ROOT / 'android-module/licenses').glob('*')):
                output.write(license, 'assets/onegram-licenses/' + license.name)
            output.write(ROOT / 'android-module/http2-dependencies.json', 'assets/onegram-licenses/http2-dependencies.json')
        aligned = WORK / f'aligned-{variant}.apk'
        run([alignment, '-P', '16', '-f', '4', injected, aligned])
        target = ROOT / 'dist' / filename
        signed = WORK / f'signed-{variant}.apk'
        run([JAVA, '-jar', signer, 'sign', '--v4-signing-enabled', 'false', '--ks', key, '--ks-key-alias', 'onegram', '--ks-pass', 'env:ONEGRAM_SIGNING_PASSWORD', '--out', signed, aligned], env=environment)
        run([JAVA, '-jar', signer, 'verify', '--verbose', signed])
        run([alignment, '-c', '-P', '16', '4', signed])
        publish = target.with_suffix('.apk.tmp')
        shutil.copyfile(signed, publish)
        os.replace(publish, target)
        variants[variant] = {'file': filename, 'abi': abi or 'all', 'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'bytes': target.stat().st_size}
        print(target, flush=True)
    manifest = json.loads((LOCAL / 'downloads/android-source.json').read_text(encoding='utf-8'))
    manifest.update({'onegram_version': '1.0.3', 'base_version': '13.1.1', 'package': PACKAGE, 'min_sdk': 26, 'artifact_sha256': variants['universal']['sha256'], 'variants': variants, 'native_libraries': 'uncompressed and 16 KB ZIP aligned; extractNativeLibs=false', 'dex': 'uncompressed; stale upstream baseline profiles removed', 'connection': 'Telegram WSS plus upstream reserve WSS endpoints; bounded parallel dialing; persistent listener and resume/network recovery', 'automatic_subscription': True, 'subscription_channel': '@On3Gram', 'subscription_policy': 'Once per account after login; successful join persisted; manual leave respected'})
    (ROOT / 'dist' / 'Android-BUILD.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
if __name__ == '__main__':
    main()
