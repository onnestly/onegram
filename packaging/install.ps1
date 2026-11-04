[CmdletBinding()]
param([string]$Destination = '', [switch]$NoLaunch, [switch]$NoShortcut, [switch]$NonInteractive)
$ErrorActionPreference = 'Stop'
$oneGramTemp = $null
try {
    if (-not $Destination) { $Destination = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'Programs\OneGram' }
    $oneGramDestination = [IO.Path]::GetFullPath($Destination).TrimEnd('\')
    if ([IO.Path]::GetFileName($oneGramDestination) -ne 'OneGram') { throw 'The destination folder must be named OneGram.' }
    if ((Test-Path -LiteralPath $oneGramDestination) -and ((Get-Item -LiteralPath $oneGramDestination).Attributes -band [IO.FileAttributes]::ReparsePoint)) { throw 'The destination must not be a linked folder.' }
    $oneGramPrefix = $oneGramDestination + '\'
    foreach ($oneGramProcess in Get-Process) {
        $oneGramExe = $null
        try { $oneGramExe = $oneGramProcess.Path } catch {}
        if ($oneGramExe -and $oneGramExe.StartsWith($oneGramPrefix, [StringComparison]::OrdinalIgnoreCase)) { throw 'Exit OneGram through its tray menu before updating.' }
    }
    $oneGramPayload = Join-Path $PSScriptRoot 'payload.zip'
    $oneGramExpected = (Get-Content -LiteralPath (Join-Path $PSScriptRoot 'payload.sha256') -Raw).Trim()
    if ((Get-FileHash -LiteralPath $oneGramPayload -Algorithm SHA256).Hash -ne $oneGramExpected) { throw 'Installer payload checksum mismatch.' }
    $oneGramTemp = Join-Path ([IO.Path]::GetTempPath()) ('OneGram-install-' + [Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $oneGramTemp | Out-Null
    Expand-Archive -LiteralPath $oneGramPayload -DestinationPath $oneGramTemp
    $oneGramSource = Join-Path $oneGramTemp 'OneGram'
    if (-not (Test-Path -LiteralPath (Join-Path $oneGramSource 'OneGram.exe'))) { throw 'The installer does not contain OneGram.exe.' }
    New-Item -ItemType Directory -Path $oneGramDestination -Force | Out-Null
    foreach ($oneGramFile in Get-ChildItem -LiteralPath $oneGramSource -Recurse -File) {
        $oneGramRelative = $oneGramFile.FullName.Substring($oneGramSource.Length + 1)
        if ($oneGramRelative -eq 'data' -or $oneGramRelative.StartsWith('data\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Installer payload must not include a user profile.' }
        $oneGramTarget = Join-Path $oneGramDestination $oneGramRelative
        $oneGramParent = Split-Path -Parent $oneGramTarget
        New-Item -ItemType Directory -Path $oneGramParent -Force | Out-Null
        if ((Get-Item -LiteralPath $oneGramParent).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing to install through a linked folder.' }
        $oneGramPending = $oneGramTarget + '.install-new'
        Copy-Item -LiteralPath $oneGramFile.FullName -Destination $oneGramPending -Force
        Move-Item -LiteralPath $oneGramPending -Destination $oneGramTarget -Force
    }
    $oneGramApplication = Join-Path $oneGramDestination 'OneGram.exe'
    if (-not $NoShortcut) {
        $oneGramShell = New-Object -ComObject WScript.Shell
        foreach ($oneGramShortcutFolder in @([Environment]::GetFolderPath('DesktopDirectory'), [Environment]::GetFolderPath('Programs'))) {
            $oneGramShortcut = $oneGramShell.CreateShortcut((Join-Path $oneGramShortcutFolder 'OneGram.lnk'))
            $oneGramShortcut.TargetPath = $oneGramApplication
            $oneGramShortcut.WorkingDirectory = $oneGramDestination
            $oneGramShortcut.IconLocation = $oneGramApplication + ',0'
            $oneGramShortcut.Save()
        }
    }
    if (-not $NoLaunch) { Start-Process -FilePath $oneGramApplication -WorkingDirectory $oneGramDestination }
    Write-Output ('Installed OneGram 1.0.3 to ' + $oneGramDestination)
} catch {
    if (-not $NonInteractive) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, 'OneGram installation', 'OK', 'Error') | Out-Null
    }
    Write-Error $_
    exit 1
} finally {
    if ($oneGramTemp -and (Test-Path -LiteralPath $oneGramTemp)) {
        $oneGramResolved = [IO.Path]::GetFullPath($oneGramTemp)
        $oneGramAllowed = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\') + '\OneGram-install-'
        if ($oneGramResolved.StartsWith($oneGramAllowed, [StringComparison]::OrdinalIgnoreCase)) { Remove-Item -LiteralPath $oneGramResolved -Recurse -Force }
    }
}
