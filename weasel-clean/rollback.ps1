# Restore one exact snapshot; never merge unrelated backups.
[CmdletBinding()]
param([Parameter(Mandatory=$true)][string]$BackupDir,[switch]$DryRun,[switch]$Json)
. (Join-Path $PSScriptRoot 'common.ps1')
$operationLock=$null
$report=[ordered]@{ schema_version=1; operation='rollback'; status='failed'; exit_code=1 }
try {
    $BackupDir=Resolve-Directory $BackupDir
    $manifest=Read-Snapshot $BackupDir
    $report.user_dir=$manifest.user_dir
    $report.files=@($manifest.entries | ForEach-Object { $_.name })
    if ($DryRun) { $report.status='planned' }
    else {
        $operationLock=Enter-Operation $manifest.user_dir
        Restore-Snapshot $BackupDir
        $report.status='restored'
    }
    $report.exit_code=0
} catch { $report.error=$_.Exception.Message }
finally { if ($operationLock) { $operationLock.Dispose() } }
if ($Json) { $report | ConvertTo-Json -Depth 8 } else { $report | Format-List | Out-String | Write-Output }
exit $report.exit_code
