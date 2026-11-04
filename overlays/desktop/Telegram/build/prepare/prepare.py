import os, sys, pprint, re, json, pathlib, hashlib, subprocess, glob, tempfile, plistlib
executePath = os.getcwd()
sys.dont_write_bytecode = True
scriptPath = os.path.dirname(os.path.realpath(__file__))
sys.path.append(scriptPath + '/..')
import qt_version
import build_mac

def finish(code):
    global executePath
    os.chdir(executePath)
    sys.exit(code)

def error(text):
    print('[ERROR] ' + text)
    finish(1)

def nativeToolsError():
    error('Make sure to run from Native Tools Command Prompt.')
win = sys.platform == 'win32'
mac = sys.platform == 'darwin'
if win and (not 'Platform' in os.environ):
    nativeToolsError()
win32 = win and os.environ['Platform'] == 'x86'
win64 = win and os.environ['Platform'] == 'x64'
winarm = win and os.environ['Platform'] == 'arm64'
arch = ''
if win32:
    arch = 'x86'
elif win64:
    arch = 'x64'
elif winarm:
    arch = 'arm'
if not qt_version.resolve(arch):
    error('Usupported platform.')
qt = os.environ.get('QT')
if win and (not 'COMSPEC' in os.environ):
    error('COMSPEC environment variable is not set.')
if win and (not win32) and (not win64) and (not winarm):
    nativeToolsError()
os.chdir(scriptPath + '/../../../..')
pathSep = ';' if win else ':'
libsLoc = 'Libraries' if not win64 else os.path.join('Libraries', 'win64')
keysLoc = 'cache_keys'
rootDir = os.getcwd()
libsDir = os.path.realpath(os.path.join(rootDir, libsLoc))
thirdPartyDir = os.path.realpath(os.path.join(rootDir, 'ThirdParty'))
usedPrefix = os.path.realpath(os.path.join(libsDir, 'local'))
optionsList = ['qt5', 'qt6', 'skip-release', 'build-stackwalk', 'qt-asserts']
options = []
runCommand = []
customRunCommand = False
for arg in sys.argv[1:]:
    if customRunCommand:
        runCommand.append(arg)
    if arg in optionsList:
        options.append(arg)
    elif arg == 'run':
        customRunCommand = True
    elif arg == 'shell':
        customRunCommand = True
        runCommand.append('shell')
pathPrefixes = ['ThirdParty\\msys64\\ucrt64\\bin', 'ThirdParty\\jom', 'ThirdParty\\gyp'] if win else ['ThirdParty/gyp']
pathPrefix = ''
for singlePrefix in pathPrefixes:
    pathPrefix = pathPrefix + os.path.join(rootDir, singlePrefix) + pathSep
environment = {'USED_PREFIX': usedPrefix, 'ROOT_DIR': rootDir, 'LIBS_DIR': libsDir, 'THIRDPARTY_DIR': thirdPartyDir, 'PATH_PREFIX': pathPrefix, 'CMAKE_GENERATOR': 'Ninja Multi-Config'}
if win32:
    environment.update({'SPECIAL_TARGET': 'win', 'X8664': 'x86'})
elif win64:
    environment.update({'SPECIAL_TARGET': 'win64', 'X8664': 'x64'})
elif winarm:
    environment.update({'SPECIAL_TARGET': 'winarm', 'X8664': 'ARM64'})
elif mac:
    macToolchain = pathlib.Path(rootDir) / 'Toolchains/CommandLineTools-26.6'
    macToolchainChoice = os.environ.get('TDESKTOP_MAC_TOOLCHAIN', 'auto')
    if macToolchainChoice not in ('auto', '26.6', 'system'):
        error('TDESKTOP_MAC_TOOLCHAIN must be auto, 26.6, or system.')
    macRelease = macToolchainChoice == '26.6' or (macToolchainChoice == 'auto' and (pathlib.Path(rootDir) / 'DesktopPrivate').is_dir())
    if macRelease:
        if os.environ.get('MACOSX_DEPLOYMENT_TARGET', '10.13') != '10.13':
            error('Official dependency preparation requires deployment target 10.13.')
        try:
            macEnvironment, macSdk = build_mac.toolchain_environment(macToolchain)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exception:
            error(str(exception))
        macSdk = str(macSdk)
        macDeployment = '10.13'
        environment['PATH_PREFIX'] = str(macToolchain / 'usr/bin') + pathSep + pathPrefix
        for variable, program in (('CC', 'clang'), ('CXX', 'clang++'), ('OBJC', 'clang'), ('OBJCXX', 'clang++'), ('AR', 'ar'), ('RANLIB', 'ranlib'), ('LD', 'ld')):
            environment[variable] = str(macToolchain / 'usr/bin' / program)
        macCompiler = environment['CC']
        for target in ('AARCH64_APPLE_DARWIN', 'X86_64_APPLE_DARWIN'):
            environment['CARGO_TARGET_' + target + '_LINKER'] = macCompiler
            for variable in ('CC', 'CXX', 'AR'):
                environment[variable + '_' + target.lower()] = environment[variable]
        if 'build-stackwalk' in options:
            error('Legacy stackwalk preparation still requires full Xcode 26.6.')
    else:
        macSdk = subprocess.check_output(['xcrun', '--sdk', 'macosx', '--show-sdk-path'], text=True).strip()
        macCompiler = subprocess.check_output(['xcrun', '--find', 'clang'], text=True).strip()
    with open(os.path.join(macSdk, 'SDKSettings.plist'), 'rb') as file:
        macSdkSettings = plistlib.load(file)
    macMinimum = macSdkSettings['SupportedTargets']['macosx']['MinimumDeploymentTarget']
    if not macRelease:
        macDeployment = os.environ.get('MACOSX_DEPLOYMENT_TARGET', macMinimum)
    if tuple(map(int, macDeployment.split('.'))) < tuple(map(int, macMinimum.split('.'))):
        error('The selected macOS SDK requires deployment target ' + macMinimum + ' or newer; select the older toolchain to build for ' + macDeployment + '.')
    environment.update({'SPECIAL_TARGET': 'mac', 'MAKE_THREADS_CNT': '-j' + str(os.cpu_count()), 'SDKROOT': macSdk, 'MACOSX_DEPLOYMENT_TARGET': macDeployment, 'UNGUARDED': '-Werror=unguarded-availability-new', 'MIN_VER': '-mmacosx-version-min=' + macDeployment, 'CMAKE_GENERATOR': 'Ninja'})
ignoreInCacheForThirdParty = ['USED_PREFIX', 'LIBS_DIR', 'SPECIAL_TARGET', 'X8664']
environmentKeyString = ''
envForThirdPartyKeyString = ''
for key in environment:
    part = key + '=' + environment[key] + ';'
    environmentKeyString += part
    if not key in ignoreInCacheForThirdParty:
        envForThirdPartyKeyString += part
if mac:
    environmentKeyString += subprocess.check_output([macCompiler, '--version'], text=True)
    environmentKeyString += json.dumps(macSdkSettings, sort_keys=True)
environmentKey = hashlib.sha1(environmentKeyString.encode('utf-8')).hexdigest()
envForThirdPartyKey = hashlib.sha1(envForThirdPartyKeyString.encode('utf-8')).hexdigest()
modifiedEnv = os.environ.copy()
if mac and macRelease:
    modifiedEnv.pop('TOOLCHAINS', None)
    modifiedEnv['PREPARE_DIR'] = scriptPath
for key in environment:
    modifiedEnv[key] = environment[key]
if win and 'NoDefaultCurrentDirectoryInExePath' in modifiedEnv:
    del modifiedEnv['NoDefaultCurrentDirectoryInExePath']
modifiedEnv['PATH'] = environment['PATH_PREFIX'] + modifiedEnv['PATH']
if mac:
    toolchainState = pathlib.Path(libsDir) / 'macos_toolchain.json'
    purpose = 'release' if macRelease else 'development'
    if toolchainState.is_file():
        previous = json.loads(toolchainState.read_text())
        if previous['purpose'] != purpose:
            error('Libraries was prepared for ' + previous['purpose'] + ' builds. Use a separate dependency directory for ' + purpose + ' builds.')
    pathlib.Path(libsDir).mkdir(parents=True, exist_ok=True)
    toolchainState.write_text(json.dumps({'purpose': purpose, 'compiler': macCompiler, 'sdk': macSdk, 'deployment_target': macDeployment}, indent=2) + '\n')
pathlib.Path(os.path.join(libsDir, keysLoc)).mkdir(parents=True, exist_ok=True)
pathlib.Path(os.path.join(thirdPartyDir, keysLoc)).mkdir(parents=True, exist_ok=True)

def computeFileHash(path):
    sha1 = hashlib.sha1()
    with open(path, 'rb') as f:
        while True:
            data = f.read(256 * 1024)
            if not data:
                break
            sha1.update(data)
    return sha1.hexdigest()

def computeCacheKey(stage):
    if stage['location'] == 'ThirdParty':
        envKey = envForThirdPartyKey
    else:
        envKey = environmentKey
    objects = [envKey, stage['location'], stage['name'], stage['version'], stage['commands']]
    for pattern in stage['dependencies']:
        pathlist = glob.glob(os.path.join(libsDir, pattern))
        items = [pattern]
        if len(pathlist) == 0:
            pathlist = glob.glob(os.path.join(thirdPartyDir, pattern))
        if len(pathlist) == 0:
            error('Nothing found: ' + pattern)
        for path in pathlist:
            if not os.path.exists(path):
                error('Not found: ' + path)
            items.append(computeFileHash(path))
        objects.append(':'.join(items))
    return hashlib.sha1(';'.join(objects).encode('utf-8')).hexdigest()

def keyPath(stage):
    return os.path.join(stage['directory'], keysLoc, stage['name'])

def checkCacheKey(stage):
    if not 'key' in stage:
        error('Key not set in stage: ' + stage['name'])
    key = keyPath(stage)
    if not os.path.exists(os.path.join(stage['directory'], stage['name'])):
        return 'NotFound'
    if not os.path.exists(key):
        return 'Stale'
    with open(key, 'r') as file:
        return 'Good' if file.read() == stage['key'] else 'Stale'

def clearCacheKey(stage):
    key = keyPath(stage)
    if os.path.exists(key):
        os.remove(key)

def writeCacheKey(stage):
    if not 'key' in stage:
        error('Key not set in stage: ' + stage['name'])
    key = keyPath(stage)
    with open(key, 'w') as file:
        file.write(stage['key'])
stages = []

def removeDir(folder):
    if win:
        return 'if exist ' + folder + ' rmdir /Q /S ' + folder + '\nif exist ' + folder + ' exit /b 1'
    return 'rm -rf ' + folder

def setVar(key, multilineValue):
    singlelineValue = ' '.join(multilineValue.replace('\n', '').split())
    if win:
        return 'SET "' + key + '=' + singlelineValue + '"'
    return key + '="' + singlelineValue + '"'

def filterByPlatform(commands):
    commands = commands.split('\n')
    result = ''
    dependencies = []
    version = '0'
    skip = False
    for command in commands:
        m = re.match('(!?)([a-z0-9_]+):', command)
        if m and m.group(2) != 'depends' and (m.group(2) != 'version'):
            scopes = m.group(2).split('_')
            inscope = 'common' in scopes
            if win and 'win' in scopes:
                inscope = True
            if win32 and 'win32' in scopes:
                inscope = True
            if win64 and 'win64' in scopes:
                inscope = True
            if winarm and 'winarm' in scopes:
                inscope = True
            if mac and 'mac' in scopes:
                inscope = True
            if 'release' in scopes:
                if 'skip-release' in options:
                    inscope = False
                elif len(scopes) == 1:
                    continue
            if 'asserts' in scopes:
                inscope = inscope and 'qt-asserts' in options
            skip = inscope if m.group(1) == '!' else not inscope
        elif not skip and (not re.match('\\s*#', command)):
            if m and m.group(2) == 'version':
                version = version + '.' + command[len(m.group(0)):].strip()
            elif m and m.group(2) == 'depends':
                pattern = command[len(m.group(0)):].strip()
                dependencies.append(pattern)
            else:
                command = command.strip()
                if len(command) > 0:
                    result = result + command + '\n'
    return [result, dependencies, version]

def stage(name, commands, location='Libraries'):
    if location == 'Libraries':
        directory = libsDir
    elif location == 'ThirdParty':
        directory = thirdPartyDir
    else:
        error('Unknown location: ' + location)
    [commands, dependencies, version] = filterByPlatform(commands)
    if len(commands) > 0:
        stages.append({'name': name, 'location': location, 'directory': directory, 'commands': commands, 'version': version, 'dependencies': dependencies})

