<#
.SYNOPSIS
Installs or removes the per-user Logifetch background agent.

.DESCRIPTION
Copies the agent, its configuration, and its checked-in Logitech protocol
helpers to %LOCALAPPDATA%\Logifetch. It then registers the agent in the
current user's Windows Run key, so it starts at logon. Administrator rights are
not needed.
#>

[CmdletBinding()]
param(
    [switch]$Remove,
    [string]$InstallPath = (Join-Path $env:LOCALAPPDATA 'Logifetch'),
    [string]$PythonPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$runKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$runValue = 'Logifetch'

if ($Remove) {
    Remove-ItemProperty -LiteralPath $runKey -Name $runValue -ErrorAction SilentlyContinue
    try {
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
            Where-Object { $_.CommandLine -like "*$InstallPath*logifetch_agent.py*" } |
            ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate | Out-Null }
    } catch {
        Write-Warning 'Could not stop a running Logifetch process automatically; sign out or end it manually before removal.'
    }
    Remove-Item -LiteralPath $InstallPath -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host 'Removed the Logifetch background agent and its current-user Run entry.'
    exit 0
}

$sourceRoot = $PSScriptRoot
if (-not $PythonPath) {
    $python = Get-Command python.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $python) {
        throw 'Python 3 is required. Install Python, or rerun with -PythonPath C:\Path\to\python.exe.'
    }
    $PythonPath = $python.Source
}
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python executable was not found: $PythonPath"
}

New-Item -ItemType Directory -Path $InstallPath -Force | Out-Null
foreach ($folder in 'src', 'reverse') {
    $destination = Join-Path $InstallPath $folder
    Remove-Item -LiteralPath $destination -Recurse -Force -ErrorAction SilentlyContinue
    Copy-Item -LiteralPath (Join-Path $sourceRoot $folder) -Destination $destination -Recurse -Force
}
$installedConfig = Join-Path $InstallPath 'config.json'
if (-not (Test-Path -LiteralPath $installedConfig)) {
    Copy-Item -LiteralPath (Join-Path $sourceRoot 'config.json') -Destination $installedConfig
}

$agentPath = Join-Path $InstallPath 'src\logifetch_agent.py'
& $PythonPath $agentPath --config $installedConfig --check-config
if ($LASTEXITCODE -ne 0) {
    throw 'The copied Logifetch configuration did not validate.'
}

$backgroundPython = Join-Path (Split-Path -Parent $PythonPath) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $backgroundPython -PathType Leaf)) {
    $backgroundPython = $PythonPath
}
$arguments = '"{0}" --config "{1}"' -f $agentPath, $installedConfig
$runCommand = '"{0}" {1}' -f $backgroundPython, $arguments
New-ItemProperty -LiteralPath $runKey -Name $runValue -Value $runCommand -PropertyType String -Force -ErrorAction Stop | Out-Null
Start-Process -FilePath $backgroundPython -ArgumentList $arguments -WindowStyle Hidden -ErrorAction Stop
Write-Host "Installed Logifetch for the current user. It will start at logon from the Windows Run key. Edit $installedConfig, then rerun this script to update the agent files."
