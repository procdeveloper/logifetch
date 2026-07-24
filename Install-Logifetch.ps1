<#
.SYNOPSIS
Installs or removes the per-user Logifetch background agent.

.DESCRIPTION
Copies the agent, its configuration, and its checked-in Logitech protocol
helpers to %LOCALAPPDATA%\Logifetch. It then registers an interactive
Scheduled Task for the current user, so it starts reliably at logon and is
restarted after a crash. Administrator rights are not needed.
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
$taskName = 'Logifetch'

function Stop-LogifetchAgent {
    param([string]$Path)

    try {
        Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
            Where-Object { $_.CommandLine -like "*$Path*logifetch_agent.py*" } |
            ForEach-Object { Invoke-CimMethod -InputObject $_ -MethodName Terminate | Out-Null }
    } catch {
        Write-Warning 'Could not stop a running Logifetch process automatically; it will be replaced at the next logon.'
    }
}

if ($Remove) {
    Remove-ItemProperty -LiteralPath $runKey -Name $runValue -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
    Stop-LogifetchAgent -Path $InstallPath
    Remove-Item -LiteralPath $InstallPath -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host 'Removed the Logifetch background agent and its current-user Scheduled Task.'
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
$taskAction = New-ScheduledTaskAction -Execute $backgroundPython -Argument $arguments
$taskTrigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$taskSettings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit ([TimeSpan]::Zero) `
    -MultipleInstances IgnoreNew `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask `
    -TaskName $taskName `
    -Action $taskAction `
    -Trigger $taskTrigger `
    -Settings $taskSettings `
    -Description 'Runs the interactive Logifetch mouse agent at logon and restarts it after a crash.' `
    -Force | Out-Null

# Remove the legacy Run-key entry only after the task is safely registered.
Remove-ItemProperty -LiteralPath $runKey -Name $runValue -ErrorAction SilentlyContinue
Stop-LogifetchAgent -Path $InstallPath
Start-Process -FilePath $backgroundPython -ArgumentList $arguments -WindowStyle Hidden -ErrorAction Stop
Write-Host "Installed Logifetch for the current user. It will start at logon from Scheduled Tasks and restart after a crash. Edit $installedConfig, then rerun this script to update the agent files."