def winFailOnEach(command):
    commands = command.split('\n')
    result = ''
    startingCommand = True
    for command in commands:
        command = re.sub('\\$([A-Za-z0-9_]+)', '%\\1%', command)
        if re.search('\\$[^<]', command):
            error('Bad command: ' + command)
        appendCall = startingCommand and (not re.match('(if|for) ', command))
        called = 'call ' + command if appendCall else command
        result = result + called
        if command.endswith('^'):
            startingCommand = False
        else:
            startingCommand = True
            result = result + '\r\nif %errorlevel% neq 0 exit /b %errorlevel%\r\n'
    return result

def printCommands(commands):
    print('---------------------------------COMMANDS-LIST----------------------------------')
    print(commands, end='')
    print('--------------------------------------------------------------------------------')

def run(commands):
    printCommands(commands)
    if win:
        if os.path.exists('command.bat'):
            os.remove('command.bat')
        with open('command.bat', 'w') as file:
            file.write('@echo OFF\r\nset "NoDefaultCurrentDirectoryInExePath="\r\n' + winFailOnEach(commands))
        batPath = os.path.abspath('command.bat')
        result = subprocess.run(batPath, shell=True, env=modifiedEnv).returncode == 0
        if result and os.path.exists('command.bat'):
            os.remove('command.bat')
        return result
    elif re.search('\\%', commands):
        error('Bad command: ' + commands)
    else:
        return subprocess.run('set -e\n' + commands, shell=True, env=modifiedEnv).returncode == 0

class _Getch:

    def __init__(self):
        try:
            self.impl = _GetchWindows()
        except ImportError:
            self.impl = _GetchUnix()

    def __call__(self):
        return self.impl()

class _GetchUnix:

    def __init__(self):
        import tty, sys

    def __call__(self):
        import sys, tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

class _GetchWindows:

    def __init__(self):
        import msvcrt

    def __call__(self):
        import msvcrt
        return msvcrt.getch().decode('ascii')
getch = _Getch()

def runStages():
    onlyStages = []
    rebuildStale = False
    for arg in sys.argv[1:]:
        if arg in options:
            continue
        elif arg == 'silent':
            rebuildStale = True
            continue
        found = False
        for stage in stages:
            if stage['name'] == arg:
                onlyStages.append(arg)
                found = True
                break
        if not found:
            error('Unknown argument: ' + arg)
    count = len(stages)
    index = 0
    for stage in stages:
        if len(onlyStages) > 0 and (not stage['name'] in onlyStages):
            continue
        index = index + 1
        version = '#' + str(stage['version']) if stage['version'] != '0' else ''
        prefix = '[' + str(index) + '/' + str(count) + '](' + stage['location'] + '/' + stage['name'] + version + ')'
        print(prefix + ': ', end='', flush=True)
        stage['key'] = computeCacheKey(stage)
        commands = removeDir(stage['name']) + '\n' + stage['commands']
        checkResult = 'Forced' if len(onlyStages) > 0 else checkCacheKey(stage)
        if checkResult == 'Good':
            print('SKIPPING')
            continue
        elif checkResult == 'NotFound':
            print('NOT FOUND, ', end='')
        elif checkResult == 'Stale' or checkResult == 'Forced':
            if checkResult == 'Stale':
                print('CHANGED, ', end='')
            if rebuildStale:
                checkResult == 'Rebuild'
            else:
                print('(r)ebuild, rebuild (a)ll, (s)kip, (p)rint, (q)uit?: ', end='', flush=True)
                while True:
                    ch = 'r' if rebuildStale else getch()
                    if ch == 'q':
                        finish(0)
                    elif ch == 'p':
                        printCommands(commands)
                        checkResult = 'Printed'
                        break
                    elif ch == 's':
                        checkResult = 'Skip'
                        break
                    elif ch == 'r':
                        checkResult = 'Rebuild'
                        break
                    elif ch == 'a':
                        checkResult = 'Rebuild'
                        rebuildStale = True
                        break
        if checkResult == 'Printed':
            continue
        if checkResult == 'Skip':
            print('SKIPPING')
            continue
        clearCacheKey(stage)
        print('BUILDING:')
        os.chdir(stage['directory'])
        if not run(commands):
            print(prefix + ': FAILED')
            finish(1)
        writeCacheKey(stage)
if customRunCommand:
    os.chdir(executePath)
    if len(runCommand) == 1 and runCommand[0] == 'shell':
        print('Preparing interactive mode..')
        if win:
            modifiedEnv['PROMPT'] = '(prepare) $P$G'
            subprocess.run('cmd.exe', shell=True, env=modifiedEnv)
        else:
            prompt = '(prepare) %~ %# '
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp_zshrc:
                tmp_zshrc.write(f'export PS1="{prompt}"\n')
                tmp_zshrc_path = tmp_zshrc.name
            subprocess.run(['zsh', '--rcs', tmp_zshrc_path], shell=True, env=modifiedEnv)
            os.remove(tmp_zshrc_path)
    elif not run(' '.join(runCommand) + '\n'):
        print('FAILED :(')
        finish(1)
    finish(0)
stage('patches', '\n    git clone https://github.com/desktop-app/patches.git\n    cd patches\n    git checkout 13b4eb3dc1b8ef404b4ab04750e0fd7aafbe06c2\nmac:\n    sed -i \'\' "s/10.13/$MACOSX_DEPLOYMENT_TARGET/g" macos_meson_*.txt\n    git clone https://github.com/desktop-app/qt6_highsierra_patches.git qt6_highsierra\n    cd qt6_highsierra\n    git checkout 7387476bb3b7200d3b044015696cb3c28f78593c\n')
stage('msys64', '\nwin:\n    SET PATH=%THIRDPARTY_DIR%\\msys64\\usr\\bin;%PATH%\n    SET CHERE_INVOKING=enabled_from_arguments\n    SET MSYS2_PATH_TYPE=inherit\n\n    powershell -Command "iwr -OutFile ./msys64.exe https://github.com/msys2/msys2-installer/releases/download/2026-09-27/msys2-base-x86_64-20260927.sfx.exe"\n    msys64.exe\n    del msys64.exe\n\n    bash -c "pacman-key --init; pacman-key --populate; pacman -Syu --noconfirm"\n    pacman -Syu --noconfirm ^\n        make ^\n        mingw-w64-ucrt-x86_64-diffutils ^\n        mingw-w64-ucrt-x86_64-gperf ^\n        mingw-w64-ucrt-x86_64-nasm ^\n        mingw-w64-ucrt-x86_64-perl ^\n        mingw-w64-ucrt-x86_64-pkgconf\n', 'ThirdParty')
stage('python', '\nversion: ' + (subprocess.run(['python', '-V'], capture_output=True, text=True, env=modifiedEnv).stdout.strip().split()[-1] if win else '0') + '\nwin:\n    python -m venv python\n    python\\Scripts\\activate.bat\n    pip install pywin32 six meson\n    deactivate\n', 'ThirdParty')
stage('NuGet', '\nwin:\n    mkdir NuGet\n    powershell -Command "iwr -OutFile ./NuGet/nuget.exe https://dist.nuget.org/win-x86-commandline/latest/nuget.exe"\n', 'ThirdParty')
stage('jom', '\nwin:\n    if not exist jom.zip powershell -Command "iwr -OutFile ./jom.zip https://qt.mirror.constant.com/official_releases/jom/jom_1_1_3.zip"\n    python -c "import hashlib; assert hashlib.sha256(open(\'jom.zip\',\'rb\').read()).hexdigest() == \'128fdd846fe24f8594eed37d1d8929a0ea78df563537c0c1b1861a635013fff8\', \'Qt JOM checksum mismatch\'"\n    powershell -Command "Expand-Archive ./jom.zip"\n    del jom.zip\n', 'ThirdParty')
if not mac or 'build-stackwalk' in options:
    stage('gyp', '\nwin:\n    git clone https://github.com/desktop-app/gyp.git\n    cd gyp\n    git checkout 5e2425c47b\nmac:\n    python3 -m pip install \\\n        --ignore-installed \\\n        --target=$THIRDPARTY_DIR/gyp \\\n        git+https://chromium.googlesource.com/external/gyp@master six\n', 'ThirdParty')
