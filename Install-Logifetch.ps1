<#
.SYNOPSIS
Installs or removes the per-user Logifetch background agent.

.DESCRIPTION
Copies the agent, its configuration, and its checked-in Logitech protocol
helpers to %LOCALAPPDATA%\Logifetch. It then creates one Task Scheduler task
for the current user, triggered at logon. Administrator rights are not needed.
#>

[CmdletBinding()]
param(
    [switch]$Remove,
    [string]$InstallPath = (Join-Path $env:LOCALAPPDATA 'Logifetch'),
    [string]$PythonPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$taskName = 'Logifetch'

if ($Remove) {
    & schtasks.exe /Delete /TN $taskName /F 2>$null | Out-Null
    Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
        Where-Object { $_.CommandLine -like "*$InstallPath*logifetch_agent.py*" } |
        ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate | Out-Null }
    Remove-Item -LiteralPath $InstallPath -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host 'Removed the Logifetch background agent and its current-user startup task.'
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

$taskCommand = '"{0}" "{1}" --config "{2}"' -f $PythonPath, $agentPath, $installedConfig
& schtasks.exe /Create /TN $taskName /SC ONLOGON /TR $taskCommand /F | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Could not create the Logifetch startup task.'
}
& schtasks.exe /Run /TN $taskName | Out-Null
Write-Host "Installed Logifetch for the current user. Edit $installedConfig, then rerun this script to update the agent files."
