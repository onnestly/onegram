import argparse
from datetime import datetime
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from brand_client import make_icon, CopyIcons_FromIco

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--portable', type=Path, default=ROOT/'dist/OneGram-Windows-x64-1.0.3.zip')
    parser.add_argument('--output', type=Path, default=ROOT/'dist/OneGram-Setup-1.0.3-x64.exe')
    args = parser.parse_args()
    work = ROOT/'.local/installer'/datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    work.mkdir(parents=True)
    for name in ('install.cmd', 'install.ps1'): shutil.copy2(ROOT/'packaging'/name,work/name)
    shutil.copy2(args.portable,work/'payload.zip')
    with (work/'payload.zip').open('rb') as stream: digest=hashlib.file_digest(stream,'sha256').hexdigest()
    (work/'payload.sha256').write_text(digest,encoding='ascii')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    sed = '[Version]\nClass=IEXPRESS\nSEDVersion=3\n[Options]\nPackagePurpose=InstallApp\nShowInstallProgramWindow=0\nHideExtractAnimation=1\nUseLongFileName=1\nInsideCompressed=0\nCAB_FixedSize=0\nCAB_ResvCodeSigning=0\nRebootMode=N\nInstallPrompt=\nDisplayLicense=\nFinishMessage=\nTargetName='+str(args.output.resolve())+'\nFriendlyName=OneGram 1.0.3\nAppLaunched=cmd.exe /d /c install.cmd\nPostInstallCmd=<None>\nAdminQuietInstCmd=\nUserQuietInstCmd=\nSourceFiles=SourceFiles\n[Strings]\nFILE0="install.cmd"\nFILE1="install.ps1"\nFILE2="payload.zip"\nFILE3="payload.sha256"\n[SourceFiles]\nSourceFiles0='+str(work.resolve())+'\\\n[SourceFiles0]\n%FILE0%=\n%FILE1%=\n%FILE2%=\n%FILE3%=\n'
    config=work/'setup.sed';config.write_text(sed,encoding='ascii')
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    command=Path(os.environ.get('WINDIR','C:/Windows'))/'System32/iexpress.exe'
    environment=os.environ.copy();environment['TEMP']=environment['TMP']=str(work)
    subprocess.run([str(command),'/N','/Q',str(config)],cwd=work,startupinfo=startup,env=environment,check=True)
    if not args.output.is_file() or args.output.stat().st_size < 1024 * 1024:
        raise RuntimeError('IExpress did not produce a complete installer')
    icon = work / 'onegram.ico'
    make_icon().save(icon, sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])
    CopyIcons_FromIco(str(args.output), [str(icon)])
    print(args.output)

if __name__ == '__main__':
    main()