rustToolchain = '1.96.1'
stage('rust', '\nwin:\n    powershell -Command "iwr -OutFile ./rustup-init.exe https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe"\n    SET "RUSTUP_HOME=%THIRDPARTY_DIR%\\rust\\rustup"\n    SET "CARGO_HOME=%THIRDPARTY_DIR%\\rust\\cargo"\n    rustup-init.exe -y --no-modify-path --profile minimal ^\n        --default-toolchain ' + rustToolchain + ' ^\n        --component rust-src\n    del rustup-init.exe\nmac:\n    wget -O rustup-init.sh https://sh.rustup.rs\n    export RUSTUP_HOME=$THIRDPARTY_DIR/rust/rustup\n    export CARGO_HOME=$THIRDPARTY_DIR/rust/cargo\n    sh rustup-init.sh -y --no-modify-path --profile minimal \\\n        --default-toolchain ' + rustToolchain + ' \\\n        --target aarch64-apple-darwin \\\n        --target x86_64-apple-darwin\n    rm rustup-init.sh\n', 'ThirdParty')
stage('lzma', '\nwin:\n    git clone https://github.com/desktop-app/lzma.git\n    cd lzma\\C\\Util\\LzmaLib\n    SET "ToolsetProp="\nwinarm:\n    SET "ToolsetProp=/property:PlatformToolset=v145"\nwin:\n    msbuild -m LzmaLib.sln /property:Configuration=Debug /property:Platform="$X8664" %ToolsetProp%\nrelease:\n    msbuild -m LzmaLib.sln /property:Configuration=Release /property:Platform="$X8664" %ToolsetProp%\n')
stage('xz', '\n!win:\n    git clone -b v5.4 https://github.com/tukaani-project/xz.git\n    cd xz\n    git checkout 05af863c3166cddeb4ab935829b14e995c8346b4\n    sed -i \'\' \'\\@check_symbol_exists(futimens "sys/types.h;sys/stat.h" HAVE_FUTIMENS)@d\' CMakeLists.txt\n    CFLAGS="$UNGUARDED" CPPFLAGS="$UNGUARDED" cmake -B build . \\\n        -D CMAKE_OSX_ARCHITECTURES="x86_64;arm64" \\\n        -D CMAKE_INSTALL_PREFIX:STRING=$USED_PREFIX\n    cmake --build build\n    cmake --install build\n')
stage('zlib', '\n    git clone https://github.com/madler/zlib.git\n    cd zlib\n    git checkout e3dc0a85b7032e98380dec011bc8f2c2ee0d8fca\nwin:\n    cmake . ^\n        -DCMAKE_MSVC_RUNTIME_LIBRARY="MultiThreaded$<$<CONFIG:Debug>:Debug>" ^\n        -DCMAKE_C_FLAGS="/DZLIB_WINAPI" ^\n        -DZLIB_BUILD_SHARED=OFF ^\n        -DZLIB_BUILD_TESTING=OFF ^\n        -DZLIB_BUILD_MINIZIP=ON ^\n        -DZLIB_MINIZIP_BUILD_SHARED=OFF ^\n        -DZLIB_MINIZIP_BUILD_TESTING=OFF\n    cmake --build . --config Debug\nrelease:\n    cmake --build . --config Release\nmac:\n    CFLAGS="$MIN_VER $UNGUARDED" LDFLAGS="$MIN_VER" ./configure \\\n        --static \\\n        --prefix=$USED_PREFIX \\\n        --archs="-arch x86_64 -arch arm64"\n    make $MAKE_THREADS_CNT\n    make install\n    cd contrib/minizip\n    autoreconf -fi\n    CFLAGS="$MIN_VER $UNGUARDED -arch arm64" CPPFLAGS="$MIN_VER $UNGUARDED -arch arm64" LDFLAGS="$MIN_VER" ./configure --enable-static --disable-shared --host=arm --prefix=$USED_PREFIX\n    make $MAKE_THREADS_CNT\n    mkdir out.arm64\n    mv .libs/libminizip.a out.arm64\n    make clean\n    CFLAGS="$MIN_VER $UNGUARDED -arch x86_64" CPPFLAGS="$MIN_VER $UNGUARDED -arch x86_64" LDFLAGS="$MIN_VER" ./configure --enable-static --disable-shared --host=x86_64 --prefix=$USED_PREFIX\n    make $MAKE_THREADS_CNT\n    mkdir out.x86_64\n    mv .libs/libminizip.a out.x86_64\n    lipo -create out.arm64/libminizip.a out.x86_64/libminizip.a -output .libs/libminizip.a\n    make install\n')
stage('mozjpeg', '\n    git clone -b v4.1.5 https://github.com/mozilla/mozjpeg.git\n    cd mozjpeg\nwin:\n    cmake . ^\n        -DCMAKE_POLICY_VERSION_MINIMUM=3.5 ^\n        -DWITH_JPEG8=ON ^\n        -DPNG_SUPPORTED=OFF\n    cmake --build . --config Debug\nrelease:\n    cmake --build . --config Release\nmac:\n    CFLAGS="-arch arm64" cmake -B build.arm64 . \\\n        -D CMAKE_POLICY_VERSION_MINIMUM=3.5 \\\n        -D CMAKE_SYSTEM_NAME=Darwin \\\n        -D CMAKE_SYSTEM_PROCESSOR=arm64 \\\n        -D CMAKE_BUILD_TYPE=Release \\\n        -D CMAKE_INSTALL_PREFIX=$USED_PREFIX \\\n        -D WITH_JPEG8=ON \\\n        -D ENABLE_SHARED=OFF \\\n        -D PNG_SUPPORTED=OFF\n    cmake --build build.arm64\n    CFLAGS="-arch x86_64" cmake -B build . \\\n        -D CMAKE_POLICY_VERSION_MINIMUM=3.5 \\\n        -D CMAKE_SYSTEM_NAME=Darwin \\\n        -D CMAKE_SYSTEM_PROCESSOR=x86_64 \\\n        -D CMAKE_BUILD_TYPE=Release \\\n        -D CMAKE_INSTALL_PREFIX=$USED_PREFIX \\\n        -D WITH_JPEG8=ON \\\n        -D ENABLE_SHARED=OFF \\\n        -D PNG_SUPPORTED=OFF\n    cmake --build build\n    lipo -create build.arm64/libjpeg.a build/libjpeg.a -output build/libjpeg.a\n    lipo -create build.arm64/libturbojpeg.a build/libturbojpeg.a -output build/libturbojpeg.a\n    cmake --install build\n')
stage('openssl3', '\n    git clone -b openssl-3.5.9 https://github.com/openssl/openssl openssl3\n    cd openssl3\nwin32:\n    perl Configure no-shared no-tests debug-VC-WIN32 /FS\nwin64:\n    perl Configure no-shared no-tests debug-VC-WIN64A /FS\nwinarm:\n    perl Configure no-shared no-tests debug-VC-WIN64-ARM /FS\nwin:\n    jom -j%NUMBER_OF_PROCESSORS% build_libs\n    mkdir out.dbg\n    move libcrypto.lib out.dbg\n    move libssl.lib out.dbg\n    move ossl_static.pdb out.dbg\nrelease:\n    move out.dbg\\ossl_static.pdb out.dbg\\ossl_static\n    jom clean\n    move out.dbg\\ossl_static out.dbg\\ossl_static.pdb\nwin32_release:\n    perl Configure no-shared no-tests VC-WIN32 /FS\nwin64_release:\n    perl Configure no-shared no-tests VC-WIN64A /FS\nwinarm_release:\n    perl Configure no-shared no-tests VC-WIN64-ARM /FS /Gs4096\nwin_release:\n    jom -j%NUMBER_OF_PROCESSORS% build_libs\n    mkdir out\n    move libcrypto.lib out\n    move libssl.lib out\n    move ossl_static.pdb out\nmac:\n    ./Configure --prefix=$USED_PREFIX no-shared no-tests darwin64-arm64-cc $MIN_VER\n    make build_libs $MAKE_THREADS_CNT\n    mkdir out.arm64\n    mv libssl.a out.arm64\n    mv libcrypto.a out.arm64\n    make clean\n    ./Configure --prefix=$USED_PREFIX no-shared no-tests darwin64-x86_64-cc $MIN_VER\n    make build_libs $MAKE_THREADS_CNT\n    mkdir out.x86_64\n    mv libssl.a out.x86_64\n    mv libcrypto.a out.x86_64\n    lipo -create out.arm64/libcrypto.a out.x86_64/libcrypto.a -output libcrypto.a\n    lipo -create out.arm64/libssl.a out.x86_64/libssl.a -output libssl.a\n')
stage('opus', '\n    git clone --depth 1 -b v1.5.2 https://github.com/xiph/opus.git\n    cd opus\nwin:\n    cmake -B out . ^\n        -DCMAKE_INSTALL_PREFIX=%LIBS_DIR%/local ^\n        -DOPUS_STATIC_RUNTIME=ON\n    cmake --build out --config Debug\n    cmake --build out --config Release\n    cmake --install out --config Release\nmac:\n    CFLAGS="$UNGUARDED" CPPFLAGS="$UNGUARDED" cmake -B build . \\\n        -D CMAKE_OSX_ARCHITECTURES="x86_64;arm64" \\\n        -D CMAKE_INSTALL_PREFIX:STRING=$USED_PREFIX\n    cmake --build build\n    cmake --install build\n')
stage('rnnoise', '\n    git clone https://github.com/desktop-app/rnnoise.git\n    cd rnnoise\n    git checkout d8ea2b0\n    mkdir out\n    cd out\nwin:\n    cmake .. -DCMAKE_MSVC_RUNTIME_LIBRARY="MultiThreaded$<$<CONFIG:Debug>:Debug>"\n    cmake --build . --config Debug\nrelease:\n    cmake --build . --config Release\n!win:\n    mkdir Debug\n    cd Debug\n    cmake ../.. \\\n        -D CMAKE_BUILD_TYPE=Debug \\\n        -D CMAKE_OSX_ARCHITECTURES="x86_64;arm64"\n    cmake --build .\nrelease:\n    cd ..\n    mkdir Release\n    cd Release\n    cmake ../.. \\\n        -D CMAKE_BUILD_TYPE=Release \\\n        -D CMAKE_OSX_ARCHITECTURES="x86_64;arm64"\n    cmake --build .\n')
stage('libiconv', '\nmac:\n    VERSION=1.18\n    rm -f libiconv.tar.gz\n    wget --timeout=30 --tries=2 -O libiconv.tar.gz ftp://ftp.gnu.org/gnu/libiconv/libiconv-$VERSION.tar.gz || wget -O libiconv.tar.gz https://ftp.gnu.org/pub/gnu/libiconv/libiconv-$VERSION.tar.gz\n    rm -rf libiconv-$VERSION\n    tar -xvzf libiconv.tar.gz\n    rm libiconv.tar.gz\n    mv libiconv-$VERSION libiconv\n    cd libiconv\n    CFLAGS="$MIN_VER $UNGUARDED -arch arm64" CPPFLAGS="$MIN_VER $UNGUARDED -arch arm64" LDFLAGS="$MIN_VER" ./configure --enable-static --host=arm --prefix=$USED_PREFIX\n    make $MAKE_THREADS_CNT\n    mkdir out.arm64\n    mv lib/.libs/libiconv.a out.arm64\n    make clean\n    CFLAGS="$MIN_VER $UNGUARDED -arch x86_64" CPPFLAGS="$MIN_VER $UNGUARDED -arch x86_64" LDFLAGS="$MIN_VER" ./configure --enable-static --host=x86_64 --prefix=$USED_PREFIX\n    make $MAKE_THREADS_CNT\n    mkdir out.x86_64\n    mv lib/.libs/libiconv.a out.x86_64\n    lipo -create out.arm64/libiconv.a out.x86_64/libiconv.a -output lib/.libs/libiconv.a\n    make install\n')
stage('gas-preprocessor', '\nwin:\n    git clone https://github.com/FFmpeg/gas-preprocessor\n    cd gas-preprocessor\n    echo @echo off > cpp.bat\n    echo cl %%%%%%** >> cpp.bat\n')
stage('dav1d', '\n    git clone -b 1.5.4 https://code.videolan.org/videolan/dav1d.git\n    cd dav1d\nwin32:\n    SET "TARGET=x86"\n    SET "DAV1D_ASM_DISABLE=-Denable_asm=false"\nwin64:\n    SET "TARGET=x86_64"\n    SET "DAV1D_ASM_DISABLE="\nwinarm:\n    SET "TARGET=aarch64"\n    SET "DAV1D_ASM_DISABLE="\n    SET "PATH=%LIBS_DIR%\\gas-preprocessor;%PATH%"\n    echo armasm64 fails with \'syntax error in expression: tbnz x14, #4, 8f\' as if this instruction is unknown/unsupported.\n    git revert --no-edit d503bb0ccaf104b2f13da0f092e09cc9411b3297\nwin:\n    set FILE=cross-file.txt\n    echo [binaries] > %FILE%\n    echo c = \'cl\' >> %FILE%\n    echo cpp = \'cl\' >> %FILE%\n    echo ar = \'lib\' >> %FILE%\n    echo windres = \'rc\' >> %FILE%\n    echo [host_machine] >> %FILE%\n    echo system = \'windows\' >> %FILE%\n    echo cpu_family = \'%TARGET%\' >> %FILE%\n    echo cpu = \'%TARGET%\' >> %FILE%\n    echo endian = \'little\' >> %FILE%\n\ndepends:python/Scripts/activate.bat\n    %THIRDPARTY_DIR%\\python\\Scripts\\activate.bat\n    meson setup --cross-file %FILE% --prefix %LIBS_DIR%/local --default-library=static --buildtype=debug -Denable_tools=false -Denable_tests=false %DAV1D_ASM_DISABLE% -Db_vscrt=mtd builddir-debug\n    meson compile -C builddir-debug\n    meson install -C builddir-debug\nrelease:\n    meson setup --cross-file %FILE% --prefix %LIBS_DIR%/local --default-library=static --buildtype=release -Denable_tools=false -Denable_tests=false -Db_vscrt=mt builddir-release\n    meson compile -C builddir-release\n    meson install -C builddir-release\nwin:\n    copy %LIBS_DIR%\\local\\lib\\libdav1d.a %LIBS_DIR%\\local\\lib\\dav1d.lib\n    deactivate\nmac:\n    buildOneArch() {\n        arch=$1\n        folder=`pwd`/$2\n\n        meson setup \\\n            --cross-file ../patches/macos_meson_${arch}.txt \\\n            --prefix ${USED_PREFIX} \\\n            --default-library=static \\\n            --buildtype=minsize \\\n            -Denable_tools=false \\\n            -Denable_tests=false \\\n            ${folder}\n        meson compile -C ${folder}\n        meson install -C ${folder}\n\n        mv ${USED_PREFIX}/lib/libdav1d.a ${folder}/libdav1d.a\n    }\n\n    buildOneArch arm64 build.arm64\n    buildOneArch x86_64 build\n\n    lipo -create build.arm64/libdav1d.a build/libdav1d.a -output ${USED_PREFIX}/lib/libdav1d.a\n')
stage('openh264', '\n    git clone -b v2.6.0 https://github.com/cisco/openh264.git\n    cd openh264\nwin32:\n    SET "TARGET=x86"\nwin64:\n    SET "TARGET=x86_64"\nwinarm:\n    SET "TARGET=aarch64"\n    SET "PATH=%LIBS_DIR%\\gas-preprocessor;%PATH%"\nwin:\n    set FILE=cross-file.txt\n    echo [binaries] > %FILE%\n    echo c = \'cl\' >> %FILE%\n    echo cpp = \'cl\' >> %FILE%\n    echo ar = \'lib\' >> %FILE%\n    echo windres = \'rc\' >> %FILE%\n    echo [host_machine] >> %FILE%\n    echo system = \'windows\' >> %FILE%\n    echo cpu_family = \'%TARGET%\' >> %FILE%\n    echo cpu = \'%TARGET%\' >> %FILE%\n    echo endian = \'little\' >> %FILE%\n\ndepends:python/Scripts/activate.bat\n    %THIRDPARTY_DIR%\\python\\Scripts\\activate.bat\n    meson setup --cross-file %FILE% --prefix %LIBS_DIR%/local --default-library=static --buildtype=debug -Db_vscrt=mtd builddir-debug\n    meson compile -C builddir-debug\n    meson install -C builddir-debug\nrelease:\n    meson setup --cross-file %FILE% --prefix %LIBS_DIR%/local --default-library=static --buildtype=release -Db_vscrt=mt builddir-release\n    meson compile -C builddir-release\n    meson install -C builddir-release\nwin:\n    copy %LIBS_DIR%\\local\\lib\\libopenh264.a %LIBS_DIR%\\local\\lib\\openh264.lib\n    deactivate\nmac:\n    buildOneArch() {\n        arch=$1\n        folder=`pwd`/$2\n\n        meson setup             --cross-file ../patches/macos_meson_${arch}.txt             --prefix ${USED_PREFIX}             --default-library=static             --buildtype=minsize             ${folder}\n        meson compile -C ${folder}\n        meson install -C ${folder}\n\n        mv ${USED_PREFIX}/lib/libopenh264.a ${folder}/libopenh264.a\n    }\n\n    buildOneArch aarch64 build.aarch64\n    buildOneArch x86_64 build.x86_64\n\n    lipo -create build.aarch64/libopenh264.a build.x86_64/libopenh264.a -output ${USED_PREFIX}/lib/libopenh264.a\n')
stage('libavif', '\n    git clone -b v1.4.2 https://github.com/AOMediaCodec/libavif.git\n    cd libavif\nwin:\n    cmake . ^\n        -DCMAKE_INSTALL_PREFIX=%LIBS_DIR%/local ^\n        -DCMAKE_MSVC_RUNTIME_LIBRARY="MultiThreaded$<$<CONFIG:Debug>:Debug>" ^\n        -DCMAKE_POLICY_DEFAULT_CMP0091=NEW ^\n        -DBUILD_SHARED_LIBS=OFF ^\n        -DAVIF_ENABLE_WERROR=OFF ^\n        -DAVIF_CODEC_DAV1D=SYSTEM ^\n        -DAVIF_LIBYUV=OFF\n    cmake --build . --config Debug\n    cmake --install . --config Debug\nrelease:\n    cmake --build . --config Release\n    cmake --install . --config Release\nmac:\n    cmake . \\\n        -D CMAKE_OSX_ARCHITECTURES="x86_64;arm64" \\\n        -D CMAKE_INSTALL_PREFIX:STRING=$USED_PREFIX \\\n        -D BUILD_SHARED_LIBS=OFF \\\n        -D AVIF_ENABLE_WERROR=OFF \\\n        -D AVIF_CODEC_DAV1D=SYSTEM \\\n        -D AVIF_LIBYUV=OFF\n    cmake --build . --config MinSizeRel\n    cmake --install . --config MinSizeRel\n')
stage('libwebp', '\n    git clone -b v1.6.0 https://github.com/webmproject/libwebp.git\n    cd libwebp\nwin:\n    nmake /f Makefile.vc CFG=debug-static OBJDIR=out RTLIBCFG=static all\n    nmake /f Makefile.vc CFG=release-static OBJDIR=out RTLIBCFG=static all\n    copy out\\release-static\\$X8664\\lib\\libwebp.lib out\\release-static\\$X8664\\lib\\webp.lib\n    copy out\\release-static\\$X8664\\lib\\libwebpdemux.lib out\\release-static\\$X8664\\lib\\webpdemux.lib\n    copy out\\release-static\\$X8664\\lib\\libwebpmux.lib out\\release-static\\$X8664\\lib\\webpmux.lib\nmac:\n    buildOneArch() {\n        arch=$1\n        folder=$2\n\n        CFLAGS=$UNGUARDED cmake -B $folder . \\\n            -D CMAKE_BUILD_TYPE=Release \\\n            -D CMAKE_INSTALL_PREFIX=$USED_PREFIX \\\n            -D CMAKE_OSX_ARCHITECTURES=$arch \\\n            -D WEBP_BUILD_ANIM_UTILS=OFF \\\n            -D WEBP_BUILD_CWEBP=OFF \\\n            -D WEBP_BUILD_DWEBP=OFF \\\n            -D WEBP_BUILD_GIF2WEBP=OFF \\\n            -D WEBP_BUILD_IMG2WEBP=OFF \\\n            -D WEBP_BUILD_VWEBP=OFF \\\n            -D WEBP_BUILD_WEBPMUX=OFF \\\n            -D WEBP_BUILD_WEBPINFO=OFF \\\n            -D WEBP_BUILD_EXTRAS=OFF\n        cmake --build $folder\n    }\n    buildOneArch arm64 build.arm64\n    buildOneArch x86_64 build\n\n    lipo -create build.arm64/libsharpyuv.a build/libsharpyuv.a -output build/libsharpyuv.a\n    lipo -create build.arm64/libwebp.a build/libwebp.a -output build/libwebp.a\n    lipo -create build.arm64/libwebpdemux.a build/libwebpdemux.a -output build/libwebpdemux.a\n    lipo -create build.arm64/libwebpmux.a build/libwebpmux.a -output build/libwebpmux.a\n    cmake --install build\n')
stage('libjxl', '\n    git clone -b v0.12.0 --recursive --shallow-submodules https://github.com/libjxl/libjxl.git\n    cd libjxl\n' + setVar('cmake_defines', '\n    -DBUILD_SHARED_LIBS=OFF\n    -DBUILD_TESTING=OFF\n    -DJPEGXL_ENABLE_FUZZERS=OFF\n    -DJPEGXL_ENABLE_DEVTOOLS=OFF\n    -DJPEGXL_ENABLE_TOOLS=OFF\n    -DJPEGXL_ENABLE_DOXYGEN=OFF\n    -DJPEGXL_ENABLE_MANPAGES=OFF\n    -DJPEGXL_ENABLE_EXAMPLES=OFF\n    -DJPEGXL_ENABLE_JNI=OFF\n    -DJPEGXL_ENABLE_SJPEG=OFF\n    -DJPEGXL_ENABLE_OPENEXR=OFF\n    -DJPEGXL_ENABLE_SKCMS=ON\n    -DJPEGXL_ENABLE_VIEWERS=OFF\n    -DJPEGXL_ENABLE_TCMALLOC=OFF\n    -DJPEGXL_ENABLE_PLUGINS=OFF\n    -DJPEGXL_ENABLE_COVERAGE=OFF\n    -DJPEGXL_WARNINGS_AS_ERRORS=OFF\n') + '\nwin:\n    cmake . ^\n        -DCMAKE_INSTALL_PREFIX=%LIBS_DIR%/local ^\n        -DCMAKE_MSVC_RUNTIME_LIBRARY="MultiThreaded$<$<CONFIG:Debug>:Debug>" ^\n        -DCMAKE_C_FLAGS="/DJXL_STATIC_DEFINE /DJXL_THREADS_STATIC_DEFINE /DJXL_CMS_STATIC_DEFINE" ^\n        -DCMAKE_CXX_FLAGS="/DJXL_STATIC_DEFINE /DJXL_THREADS_STATIC_DEFINE /DJXL_CMS_STATIC_DEFINE" ^\n        %cmake_defines%\n    cmake --build . --config Debug\n    cmake --install . --config Debug\nrelease:\n    cmake --build . --config Release\n    cmake --install . --config Release\nmac:\n    cmake . \\\n        -D CMAKE_OSX_ARCHITECTURES="x86_64;arm64" \\\n        -D CMAKE_INSTALL_PREFIX:STRING=$USED_PREFIX \\\n        ${cmake_defines}\n    cmake --build . --config MinSizeRel\n    cmake --install . --config MinSizeRel\n')
stage('libvpx', '\n    git clone https://github.com/webmproject/libvpx.git\ndepends:patches/libvpx/*.patch\n    cd libvpx\n    git checkout v1.14.1\nwin:\n    for /r %%i in (..\\patches\\libvpx\\*) do git apply %%i\n\n    SET PATH=%THIRDPARTY_DIR%\\msys64\\usr\\bin;%PATH%\n    SET CHERE_INVOKING=enabled_from_arguments\n    SET MSYS2_PATH_TYPE=inherit\n\nwin32:\n    SET "TOOLCHAIN=x86-win32-vs17"\nwin64:\n    SET "TOOLCHAIN=x86_64-win64-vs17"\nwinarm:\n    SET "TOOLCHAIN=arm64-win64-vs17-v145"\nwin:\ndepends:patches/build_libvpx_win.sh\n    bash --login ../patches/build_libvpx_win.sh\nmac:\n    find ../patches/libvpx -type f -print0 | sort -z | xargs -0 git apply\n\n    ./configure --prefix=$USED_PREFIX     --target=arm64-darwin20-gcc     --disable-examples     --disable-unit-tests     --disable-tools     --disable-docs     --enable-vp8     --enable-vp9     --enable-webm-io     --size-limit=4096x4096\n\n    make $MAKE_THREADS_CNT\n\n    mkdir out.arm64\n    mv libvpx.a out.arm64\n\n    make clean\n\n    ./configure --prefix=$USED_PREFIX     --target=x86_64-darwin20-gcc     --disable-examples     --disable-unit-tests     --disable-tools     --disable-docs     --enable-vp8     --enable-vp9     --enable-webm-io\n\n    make $MAKE_THREADS_CNT\n\n    mkdir out.x86_64\n    mv libvpx.a out.x86_64\n\n    lipo -create out.arm64/libvpx.a out.x86_64/libvpx.a -output libvpx.a\n\n    make install\n')
stage('liblcms2', '\n    git clone -b lcms2.16 https://github.com/mm2/Little-CMS.git liblcms2\n    cd liblcms2\nwin:\ndepends:python/Scripts/activate.bat\n    %THIRDPARTY_DIR%\\python\\Scripts\\activate.bat\n    meson setup --default-library=static --buildtype=debug -Db_vscrt=mtd out/Debug\n    meson compile -C out/Debug\n    meson setup --default-library=static --buildtype=release -Db_vscrt=mt out/Release\n    meson compile -C out/Release\n    deactivate\nmac:\n    buildOneArch() {\n        arch=$1\n        folder=`pwd`/$2\n\n        meson setup \\\n            --cross-file ../patches/macos_meson_${arch}.txt \\\n            --prefix ${USED_PREFIX} \\\n            --default-library=static \\\n            --buildtype=minsize \\\n            ${folder}\n        meson compile -C ${folder}\n        meson install -C ${folder}\n\n        mv ${USED_PREFIX}/lib/liblcms2.a ${folder}/liblcms2.a\n    }\n\n    buildOneArch arm64 build.arm64\n    buildOneArch x86_64 build\n\n    lipo -create build.arm64/liblcms2.a build/liblcms2.a -output ${USED_PREFIX}/lib/liblcms2.a\n')
stage('nv-codec-headers', '\nwin:\n    git clone -b n12.1.14.0 https://github.com/FFmpeg/nv-codec-headers.git\n')
stage('regex', '\n    git clone -b boost-1.83.0 https://github.com/boostorg/regex.git\n')
stage('ffmpeg', '\n    git clone --depth 1 -b n8.1.3 https://github.com/FFmpeg/FFmpeg.git ffmpeg\n    cd ffmpeg\nwin:\ndepends:patches/ffmpeg.patch\n    git apply ../patches/ffmpeg.patch\n    python -c "from pathlib import Path; p=Path(\'configure\'); s=p.read_text(); anchor=chr(94); assert \'grep -q \'+anchor+\'Microsoft\' in s; p.write_bytes(s.replace(\'grep -q \'+anchor+\'Microsoft\', \'grep -q Microsoft\').replace(\'grep \'+anchor+\'Microsoft\', \'grep Microsoft\').encode())"\n\n    SET PATH=%THIRDPARTY_DIR%\\msys64\\usr\\bin;%PATH%\n    SET CHERE_INVOKING=enabled_from_arguments\n    SET MSYS2_PATH_TYPE=inherit\n\n    SET "ARCH_PARAM="\nwinarm:\n    SET "ARCH_PARAM=--arch=aarch64"\nwin:\ndepends:patches/build_ffmpeg_win.sh\n    bash --login ../patches/build_ffmpeg_win.sh\nmac:\n    export PKG_CONFIG_PATH=$USED_PREFIX/lib/pkgconfig\n\n    configureFFmpeg() {\n        arch=$1\n\n        ./configure --prefix=$USED_PREFIX         --enable-cross-compile         --target-os=darwin         --arch="$arch"         --extra-cflags="$MIN_VER -arch $arch $UNGUARDED -DCONFIG_SAFE_BITSTREAM_READER=1 -I$USED_PREFIX/include"         --extra-cxxflags="$MIN_VER -arch $arch $UNGUARDED -DCONFIG_SAFE_BITSTREAM_READER=1 -I$USED_PREFIX/include"         --extra-ldflags="$MIN_VER -arch $arch $USED_PREFIX/lib/libopus.a -lc++"         --disable-programs         --disable-doc         --disable-network         --disable-everything         --enable-protocol=file         --enable-libdav1d         --enable-libopenh264         --enable-libopus         --enable-libvpx         --enable-hwaccel=h264_videotoolbox         --enable-hwaccel=hevc_videotoolbox         --enable-hwaccel=mpeg1_videotoolbox         --enable-hwaccel=mpeg2_videotoolbox         --enable-hwaccel=mpeg4_videotoolbox         --enable-decoder=aac         --enable-decoder=aac_at         --enable-decoder=aac_fixed         --enable-decoder=aac_latm         --enable-decoder=aasc         --enable-decoder=ac3         --enable-decoder=alac         --enable-decoder=alac_at         --enable-decoder=av1         --enable-decoder=eac3         --enable-decoder=flac         --enable-decoder=gif         --enable-decoder=h264         --enable-decoder=hevc         --enable-decoder=libdav1d         --enable-decoder=libvpx_vp8         --enable-decoder=libvpx_vp9         --enable-decoder=mp1         --enable-decoder=mp1float         --enable-decoder=mp2         --enable-decoder=mp2float         --enable-decoder=mp3         --enable-decoder=mp3adu         --enable-decoder=mp3adufloat         --enable-decoder=mp3float         --enable-decoder=mp3on4         --enable-decoder=mp3on4float         --enable-decoder=mpeg4         --enable-decoder=msmpeg4v2         --enable-decoder=msmpeg4v3         --enable-decoder=opus         --enable-decoder=pcm_alaw         --enable-decoder=pcm_alaw_at         --enable-decoder=pcm_f32be         --enable-decoder=pcm_f32le         --enable-decoder=pcm_f64be         --enable-decoder=pcm_f64le         --enable-decoder=pcm_lxf         --enable-decoder=pcm_mulaw         --enable-decoder=pcm_mulaw_at         --enable-decoder=pcm_s16be         --enable-decoder=pcm_s16be_planar         --enable-decoder=pcm_s16le         --enable-decoder=pcm_s16le_planar         --enable-decoder=pcm_s24be         --enable-decoder=pcm_s24daud         --enable-decoder=pcm_s24le         --enable-decoder=pcm_s24le_planar         --enable-decoder=pcm_s32be         --enable-decoder=pcm_s32le         --enable-decoder=pcm_s32le_planar         --enable-decoder=pcm_s64be         --enable-decoder=pcm_s64le         --enable-decoder=pcm_s8         --enable-decoder=pcm_s8_planar         --enable-decoder=pcm_u16be         --enable-decoder=pcm_u16le         --enable-decoder=pcm_u24be         --enable-decoder=pcm_u24le         --enable-decoder=pcm_u32be         --enable-decoder=pcm_u32le         --enable-decoder=pcm_u8         --enable-decoder=vorbis         --enable-decoder=vp8         --enable-decoder=wavpack         --enable-decoder=wmalossless         --enable-decoder=wmapro         --enable-decoder=wmav1         --enable-decoder=wmav2         --enable-decoder=wmavoice         --enable-encoder=aac         --enable-encoder=libopus         --enable-encoder=libopenh264         --enable-encoder=libvpx_vp9         --enable-encoder=pcm_s16le         --enable-filter=atempo         --enable-parser=aac         --enable-parser=aac_latm         --enable-parser=flac         --enable-parser=gif         --enable-parser=h264         --enable-parser=hevc         --enable-parser=mpeg4video         --enable-parser=mpegaudio         --enable-parser=opus         --enable-parser=vorbis         --enable-demuxer=aac         --enable-demuxer=flac         --enable-demuxer=gif         --enable-demuxer=h264         --enable-demuxer=hevc         --enable-demuxer=matroska         --enable-demuxer=m4v         --enable-demuxer=mov         --enable-demuxer=mp3         --enable-demuxer=ogg         --enable-demuxer=wav         --enable-muxer=mp4         --enable-muxer=ogg         --enable-muxer=opus         --enable-muxer=wav         --enable-muxer=webm\n    }\n\n    configureFFmpeg arm64\n    make $MAKE_THREADS_CNT\n\n    mkdir out.arm64\n    mv libavfilter/libavfilter.a out.arm64\n    mv libavformat/libavformat.a out.arm64\n    mv libavcodec/libavcodec.a out.arm64\n    mv libswresample/libswresample.a out.arm64\n    mv libswscale/libswscale.a out.arm64\n    mv libavutil/libavutil.a out.arm64\n\n    make clean\n\n    configureFFmpeg x86_64\n    make $MAKE_THREADS_CNT\n\n    mkdir out.x86_64\n    mv libavfilter/libavfilter.a out.x86_64\n    mv libavformat/libavformat.a out.x86_64\n    mv libavcodec/libavcodec.a out.x86_64\n    mv libswresample/libswresample.a out.x86_64\n    mv libswscale/libswscale.a out.x86_64\n    mv libavutil/libavutil.a out.x86_64\n\n    lipo -create out.arm64/libavfilter.a out.x86_64/libavfilter.a -output libavfilter/libavfilter.a\n    lipo -create out.arm64/libavformat.a out.x86_64/libavformat.a -output libavformat/libavformat.a\n    lipo -create out.arm64/libavcodec.a out.x86_64/libavcodec.a -output libavcodec/libavcodec.a\n    lipo -create out.arm64/libswresample.a out.x86_64/libswresample.a -output libswresample/libswresample.a\n    lipo -create out.arm64/libswscale.a out.x86_64/libswscale.a -output libswscale/libswscale.a\n    lipo -create out.arm64/libavutil.a out.x86_64/libavutil.a -output libavutil/libavutil.a\n\n    make install\n')
stage('libheif', '\ndepends:patches/libheif.patch\n    git clone -b v1.23.5 https://github.com/strukturag/libheif.git\n    cd libheif\n    git apply ../patches/libheif.patch\nwin:\n    %THIRDPARTY_DIR%\\msys64\\usr\\bin\\sed.exe -i \'s/HAVE_VISIBILITY/LIBHEIF_STATIC_BUILD/g\' libheif/CMakeLists.txt\n    %THIRDPARTY_DIR%\\msys64\\usr\\bin\\sed.exe -i \'s/HAVE_VISIBILITY/LIBHEIF_STATIC_BUILD/g\' heifio/CMakeLists.txt\n    cmake . ^\n        -DCMAKE_INSTALL_PREFIX=%LIBS_DIR%/local ^\n        -DCMAKE_MSVC_RUNTIME_LIBRARY="MultiThreaded$<$<CONFIG:Debug>:Debug>" ^\n        -DBUILD_SHARED_LIBS=OFF ^\n        -DBUILD_DOCUMENTATION=OFF ^\n        -DBUILD_TESTING=OFF ^\n        -DENABLE_PLUGIN_LOADING=OFF ^\n        -DWITH_LIBDE265=OFF ^\n        -DWITH_FFMPEG_DECODER=ON ^\n        -DFFMPEG_ROOT=%LIBS_DIR%/local ^\n        -DWITH_X264=OFF ^\n        -DWITH_OpenH264_DECODER=OFF ^\n        -DWITH_SvtEnc=OFF ^\n        -DWITH_SvtEnc_PLUGIN=OFF ^\n        -DWITH_RAV1E=OFF ^\n        -DWITH_RAV1E_PLUGIN=OFF ^\n        -DWITH_LIBSHARPYUV=OFF ^\n        -DCMAKE_DISABLE_FIND_PACKAGE_TIFF=TRUE ^\n        -DCMAKE_DISABLE_FIND_PACKAGE_JPEG=TRUE ^\n        -DCMAKE_DISABLE_FIND_PACKAGE_PNG=TRUE ^\n        -DWITH_EXAMPLES=OFF\n    cmake --build . --config Debug\n    cmake --install . --config Debug\nrelease:\n    cmake --build . --config Release\n    cmake --install . --config Release\nmac:\n    cmake . \\\n        -D CMAKE_OSX_ARCHITECTURES="x86_64;arm64" \\\n        -D CMAKE_INSTALL_PREFIX:STRING=$USED_PREFIX \\\n        -D BUILD_SHARED_LIBS=OFF \\\n        -D BUILD_DOCUMENTATION=OFF \\\n        -D BUILD_TESTING=OFF \\\n        -D ENABLE_PLUGIN_LOADING=OFF \\\n        -D WITH_GDK_PIXBUF=OFF \\\n        -D WITH_AOM_ENCODER=OFF \\\n        -D WITH_AOM_DECODER=OFF \\\n        -D WITH_X265=OFF \\\n        -D WITH_X264=OFF \\\n        -D WITH_OpenH264_DECODER=OFF \\\n        -D WITH_SvtEnc=OFF \\\n        -D WITH_RAV1E=OFF \\\n        -D WITH_DAV1D=OFF \\\n        -D WITH_LIBDE265=OFF \\\n        -D WITH_FFMPEG_DECODER=ON \\\n        -D FFMPEG_ROOT=$USED_PREFIX \\\n        -D WITH_LIBSHARPYUV=OFF \\\n        -D CMAKE_DISABLE_FIND_PACKAGE_TIFF=TRUE \\\n        -D CMAKE_DISABLE_FIND_PACKAGE_JPEG=TRUE \\\n        -D CMAKE_DISABLE_FIND_PACKAGE_PNG=TRUE \\\n        -D WITH_EXAMPLES=OFF\n    cmake --build . --config MinSizeRel\n    cmake --install . --config MinSizeRel\n')
stage('openal-soft', '\n    git clone https://github.com/telegramdesktop/openal-soft.git\n    cd openal-soft\nwin:\n    git checkout 00cb9b649c\n    cmake -B build . ^\n        -D LIBTYPE:STRING=STATIC ^\n        -D FORCE_STATIC_VCRT=ON ^\n        -D ALSOFT_UTILS=OFF ^\n        -D ALSOFT_EXAMPLES=OFF ^\n        -D ALSOFT_TESTS=OFF\n    cmake --build build --config Debug\nrelease:\n    cmake --build build --config RelWithDebInfo\nmac:\n    git checkout coreaudio_device_uid\n    CFLAGS=$UNGUARDED CPPFLAGS=$UNGUARDED cmake -B build . \\\n        -D CMAKE_BUILD_TYPE=RelWithDebInfo \\\n        -D CMAKE_INSTALL_PREFIX:PATH=$USED_PREFIX \\\n        -D ALSOFT_EXAMPLES=OFF \\\n        -D ALSOFT_UTILS=OFF \\\n        -D ALSOFT_TESTS=OFF \\\n        -D LIBTYPE:STRING=STATIC \\\n        -D CMAKE_OSX_ARCHITECTURES="x86_64;arm64"\n    cmake --build build\n    cmake --install build\n')
if 'build-stackwalk' in options:
    stage('stackwalk', '\nmac:\n    git clone https://chromium.googlesource.com/breakpad/breakpad stackwalk\n    cd stackwalk\n    git checkout dfcb7b6799\ndepends:patches/breakpad.diff\n    git apply ../patches/breakpad.diff\n    git clone -b release-1.11.0 https://github.com/google/googletest src/testing\n    git clone https://chromium.googlesource.com/linux-syscall-support src/third_party/lss\n    cd src/third_party/lss\n    git checkout e1e7b0ad8e\n    cd ../../build\n    PYTHONPATH=$THIRDPARTY_DIR/gyp python3 gyp_breakpad\n    cd ../processor\n    xcodebuild -project processor.xcodeproj -target minidump_stackwalk -configuration Release MACOSX_DEPLOYMENT_TARGET=$MACOSX_DEPLOYMENT_TARGET build\n')
