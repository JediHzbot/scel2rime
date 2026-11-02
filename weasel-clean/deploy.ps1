# Compile in a child process; never accept stale build artifacts as success.
[CmdletBinding()]
param(
    [string]$WeaselRoot,
    [string]$UserDir = (Join-Path $env:APPDATA 'Rime'),
    [switch]$FullCheck,
    [ValidateRange(1,3600)][int]$TimeoutSeconds = 120,
    [switch]$Json
)
. (Join-Path $PSScriptRoot 'common.ps1')
$inheritedLock = Get-Variable -Name operationLock -Scope 1 -ValueOnly -ErrorAction SilentlyContinue
$operationLock=$null; $backup=$null; $mutating=$false; $process=$null
$report=[ordered]@{ schema_version=1; operation='deploy'; status='failed'; user_dir=$UserDir; backup_dir=$null; exit_code=1 }
try {
    $UserDir=Resolve-Directory $UserDir
    $WeaselRoot=Resolve-Weasel $WeaselRoot
    $report.user_dir=$UserDir
    foreach ($name in @('scel_merged.dict.yaml','luna_pinyin_simp.custom.yaml')) {
        $path=Get-Target $UserDir $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Required source not found: $name" }
    }
    if ($inheritedLock -isnot [IO.FileStream] -or -not $inheritedLock.CanWrite -or -not $inheritedLock.Name.Equals((Join-Path $UserDir '.scel2rime.lock'),[StringComparison]::OrdinalIgnoreCase)) {
        $operationLock=Enter-Operation $UserDir
    }
    $backup=New-Snapshot $UserDir @('build','installation.yaml','user.yaml')
    $report.backup_dir=$backup
    $mutating=$true
    Remove-ManagedTarget $UserDir 'build'
    New-Item -ItemType Directory -Path (Join-Path $UserDir 'build') | Out-Null
    $worker=Join-Path $PSScriptRoot 'deploy-worker.ps1'
    $logDir=Join-Path $backup 'native-logs'
    New-Item -ItemType Directory -Path $logDir | Out-Null
    $start=New-Object Diagnostics.ProcessStartInfo
    $start.FileName=(Get-Process -Id $PID).Path
    $start.UseShellExecute=$false
    $start.CreateNoWindow=$true
    $start.RedirectStandardOutput=$true
    $start.RedirectStandardError=$true
    $start.WorkingDirectory=$UserDir
    $start.Arguments='-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' + $worker + '" -WeaselRoot "' + $WeaselRoot + '" -UserDir "' + $UserDir + '" -LogDir "' + $logDir + '"'
    $process=New-Object Diagnostics.Process
    $process.StartInfo=$start
    $null=$process.Start()
    $stdoutTask=$process.StandardOutput.ReadToEndAsync()
    $stderrTask=$process.StandardError.ReadToEndAsync()
    $finished=$process.WaitForExit($TimeoutSeconds * 1000)
    if (-not $finished) {
        $process.Kill()
        $process.WaitForExit()
    }
    Write-Utf8 (Join-Path $backup 'worker.stdout.log') $stdoutTask.GetAwaiter().GetResult()
    Write-Utf8 (Join-Path $backup 'worker.stderr.log') $stderrTask.GetAwaiter().GetResult()
    if (-not $finished) { throw "Deployment timed out after $TimeoutSeconds seconds; worker terminated" }
    if ($process.ExitCode -ne 0) { throw "Worker exited $($process.ExitCode); see logs in $backup" }
    $nativeErrors=@(Get-ChildItem -LiteralPath $logDir -File | Where-Object { $_.Name -match '\.(ERROR|FATAL)\.' -and $_.Length -gt 0 })
    if ($nativeErrors.Count) { throw "Native compiler reported errors; see $logDir" }
    $artifacts=@()
    foreach ($name in @('scel_merged.table.bin','luna_pinyin_simp.prism.bin','luna_pinyin_simp.schema.yaml')) {
        $path=Join-Path (Join-Path $UserDir 'build') $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf) -or (Get-Item -LiteralPath $path).Length -eq 0) { throw "Fresh artifact missing/empty: $name" }
        $item=Get-Item -LiteralPath $path
        $artifacts += [pscustomobject]@{ name=$name; bytes=$item.Length; sha256=(Get-FileDigest $path) }
    }
    $schema=Get-Content -LiteralPath (Join-Path $UserDir 'build\luna_pinyin_simp.schema.yaml') -Raw -Encoding UTF8
    if ($schema -notmatch '(?m)^\s+dictionary:\s*["'']?scel_merged["'']?\s*$') { throw 'Compiled schema does not reference scel_merged' }
    $report.artifacts=$artifacts
    $report.status='compiled'; $report.exit_code=0
    $report.validation='Fresh compilation artifacts checked; typing and candidate behavior require an input-method test.'
} catch {
    $report.error=$_.Exception.Message
    if ($mutating -and $backup) {
        try { Restore-Snapshot $backup; $report.status='rolled_back' }
        catch { $report.status='rollback_failed'; $report.rollback_error=$_.Exception.Message }
    }
} finally {
    if ($process) { $process.Dispose() }
    if ($operationLock) { $operationLock.Dispose() }
}
if ($Json) { $report | ConvertTo-Json -Depth 8 }
else {
    Write-Output ("Status: " + $report.status + "; target: " + $report.user_dir)
    if ($report.Contains('error')) { Write-Output $report.error }
    if ($report.Contains('validation')) { Write-Output $report.validation }
}
exit $report.exit_code
