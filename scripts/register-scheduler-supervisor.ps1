[CmdletBinding(SupportsShouldProcess = $true, ConfirmImpact = "Medium")]
param(
    [string]$PythonPath,
    [string]$OutputDirectory = "scheduled_posts",
    [string]$DatabasePath,
    [string]$TaskName = "Social Media Agent Scheduler Supervisor",
    [ValidateRange(1, 3600)]
    [int]$PollSeconds = 5,
    [ValidateRange(1, 64)]
    [int]$MaxWorkers = 4,
    [switch]$StartNow,
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if ($Unregister) {
    $existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($null -eq $existingTask) {
        Write-Warning "Scheduled task '$TaskName' was not found."
        return
    }

    if ($PSCmdlet.ShouldProcess("Scheduled task '$TaskName'", "Unregister")) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "Unregistered scheduled task '$TaskName'."
    }
    return
}

$appPath = Join-Path $projectRoot "app.py"
if (-not (Test-Path -LiteralPath $appPath -PathType Leaf)) {
    throw "Application entry point was not found: $appPath"
}

if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
    if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
        $PythonPath = $venvPython
    }
    else {
        $pythonCommand = Get-Command python -ErrorAction Stop
        $PythonPath = $pythonCommand.Source
    }
}
elseif (-not [IO.Path]::IsPathRooted($PythonPath)) {
    $PythonPath = Join-Path $projectRoot $PythonPath
}

if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw "Python executable was not found: $PythonPath"
}
$PythonPath = (Resolve-Path -LiteralPath $PythonPath).Path

if (-not [IO.Path]::IsPathRooted($OutputDirectory)) {
    $OutputDirectory = Join-Path $projectRoot $OutputDirectory
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)

if (-not [string]::IsNullOrWhiteSpace($DatabasePath)) {
    if (-not [IO.Path]::IsPathRooted($DatabasePath)) {
        $DatabasePath = Join-Path $projectRoot $DatabasePath
    }
    $DatabasePath = [IO.Path]::GetFullPath($DatabasePath)
}

function Quote-CommandArgument {
    param([string]$Value)

    if ($Value.Contains('"')) {
        throw "Paths containing a double quote cannot be used in a scheduled task argument."
    }
    return '"' + $Value + '"'
}

$arguments = @(
    (Quote-CommandArgument $appPath),
    "--supervise-scheduled",
    "--scheduled-output",
    (Quote-CommandArgument $OutputDirectory),
    "--scheduler-poll-seconds",
    "$PollSeconds",
    "--max-scheduled-workers",
    "$MaxWorkers"
)
if (-not [string]::IsNullOrWhiteSpace($DatabasePath)) {
    $arguments += @("--scheduler-db", (Quote-CommandArgument $DatabasePath))
}

$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$action = New-ScheduledTaskAction `
    -Execute $PythonPath `
    -Argument ($arguments -join " ") `
    -WorkingDirectory $projectRoot
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal `
    -UserId $userId `
    -LogonType Interactive `
    -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

if ($PSCmdlet.ShouldProcess("Scheduled task '$TaskName' for '$userId'", "Register")) {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Principal $principal `
        -Settings $settings `
        -Description "Runs the local social media agent persisted-job supervisor at user logon." `
        -Force | Out-Null

    if ($StartNow) {
        Start-ScheduledTask -TaskName $TaskName
    }
    Write-Output "Registered '$TaskName' to run at logon for '$userId'."
}