macBreakpadBuild = '\nmac:\n    cd src/client/mac\n    xcodebuild -project Breakpad.xcodeproj -target Breakpad -configuration Debug MACOSX_DEPLOYMENT_TARGET=$MACOSX_DEPLOYMENT_TARGET build\nrelease:\n    xcodebuild -project Breakpad.xcodeproj -target Breakpad -configuration Release MACOSX_DEPLOYMENT_TARGET=$MACOSX_DEPLOYMENT_TARGET build\n    cd ../../tools/mac/dump_syms\n    xcodebuild -project dump_syms.xcodeproj -target dump_syms -configuration Release MACOSX_DEPLOYMENT_TARGET=$MACOSX_DEPLOYMENT_TARGET build\n'
if mac and macRelease:
    macBreakpadBuild = '\nversion: ' + computeFileHash(os.path.join(scriptPath, 'breakpad/CMakeLists.txt')) + '\nmac:\n    cmake -S "$PREPARE_DIR/breakpad" -B out -G "Ninja Multi-Config" \\\n        -DBREAKPAD_SOURCE_DIR="$PWD" \\\n        -DCMAKE_INSTALL_PREFIX="$PWD" \\\n        -DCMAKE_OSX_ARCHITECTURES="x86_64;arm64"\n    cmake --build out --config Debug --parallel\n    cmake --install out --config Debug\nrelease:\n    cmake --build out --config Release --parallel\n    cmake --install out --config Release\n'
stage('breakpad', '\n    git clone https://chromium.googlesource.com/breakpad/breakpad\n    cd breakpad\n    git checkout dfcb7b6799\ndepends:patches/breakpad.diff\n    git apply ../patches/breakpad.diff\n    git clone -b release-1.11.0 https://github.com/google/googletest src/testing\nwin:\n    SET "PYTHONUTF8=1"\n    SET "FolderPostfix="\n    SET "ToolsetProp="\nwin64:\n    SET "FolderPostfix=_x64"\nwinarm:\n    SET "FolderPostfix=_ARM64"\n    SET "ToolsetProp=/property:PlatformToolset=v145"\nwin:\ndepends:python/Scripts/activate.bat\n    %THIRDPARTY_DIR%\\python\\Scripts\\activate.bat\n    cd src\\client\\windows\n    gyp --no-circular-check breakpad_client.gyp --format=ninja -G ninja_use_custom_environment_files\n    cd ..\\..\n    python "%LIBS_DIR%\\..\\..\\scripts\\prepare-breakpad-environment.py"\n    ninja -C out/Debug%FolderPostfix% common crash_generation_client exception_handler\nrelease:\n    ninja -C out/Release%FolderPostfix% common crash_generation_client exception_handler\n    cd tools\\windows\\dump_syms\n    gyp dump_syms.gyp --format=msvs\n    msbuild -m dump_syms.vcxproj /property:Configuration=Release /property:Platform="x64" %ToolsetProp%\nwin:\n    deactivate\nmac:\n    git clone https://chromium.googlesource.com/linux-syscall-support src/third_party/lss\n    cd src/third_party/lss\n    git checkout e1e7b0ad8e\n    cd ../../..\n' + macBreakpadBuild)
stage('crashpad', '\nmac:\n    git clone https://github.com/desktop-app/crashpad.git\n    cd crashpad\n    git checkout 3279fae3f0\n    git submodule init\n    git submodule update third_party/mini_chromium\n    ZLIB_PATH=$USED_PREFIX/include\n    ZLIB_LIB=$USED_PREFIX/lib/libz.a\n    mkdir out\n    cd out\n    mkdir Debug.x86_64\n    cd Debug.x86_64\n    cmake         -DCMAKE_BUILD_TYPE=Debug         -DCMAKE_OSX_ARCHITECTURES=x86_64         -DCRASHPAD_SPECIAL_TARGET=$SPECIAL_TARGET         -DCRASHPAD_ZLIB_INCLUDE_PATH=$ZLIB_PATH         -DCRASHPAD_ZLIB_LIB_PATH=$ZLIB_LIB ../..\n    cmake --build .\n    cd ..\n    mkdir Debug.arm64\n    cd Debug.arm64\n    cmake         -DCMAKE_BUILD_TYPE=Debug         -DCMAKE_OSX_ARCHITECTURES=arm64         -DCRASHPAD_SPECIAL_TARGET=$SPECIAL_TARGET         -DCRASHPAD_ZLIB_INCLUDE_PATH=$ZLIB_PATH         -DCRASHPAD_ZLIB_LIB_PATH=$ZLIB_LIB ../..\n    cmake --build .\n    cd ..\n    mkdir Debug\n    lipo -create Debug.arm64/crashpad_handler Debug.x86_64/crashpad_handler -output Debug/crashpad_handler\n    lipo -create Debug.arm64/libcrashpad_client.a Debug.x86_64/libcrashpad_client.a -output Debug/libcrashpad_client.a\nrelease:\n    mkdir Release.x86_64\n    cd Release.x86_64\n    cmake         -DCMAKE_BUILD_TYPE=Release         -DCMAKE_OSX_ARCHITECTURES=x86_64         -DCRASHPAD_SPECIAL_TARGET=$SPECIAL_TARGET         -DCRASHPAD_ZLIB_INCLUDE_PATH=$ZLIB_PATH         -DCRASHPAD_ZLIB_LIB_PATH=$ZLIB_LIB ../..\n    cmake --build .\n    cd ..\n    mkdir Release.arm64\n    cd Release.arm64\n    cmake         -DCMAKE_BUILD_TYPE=Release         -DCMAKE_OSX_ARCHITECTURES=arm64         -DCRASHPAD_SPECIAL_TARGET=$SPECIAL_TARGET         -DCRASHPAD_ZLIB_INCLUDE_PATH=$ZLIB_PATH         -DCRASHPAD_ZLIB_LIB_PATH=$ZLIB_LIB ../..\n    cmake --build .\n    cd ..\n    mkdir Release\n    lipo -create Release.arm64/crashpad_handler Release.x86_64/crashpad_handler -output Release/crashpad_handler\n    lipo -create Release.arm64/libcrashpad_client.a Release.x86_64/libcrashpad_client.a -output Release/libcrashpad_client.a\n')
if win and qt >= '6':
    stage('qt6_windows7', '\nwin32_win64:\n    git clone https://github.com/desktop-app/qt6_windows7_patches.git qt6_windows7\n    cd qt6_windows7\n    git checkout 9ce1ffe051161a22f7e78f715b042c773f868e59\n')
if win:
    stage('tg_angle', '\nwin32_win64:\n    git clone https://github.com/desktop-app/tg_angle.git\n    cd tg_angle\n    git checkout 9fd174a91e6155d1006c5f427366b23006f5d899\n    cmake -B out ^\n        -DTG_ANGLE_SPECIAL_TARGET=%SPECIAL_TARGET% ^\n        -DTG_ANGLE_ZLIB_INCLUDE_PATH=%LIBS_DIR%/zlib\n    cmake --build out --config Debug\nrelease:\n    cmake --build out --config Release\n')
if qt < '6':
    stage('qt_' + qt, '\n    git clone -b v$QT-lts-lgpl https://github.com/qt/qt5.git qt_$QT\n    cd qt_$QT\n    git submodule update --init --recursive --progress qtbase qtimageformats qtsvg\ndepends:patches/qtbase_' + qt + '/*.patch\ndepends:patches/qtsvg_' + qt + '/*.patch\nwin:\n    cd qtbase\n    setlocal enabledelayedexpansion\n    for /r %%i in (..\\..\\patches\\qtbase_%QT%\\*) do (\n        git apply %%i -v\n        if errorlevel 1 (\n            echo ERROR: Applying patch %%~nxi failed!\n            exit /b 1\n        )\n    )\n    cd ..\\qtsvg\n    for %%i in (..\\..\\patches\\qtsvg_%QT%\\*) do git apply %%i -v || exit /b 1\n    cd ..\n\n    SET CONFIGURATIONS=-debug\nrelease:\n    SET CONFIGURATIONS=-debug-and-release\nwin:\n    ' + removeDir('"%LIBS_DIR%\\Qt-' + qt + '"') + '\n    SET ANGLE_DIR=%LIBS_DIR%\\tg_angle\n    SET ANGLE_LIBS_DIR=%ANGLE_DIR%\\out\n    SET MOZJPEG_DIR=%LIBS_DIR%\\mozjpeg\n    SET OPENSSL_DIR=%LIBS_DIR%\\openssl3\n    SET OPENSSL_LIBS_DIR=%OPENSSL_DIR%\\out\n    SET ZLIB_LIBS_DIR=%LIBS_DIR%\\zlib\n    SET WEBP_DIR=%LIBS_DIR%\\libwebp\n    configure -prefix "%LIBS_DIR%\\Qt-%QT%" ^\n        %CONFIGURATIONS% ^\n        -force-debug-info ^\n        -opensource ^\n        -confirm-license ^\n        -static ^\n        -static-runtime ^\n        -opengl es2 -no-angle ^\n        -I "%ANGLE_DIR%\\include" ^\n        -D "KHRONOS_STATIC=" ^\n        -D "DESKTOP_APP_QT_STATIC_ANGLE=" ^\n        QMAKE_LIBS_OPENGL_ES2_DEBUG="%ANGLE_LIBS_DIR%\\Debug\\tg_angle.lib %ZLIB_LIBS_DIR%\\Debug\\libzsd.lib d3d9.lib dxgi.lib dxguid.lib" ^\n        QMAKE_LIBS_OPENGL_ES2_RELEASE="%ANGLE_LIBS_DIR%\\Release\\tg_angle.lib %ZLIB_LIBS_DIR%\\Release\\libzs.lib d3d9.lib dxgi.lib dxguid.lib" ^\n        -egl ^\n        QMAKE_LIBS_EGL_DEBUG="%ANGLE_LIBS_DIR%\\Debug\\tg_angle.lib %ZLIB_LIBS_DIR%\\Debug\\libzsd.lib d3d9.lib dxgi.lib dxguid.lib Gdi32.lib User32.lib" ^\n        QMAKE_LIBS_EGL_RELEASE="%ANGLE_LIBS_DIR%\\Release\\tg_angle.lib %ZLIB_LIBS_DIR%\\Release\\libzs.lib d3d9.lib dxgi.lib dxguid.lib Gdi32.lib User32.lib" ^\n        -openssl-linked ^\n        -I "%OPENSSL_DIR%\\include" ^\n        OPENSSL_LIBS_DEBUG="%OPENSSL_LIBS_DIR%.dbg\\libssl.lib %OPENSSL_LIBS_DIR%.dbg\\libcrypto.lib Ws2_32.lib Gdi32.lib Advapi32.lib Crypt32.lib User32.lib" ^\n        OPENSSL_LIBS_RELEASE="%OPENSSL_LIBS_DIR%\\libssl.lib %OPENSSL_LIBS_DIR%\\libcrypto.lib Ws2_32.lib Gdi32.lib Advapi32.lib Crypt32.lib User32.lib" ^\n        -I "%MOZJPEG_DIR%" ^\n        LIBJPEG_LIBS_DEBUG="%MOZJPEG_DIR%\\Debug\\jpeg-static.lib" ^\n        LIBJPEG_LIBS_RELEASE="%MOZJPEG_DIR%\\Release\\jpeg-static.lib" ^\n        -system-webp ^\n        -I "%WEBP_DIR%\\src" ^\n        -L "%WEBP_DIR%\\out\\release-static\\$X8664\\lib" ^\n        -mp ^\n        -no-feature-netlistmgr ^\n        -nomake examples ^\n        -nomake tests ^\n        -platform win32-msvc\n\n    rem jom -jN occasionally fails to create the shared mkspecs\\modules-inst\n    rem directory due to a race in qmake\'s mkpath under parallel builds; the\n    rem build is incremental, so simply retrying picks up where it stopped.\n    jom -j%NUMBER_OF_PROCESSORS% || jom -j%NUMBER_OF_PROCESSORS%\n    jom -j%NUMBER_OF_PROCESSORS% install\n')
else:
    qtAngleCmake = os.path.realpath(os.path.join(scriptPath, '../../../cmake/external/angle/qt.cmake')).replace('\\', '/')
    modifiedEnv['QT_ANGLE_CMAKE'] = qtAngleCmake
    branch = 'v$QT' + ('-lts-lgpl' if qt.startswith('6.2.') else '')
    stage('qt_' + qt, '\n    git clone --depth 1 -b ' + branch + ' https://github.com/qt/qt5.git qt_$QT\n    cd qt_$QT\n    git submodule update --init --recursive --depth 1 --progress qtbase qtimageformats qtshadertools qtsvg\ndepends:patches/qtbase_' + qt + '/*.patch\ndepends:patches/qtsvg_' + qt + '/*.patch\nwin32_win64:\ndepends:qt6_windows7/*.patch\nversion:' + computeFileHash(qtAngleCmake) + '\nmac:\n    if [ -d "../patches/qt6_highsierra" ]; then\n        find "$PWD/../patches/qt6_highsierra" -maxdepth 1 -name "*.patch" -print0 | sort -z | xargs -0 git -C qtbase apply -v\n    fi\n    find $PWD/../patches/qtbase_$QT -type f -print0 | sort -z | xargs -0 git -C qtbase apply -v\n    find $PWD/../patches/qtsvg_$QT -type f -print0 | sort -z | xargs -0 git -C qtsvg apply -v\n    sed -i.bak \'s/tqtc-//\' {qtimageformats,qtsvg}/dependencies.yaml\n\n    CONFIGURATIONS=-debug\n    ASSERTS=\nrelease:\n    CONFIGURATIONS=-debug-and-release\nmac_asserts:\n    ASSERTS=-force-asserts\nmac:\n    ./configure -prefix "$USED_PREFIX/Qt-$QT"         $CONFIGURATIONS         $ASSERTS         -force-debug-info         -opensource         -confirm-license         -static         -no-framework         -opengl desktop         -no-openssl         -securetransport         -system-webp         -I "$USED_PREFIX/include"         -no-feature-futimens         -no-feature-brotli         -no-feature-cxx17_filesystem         -platform macx-clang --         -DCMAKE_OSX_ARCHITECTURES="x86_64;arm64"         -DCMAKE_OSX_SYSROOT="$SDKROOT"         -DCMAKE_OSX_DEPLOYMENT_TARGET="$MACOSX_DEPLOYMENT_TARGET"         -DCMAKE_PREFIX_PATH="$USED_PREFIX"         -DQT_NO_HANDLE_APPLE_SINGLE_ARCH_CROSS_COMPILING=ON         -DQT_SYNC_HEADERS_AT_CONFIGURE_TIME=ON\n\n    cmake --build .\n    cmake --install .\nwin:\n    cd qtbase\n    setlocal enabledelayedexpansion\nwin32_win64:\n    for %%i in (..\\..\\qt6_windows7\\*.patch) do (\n        git apply %%i --ignore-whitespace -v\n        if errorlevel 1 (\n            echo ERROR: Applying patch %%~nxi failed!\n            exit /b 1\n        )\n    )\nwin:\n    for /r %%i in (..\\..\\patches\\qtbase_%QT%\\*) do (\n        git apply %%i --ignore-whitespace -v\n        if errorlevel 1 (\n            echo ERROR: Applying patch %%~nxi failed!\n            exit /b 1\n        )\n    )\n    cd ..\\qtsvg\n    for /r %%i in (..\\..\\patches\\qtsvg_%QT%\\*) do (\n        git apply %%i --ignore-whitespace -v\n        if errorlevel 1 (\n            echo ERROR: Applying patch %%~nxi failed!\n            exit /b 1\n        )\n    )\n    cd ..\n\n    SET CONFIGURATIONS=-debug\n    SET ASSERTS=\nrelease:\n    SET CONFIGURATIONS=-debug-and-release\nwin_asserts:\n    SET ASSERTS=-force-asserts\nwin:\n    ' + removeDir('"%LIBS_DIR%\\Qt' + qt + '"') + '\n    SET MOZJPEG_DIR=%LIBS_DIR%\\mozjpeg\n    SET OPENSSL_DIR=%LIBS_DIR%\\openssl3\n    SET OPENSSL_LIBS_DIR=%OPENSSL_DIR%\\out\n    SET ZLIB_LIBS_DIR=%LIBS_DIR%\\zlib\n    SET WEBP_DIR=%LIBS_DIR%\\libwebp\n    SET LCMS2_DIR=%LIBS_DIR%\\liblcms2\n    configure -prefix "%LIBS_DIR%\\Qt-%QT%" ^\n        %CONFIGURATIONS% ^\n        %ASSERTS% ^\n        -force-debug-info ^\n        -opensource ^\n        -confirm-license ^\n        -static ^\n        -static-runtime ^\n        -feature-c++20 ^\n        -openssl linked ^\n        -system-webp ^\n        -system-zlib ^\n        -system-libjpeg ^\nwin32_win64:\n        -trace no ^\n        -feature-egl ^\nwin32:\n        -no-feature-windows-ioring ^\nwin:\n        -platform win32-msvc ^\n        -D ZLIB_WINAPI ^\n        -- ^\nwin32_win64:\n        -D CMAKE_PROJECT_QtBase_INCLUDE:FILEPATH="%QT_ANGLE_CMAKE%" ^\n        -D DESKTOP_APP_ANGLE_DIR:PATH="%LIBS_DIR%\\tg_angle" ^\nwin:\n        -D OPENSSL_FOUND=1 ^\n        -D OPENSSL_INCLUDE_DIR="%OPENSSL_DIR%\\include" ^\n        -D LIB_EAY_DEBUG="%OPENSSL_LIBS_DIR%.dbg\\libcrypto.lib" ^\n        -D SSL_EAY_DEBUG="%OPENSSL_LIBS_DIR%.dbg\\libssl.lib" ^\n        -D LIB_EAY_RELEASE="%OPENSSL_LIBS_DIR%\\libcrypto.lib" ^\n        -D SSL_EAY_RELEASE="%OPENSSL_LIBS_DIR%\\libssl.lib" ^\n        -D JPEG_FOUND=1 ^\n        -D JPEG_INCLUDE_DIR="%MOZJPEG_DIR%" ^\n        -D JPEG_LIBRARY_DEBUG="%MOZJPEG_DIR%\\Debug\\jpeg-static.lib" ^\n        -D JPEG_LIBRARY_RELEASE="%MOZJPEG_DIR%\\Release\\jpeg-static.lib" ^\n        -D ZLIB_FOUND=1 ^\n        -D ZLIB_INCLUDE_DIR="%ZLIB_LIBS_DIR%" ^\n        -D ZLIB_LIBRARY_DEBUG="%ZLIB_LIBS_DIR%\\Debug\\libzsd.lib" ^\n        -D ZLIB_LIBRARY_RELEASE="%ZLIB_LIBS_DIR%\\Release\\libzs.lib" ^\n        -D WebP_INCLUDE_DIR="%WEBP_DIR%\\src" ^\n        -D WebP_demux_INCLUDE_DIR="%WEBP_DIR%\\src" ^\n        -D WebP_mux_INCLUDE_DIR="%WEBP_DIR%\\src" ^\n        -D WebP_LIBRARY="%WEBP_DIR%\\out\\release-static\\$X8664\\lib\\webp.lib" ^\n        -D WebP_demux_LIBRARY="%WEBP_DIR%\\out\\release-static\\$X8664\\lib\\webpdemux.lib" ^\n        -D WebP_mux_LIBRARY="%WEBP_DIR%\\out\\release-static\\$X8664\\lib\\webpmux.lib" ^\n        -D LCMS2_FOUND=1 ^\n        -D LCMS2_INCLUDE_DIR="%LCMS2_DIR%\\include" ^\n        -D LCMS2_LIBRARIES="%LCMS2_DIR%\\out\\Release\\src\\liblcms2.a"\n\n    cmake --build . --config Debug\n    cmake --install . --config Debug\n    cmake --build .\n    cmake --install .\n')
stage('tg_owt', '\n    git init tg_owt\n    cd tg_owt\n    git remote add origin https://github.com/desktop-app/tg_owt.git\n    git fetch --depth 1 origin 49ceed3985d8626b3a24bdb14d9c593a115cc6e8\n    git checkout --detach FETCH_HEAD\n    git submodule update --init --recursive --depth 1\nwin:\n    SET MOZJPEG_PATH=$LIBS_DIR/mozjpeg\n    SET OPUS_PATH=$USED_PREFIX/include/opus\n    SET OPENSSL_PATH=$LIBS_DIR/openssl3/include\n    SET LIBVPX_PATH=$USED_PREFIX/include\n    SET OPENH264_PATH=$USED_PREFIX/include\n    SET FFMPEG_PATH=$LIBS_DIR/ffmpeg\n    cmake -B out         -DCMAKE_MSVC_RUNTIME_LIBRARY="MultiThreaded$<$<CONFIG:Debug>:Debug>"         -DTG_OWT_BUILD_AUDIO_BACKENDS=OFF         -DTG_OWT_SPECIAL_TARGET=$SPECIAL_TARGET         -DTG_OWT_LIBJPEG_INCLUDE_PATH=$MOZJPEG_PATH         -DTG_OWT_OPENSSL_INCLUDE_PATH=$OPENSSL_PATH         -DTG_OWT_OPUS_INCLUDE_PATH=$OPUS_PATH         -DTG_OWT_LIBVPX_INCLUDE_PATH=$LIBVPX_PATH         -DTG_OWT_OPENH264_INCLUDE_PATH=$OPENH264_PATH         -DTG_OWT_FFMPEG_INCLUDE_PATH=$FFMPEG_PATH\n    cmake --build out --config Debug\nrelease:\n    cmake --build out --config Release\nmac:\n    MOZJPEG_PATH=$USED_PREFIX/include\n    OPUS_PATH=$USED_PREFIX/include/opus\n    LIBVPX_PATH=$USED_PREFIX/include\n    OPENH264_PATH=$USED_PREFIX/include\n    FFMPEG_PATH=$USED_PREFIX/include\n    mkdir out\n    cd out\n    mkdir Debug.x86_64\n    cd Debug.x86_64\n    cmake         -DCMAKE_BUILD_TYPE=Debug         -DCMAKE_OSX_ARCHITECTURES=x86_64         -DTG_OWT_BUILD_AUDIO_BACKENDS=OFF         -DTG_OWT_SPECIAL_TARGET=$SPECIAL_TARGET         -DTG_OWT_LIBJPEG_INCLUDE_PATH=$MOZJPEG_PATH         -DTG_OWT_OPENSSL_INCLUDE_PATH=$LIBS_DIR/openssl3/include         -DTG_OWT_OPUS_INCLUDE_PATH=$OPUS_PATH         -DTG_OWT_LIBVPX_INCLUDE_PATH=$LIBVPX_PATH         -DTG_OWT_OPENH264_INCLUDE_PATH=$OPENH264_PATH         -DTG_OWT_FFMPEG_INCLUDE_PATH=$FFMPEG_PATH ../..\n    cmake --build .\n    cd ..\n    mkdir Debug.arm64\n    cd Debug.arm64\n    cmake         -DCMAKE_BUILD_TYPE=Debug         -DCMAKE_OSX_ARCHITECTURES=arm64         -DTG_OWT_BUILD_AUDIO_BACKENDS=OFF         -DTG_OWT_SPECIAL_TARGET=$SPECIAL_TARGET         -DTG_OWT_LIBJPEG_INCLUDE_PATH=$MOZJPEG_PATH         -DTG_OWT_OPENSSL_INCLUDE_PATH=$LIBS_DIR/openssl3/include         -DTG_OWT_OPUS_INCLUDE_PATH=$OPUS_PATH         -DTG_OWT_LIBVPX_INCLUDE_PATH=$LIBVPX_PATH         -DTG_OWT_OPENH264_INCLUDE_PATH=$OPENH264_PATH         -DTG_OWT_FFMPEG_INCLUDE_PATH=$FFMPEG_PATH ../..\n    cmake --build .\n    cd ..\n    mkdir Debug\n    lipo -create Debug.arm64/libtg_owt.a Debug.x86_64/libtg_owt.a -output Debug/libtg_owt.a\nrelease:\n    mkdir Release.x86_64\n    cd Release.x86_64\n    cmake         -DCMAKE_BUILD_TYPE=Release         -DCMAKE_OSX_ARCHITECTURES=x86_64         -DTG_OWT_SPECIAL_TARGET=$SPECIAL_TARGET         -DTG_OWT_LIBJPEG_INCLUDE_PATH=$MOZJPEG_PATH         -DTG_OWT_OPENSSL_INCLUDE_PATH=$LIBS_DIR/openssl3/include         -DTG_OWT_OPUS_INCLUDE_PATH=$OPUS_PATH         -DTG_OWT_LIBVPX_INCLUDE_PATH=$LIBVPX_PATH         -DTG_OWT_OPENH264_INCLUDE_PATH=$OPENH264_PATH         -DTG_OWT_FFMPEG_INCLUDE_PATH=$FFMPEG_PATH ../..\n    cmake --build .\n    cd ..\n    mkdir Release.arm64\n    cd Release.arm64\n    cmake         -DCMAKE_BUILD_TYPE=Release         -DCMAKE_OSX_ARCHITECTURES=arm64         -DTG_OWT_SPECIAL_TARGET=$SPECIAL_TARGET         -DTG_OWT_LIBJPEG_INCLUDE_PATH=$MOZJPEG_PATH         -DTG_OWT_OPENSSL_INCLUDE_PATH=$LIBS_DIR/openssl3/include         -DTG_OWT_OPUS_INCLUDE_PATH=$OPUS_PATH         -DTG_OWT_LIBVPX_INCLUDE_PATH=$LIBVPX_PATH         -DTG_OWT_OPENH264_INCLUDE_PATH=$OPENH264_PATH         -DTG_OWT_FFMPEG_INCLUDE_PATH=$FFMPEG_PATH ../..\n    cmake --build .\n    cd ..\n    mkdir Release\n    lipo -create Release.arm64/libtg_owt.a Release.x86_64/libtg_owt.a -output Release/libtg_owt.a\n')
stage('ada', '\n    git clone -b v3.2.9 https://github.com/ada-url/ada.git\n    cd ada\nwin:\n    cmake -B out . ^\n        -D ADA_TESTING=OFF ^\n        -D ADA_TOOLS=OFF ^\n        -D ADA_INCLUDE_URL_PATTERN=OFF ^\n        -D CMAKE_MSVC_RUNTIME_LIBRARY="MultiThreaded$<$<CONFIG:Debug>:Debug>"\n    cmake --build out --config Debug\n    cmake --build out --config Release\nmac:\n    CFLAGS="$UNGUARDED" CPPFLAGS="$UNGUARDED" cmake -B build . \\\n        -D ADA_TESTING=OFF \\\n        -D ADA_TOOLS=OFF \\\n        -D CMAKE_OSX_ARCHITECTURES="x86_64;arm64" \\\n        -D CMAKE_INSTALL_PREFIX:STRING=$USED_PREFIX\n    cmake --build build\n    cmake --install build\n')
stage('tde2e', '\n    git init tde2e\n    cd tde2e\n    git remote add origin https://github.com/tdlib/td.git\n    git fetch --depth 1 origin 51743dfd01dff6179e2d8f7095729caa4e2222e9\n    git checkout --detach FETCH_HEAD\nwin:\n    SET OPENSSL_DIR=%LIBS_DIR%\\openssl3\n    SET OPENSSL_LIBS_DIR=%OPENSSL_DIR%\\out\n    SET ZLIB_LIBS_DIR=%LIBS_DIR%\\zlib\n    %THIRDPARTY_DIR%\\msys64\\usr\\bin\\sed -i "s/STREQUAL/MATCHES/" td/generate/CMakeLists.txt\n    mkdir out\n    cd out\n    mkdir Debug\n    cd Debug\n    cmake ^\n        -DOPENSSL_FOUND=1 ^\n        -DOPENSSL_INCLUDE_DIR=%OPENSSL_DIR%\\include ^\n        -DOPENSSL_CRYPTO_LIBRARY="%OPENSSL_LIBS_DIR%.dbg\\libcrypto.lib" ^\n        -DZLIB_FOUND=1 ^\n        -DZLIB_INCLUDE_DIR=%ZLIB_LIBS_DIR% ^\n        -DZLIB_LIBRARIES="%ZLIB_LIBS_DIR%\\Debug\\libzsd.lib" ^\n        -DCMAKE_CONFIGURATION_TYPES=Debug ^\n        -DCMAKE_MSVC_RUNTIME_LIBRARY="MultiThreaded$<$<CONFIG:Debug>:Debug>" ^\n        -DCMAKE_POLICY_DEFAULT_CMP0091=NEW ^\n        -DCMAKE_C_FLAGS="/DZLIB_WINAPI" ^\n        -DCMAKE_CXX_FLAGS="/DZLIB_WINAPI" ^\n        -DCMAKE_EXE_LINKER_FLAGS="/SAFESEH:NO Ws2_32.lib Gdi32.lib Advapi32.lib Crypt32.lib User32.lib %OPENSSL_LIBS_DIR%.dbg\\libssl.lib" ^\n        -DCMAKE_SHARED_LINKER_FLAGS="/SAFESEH:NO Ws2_32.lib Gdi32.lib Advapi32.lib Crypt32.lib User32.lib %OPENSSL_LIBS_DIR%.dbg\\libssl.lib" ^\n        -DTD_ENABLE_MULTI_PROCESSOR_COMPILATION=ON ^\n        -DTD_E2E_ONLY=ON ^\n        ../..\n    cmake --build . --config Debug\nrelease:\n    cd ..\n    mkdir Release\n    cd Release\n    cmake ^\n        -DOPENSSL_FOUND=1 ^\n        -DOPENSSL_INCLUDE_DIR=%OPENSSL_DIR%\\include ^\n        -DOPENSSL_CRYPTO_LIBRARY="%OPENSSL_LIBS_DIR%\\libcrypto.lib" ^\n        -DZLIB_FOUND=1 ^\n        -DZLIB_INCLUDE_DIR=%ZLIB_LIBS_DIR% ^\n        -DZLIB_LIBRARIES="%ZLIB_LIBS_DIR%\\Release\\libzs.lib" ^\n        -DCMAKE_CONFIGURATION_TYPES=Release ^\n        -DCMAKE_MSVC_RUNTIME_LIBRARY="MultiThreaded$<$<CONFIG:Debug>:Debug>" ^\n        -DCMAKE_POLICY_DEFAULT_CMP0091=NEW ^\n        -DCMAKE_C_FLAGS="/DZLIB_WINAPI" ^\n        -DCMAKE_CXX_FLAGS="/DZLIB_WINAPI" ^\n        -DCMAKE_EXE_LINKER_FLAGS="/SAFESEH:NO Ws2_32.lib Gdi32.lib Advapi32.lib Crypt32.lib User32.lib %OPENSSL_LIBS_DIR%\\libssl.lib" ^\n        -DCMAKE_SHARED_LINKER_FLAGS="/SAFESEH:NO Ws2_32.lib Gdi32.lib Advapi32.lib Crypt32.lib User32.lib %OPENSSL_LIBS_DIR%\\libssl.lib" ^\n        -DTD_ENABLE_MULTI_PROCESSOR_COMPILATION=ON ^\n        -DTD_E2E_ONLY=ON ^\n        ../..\n    cmake --build . --config Release\nmac:\n    buildTd() {\n        BUILD_CONFIG=$1\n        mkdir -p out/$BUILD_CONFIG\n        cd out/$BUILD_CONFIG\n        cmake             -DCMAKE_BUILD_TYPE=$BUILD_CONFIG             -DCMAKE_OSX_ARCHITECTURES="x86_64;arm64"             -DOPENSSL_FOUND=1             -DOPENSSL_INCLUDE_DIR=$LIBS_DIR/openssl3/include             -DOPENSSL_SSL_LIBRARY=$LIBS_DIR/openssl3/libssl.a             -DOPENSSL_CRYPTO_LIBRARY=$LIBS_DIR/openssl3/libcrypto.a             -DZLIB_FOUND=1             -DZLIB_LIBRARIES=$USED_PREFIX/lib/libz.a             -DTD_E2E_ONLY=ON             ../..\n        cmake --build .\n        cd ../..\n    }\n\n    buildTd Debug\nrelease:\n    buildTd Release\n')
tlottieRevision = '92df98dc20'
walletEngineRevision = 'e59e0d89d7ee90c388bf36e3334c5b276f396697'
stage('tlottie', '\nversion: 2\n    git init tlottie\n    cd tlottie\n    git remote add origin https://github.com/dkaraush/tlottie.git\n    git fetch --depth 1 origin 92df98dc209bc39b1e567ec74a8c86a0af5239de\n    git checkout --detach FETCH_HEAD\n')
stage('wallet-engine', '\nversion: 2\ndepends:patches/wallet-engine.patch\nwin:\n    SET "GIT_LFS_SKIP_SMUDGE=1"\nmac:\n    export GIT_LFS_SKIP_SMUDGE=1\nwin_mac:\n    git init wallet-engine\n    cd wallet-engine\n    git remote add origin https://github.com/i582/wallet-engine.git\n    git fetch --depth 1 origin ' + walletEngineRevision + '\n    git checkout --detach FETCH_HEAD\n    git apply ../patches/wallet-engine.patch\n')
stage('tdesktop_rust', '\nversion: 2.' + tlottieRevision + '.' + walletEngineRevision + '\ndepends:patches/wallet-engine.patch\nwin:\n    SET "RUSTUP_HOME=%THIRDPARTY_DIR%\\rust\\rustup"\n    SET "CARGO_HOME=%THIRDPARTY_DIR%\\rust\\cargo"\n    SET RUSTUP_TOOLCHAIN=' + rustToolchain + '\n    SET "PATH=%CARGO_HOME%\\bin;%PATH%"\nwin32:\n    SET "RUST_TARGET=i686-win7-windows-msvc"\n    SET "RUST_BUILD_STD=-Z build-std=std,panic_abort"\n    SET "RUSTC_BOOTSTRAP=1"\nwin64:\n    SET "RUST_TARGET=x86_64-win7-windows-msvc"\n    SET "RUST_BUILD_STD=-Z build-std=std,panic_abort"\n    SET "RUSTC_BOOTSTRAP=1"\nwinarm:\n    SET "RUST_TARGET=aarch64-pc-windows-msvc"\n    SET "RUST_BUILD_STD="\nwin:\n    cargo new --lib --vcs none tdesktop_rust\n    cd tdesktop_rust\n    echo pub use ::tlottie;> src\\lib.rs\n    echo pub use ::wallet_engine;>> src\\lib.rs\n    cargo add --path ..\\tlottie --features c-api\n    cargo add --path ..\\wallet-engine\n    cargo rustc --lib --release ^\n        --crate-type staticlib --crate-type cdylib ^\n        %RUST_BUILD_STD% ^\n        --target %RUST_TARGET% ^\n        --config "profile.release.opt-level=\'z\'" ^\n        --config "profile.release.lto=\'thin\'" ^\n        --config "profile.release.codegen-units=1" ^\n        --config "profile.release.panic=\'unwind\'" ^\n        --config "profile.release.package.tlottie.opt-level=3" ^\n        --config "target.%RUST_TARGET%.rustflags=[\'-C\',\'target-feature=+crt-static\']" ^\n        -- --print native-static-libs\n    mkdir out\\lib out\\include out\\include\\tlottie out\\include\\wallet_engine out\\src out\\src\\wallet_engine\n    copy target\\%RUST_TARGET%\\release\\tdesktop_rust.lib out\\lib\\tdesktop_rust.lib\n    copy ..\\tlottie\\include\\tlottie.h out\\include\\tlottie\\tlottie.h\n    cargo run --manifest-path ..\\wallet-engine\\bindgen\\cpp\\bindgen\\Cargo.toml --locked -- ^\n        --library --out-dir out\\include\\wallet_engine ^\n        target\\%RUST_TARGET%\\release\\tdesktop_rust.dll\n    move out\\include\\wallet_engine\\wallet_engine.cpp out\\src\\wallet_engine\\wallet_engine.cpp\nmac:\n    export RUSTUP_HOME=$THIRDPARTY_DIR/rust/rustup\n    export CARGO_HOME=$THIRDPARTY_DIR/rust/cargo\n    export RUSTUP_TOOLCHAIN=' + rustToolchain + '\n    export PATH=$CARGO_HOME/bin:$PATH\n    cargo new --lib --vcs none tdesktop_rust\n    cd tdesktop_rust\n    printf \'pub use ::tlottie;\\npub use ::wallet_engine;\\n\' > src/lib.rs\n    cargo add --path ../tlottie --features c-api\n    cargo add --path ../wallet-engine\n    buildOneArch() {\n        cargo rustc --lib --release \\\n            --crate-type staticlib --crate-type cdylib \\\n            --target $1 \\\n            --config "profile.release.opt-level=\'z\'" \\\n            --config "profile.release.lto=\'thin\'" \\\n            --config "profile.release.codegen-units=1" \\\n            --config "profile.release.panic=\'unwind\'" \\\n            --config "profile.release.package.tlottie.opt-level=3" \\\n            -- --print native-static-libs\n    }\n    buildOneArch aarch64-apple-darwin\n    buildOneArch x86_64-apple-darwin\n    mkdir -p $USED_PREFIX/lib $USED_PREFIX/include/tlottie $USED_PREFIX/include/wallet_engine $USED_PREFIX/src/wallet_engine\n    lipo -create target/aarch64-apple-darwin/release/libtdesktop_rust.a target/x86_64-apple-darwin/release/libtdesktop_rust.a -output $USED_PREFIX/lib/libtdesktop_rust.a\n    cp ../tlottie/include/tlottie.h $USED_PREFIX/include/tlottie/tlottie.h\n    cargo run --manifest-path ../wallet-engine/bindgen/cpp/bindgen/Cargo.toml --locked -- \\\n        --library --out-dir $USED_PREFIX/include/wallet_engine \\\n        target/aarch64-apple-darwin/release/libtdesktop_rust.dylib\n    mv $USED_PREFIX/include/wallet_engine/wallet_engine.cpp $USED_PREFIX/src/wallet_engine/wallet_engine.cpp\n')
if win:
    currentCodePage = subprocess.run('chcp', capture_output=True, shell=True, text=True, env=modifiedEnv).stdout.strip().split()[-1]
    subprocess.run('chcp 65001 > nul', shell=True, env=modifiedEnv)
    runStages()
    subprocess.run('chcp ' + currentCodePage + ' > nul', shell=True, env=modifiedEnv)
else:
    runStages()
