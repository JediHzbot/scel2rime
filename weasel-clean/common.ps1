# Shared filesystem helpers. No network access or input-method registration.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object Text.UTF8Encoding($false)

function Assert-PlainPath([string]$Path) {
    $cursor = [IO.Path]::GetFullPath($Path)
    while ($cursor) {
        if (Test-Path -LiteralPath $cursor) {
            $item = Get-Item -LiteralPath $cursor -Force
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse points are not supported: $cursor" }
        }
        $parent = Split-Path -Parent $cursor
        if ($parent -eq $cursor) { break }
        $cursor = $parent
    }
}
function Resolve-Directory([string]$Path) {
    Assert-PlainPath $Path
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { throw "Directory not found: $Path" }
    $full = (Get-Item -LiteralPath $Path -Force).FullName
    if ($full.TrimEnd('\', '/') -eq [IO.Path]::GetPathRoot($full).TrimEnd('\', '/')) { throw 'A volume root cannot be used as a managed directory' }
    return $full.TrimEnd('\', '/')
}
function Get-Target([string]$Root, [string]$Name) {
    if ($Name -notin @('build','installation.yaml','user.yaml') -and $Name -notmatch '^[^\\/:*?"<>|\x00-\x1f]+\.(dict|custom)\.yaml$') {
        throw "Unsafe managed filename: $Name"
    }
    $target = [IO.Path]::GetFullPath((Join-Path $Root $Name))
    $parent = [IO.Path]::GetFullPath((Split-Path -Parent $target)).TrimEnd('\', '/')
    if (-not $parent.Equals($Root.TrimEnd('\', '/'), [StringComparison]::OrdinalIgnoreCase)) { throw "Target escapes directory: $target" }
    Assert-PlainPath $target
    return $target
}
function Assert-PlainTree([string]$Path) {
    Assert-PlainPath $Path
    if (Test-Path -LiteralPath $Path -PathType Container) {
        foreach ($item in Get-ChildItem -LiteralPath $Path -Force -Recurse) {
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Reparse point in managed directory: $($item.FullName)" }
        }
    }
}
function Get-FileDigest([string]$Path) {
    $sha=[Security.Cryptography.SHA256]::Create()
    $stream=[IO.File]::OpenRead($Path)
    try { return [BitConverter]::ToString($sha.ComputeHash($stream)).Replace('-', '') }
    finally { $stream.Dispose(); $sha.Dispose() }
}
function Get-Digest([string]$Path) {
    Assert-PlainTree $Path
    if (Test-Path -LiteralPath $Path -PathType Leaf) { return (Get-FileDigest $Path) }
    $root = (Get-Item -LiteralPath $Path).FullName
    $lines = foreach ($item in Get-ChildItem -LiteralPath $root -Recurse -Force | Sort-Object FullName) {
        $relative = $item.FullName.Substring($root.Length)
        if ($item.PSIsContainer) { "D:$relative" } else { "F:${relative}:$((Get-FileDigest $item.FullName))" }
    }
    $sha = [Security.Cryptography.SHA256]::Create()
    try { return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($lines -join "`n")))).Replace('-', '') }
    finally { $sha.Dispose() }
}
function Write-Utf8([string]$Path, [string]$Text) {
    [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding($false)))
}
function Enter-Operation([string]$Root) {
    $path = Join-Path $Root '.scel2rime.lock'
    Assert-PlainPath $path
    return [IO.File]::Open($path, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::None)
}
function New-Snapshot([string]$Root, [string[]]$Names) {
    $backup = Join-Path $Root ('backup-scel2rime-' + (Get-Date -Format 'yyyyMMdd-HHmmss') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8))
    New-Item -ItemType Directory -Path $backup | Out-Null
    $entries = foreach ($name in $Names) {
        $target = Get-Target $Root $name
        $exists = Test-Path -LiteralPath $target
        $kind = if ($name -eq 'build') { 'directory' } else { 'file' }
        $hash = $null
        if ($exists) {
            $item = Get-Item -LiteralPath $target
            if (($kind -eq 'directory') -ne $item.PSIsContainer) { throw "Unexpected target type: $target" }
            $hash = Get-Digest $target
            Copy-Item -LiteralPath $target -Destination (Join-Path $backup $name) -Recurse -Force
            if ((Get-Digest (Join-Path $backup $name)) -ne $hash) { throw "Backup verification failed: $name" }
        }
        [pscustomobject]@{ name=$name; existed=[bool]$exists; kind=$kind; sha256=$hash }
    }
    $manifest = [pscustomobject]@{ version=1; user_dir=$Root; created_utc=[DateTime]::UtcNow.ToString('o'); entries=@($entries) }
    Write-Utf8 (Join-Path $backup 'manifest.json') ($manifest | ConvertTo-Json -Depth 8)
    return $backup
}
function Read-Snapshot([string]$BackupDir) {
    $backup = Resolve-Directory $BackupDir
    $root = Resolve-Directory (Split-Path -Parent $backup)
    Assert-PlainTree $backup
    $manifest = Get-Content -LiteralPath (Join-Path $backup 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($manifest.version -ne 1 -or -not $root.Equals($manifest.user_dir, [StringComparison]::OrdinalIgnoreCase)) { throw 'Backup directory/manifest mismatch' }
    $seen = @{}
    foreach ($entry in $manifest.entries) {
        $null = Get-Target $root $entry.name
        if ($seen.ContainsKey($entry.name)) { throw 'Duplicate manifest target' }
        $seen[$entry.name] = $true
        if ($entry.existed) {
            $source = Get-Target $backup $entry.name
            if (-not (Test-Path -LiteralPath $source) -or (Get-Digest $source) -ne $entry.sha256) { throw "Backup missing or changed: $($entry.name)" }
        }
    }
    return $manifest
}
function Remove-ManagedTarget([string]$Root, [string]$Name) {
    $target = Get-Target $Root $Name
    Assert-PlainTree $target
    if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Recurse -Force }
}
function Restore-Snapshot([string]$BackupDir) {
    # Validate the entire snapshot before restoring any destination.
    $manifest = Read-Snapshot $BackupDir
    foreach ($entry in $manifest.entries) {
        $target = Get-Target $manifest.user_dir $entry.name
        Remove-ManagedTarget $manifest.user_dir $entry.name
        if ($entry.existed) { Copy-Item -LiteralPath (Join-Path $BackupDir $entry.name) -Destination $target -Recurse -Force }
    }
    foreach ($entry in $manifest.entries) {
        $target = Get-Target $manifest.user_dir $entry.name
        if ($entry.existed) {
            if ((Get-Digest $target) -ne $entry.sha256) { throw "Restore verification failed: $($entry.name)" }
        } elseif (Test-Path -LiteralPath $target) { throw "New file was not removed: $($entry.name)" }
    }
}
function Resolve-Weasel([string]$WeaselRoot) {
    if (-not $WeaselRoot) {
        $candidates = foreach ($programRoot in @($env:ProgramFiles, ${env:ProgramFiles(x86)}) | Select-Object -Unique) {
            if ($programRoot) {
                Get-ChildItem -LiteralPath (Join-Path $programRoot 'Rime') -Directory -ErrorAction SilentlyContinue |
                    Where-Object { $_.Name -match '^weasel-\d+\.\d+' }
            }
        }
        $candidate = $candidates | Sort-Object @{ Expression={ [version](($_.Name -replace '^weasel-','') -replace '[^\d.].*$','') }; Descending=$true } | Select-Object -First 1
        if (-not $candidate) { throw 'Weasel not found. Specify -WeaselRoot explicitly.' }
        $WeaselRoot = $candidate.FullName
    }
    $WeaselRoot = Resolve-Directory $WeaselRoot
    if (-not (Test-Path -LiteralPath (Join-Path $WeaselRoot 'rime.dll') -PathType Leaf)) { throw 'rime.dll not found' }
    if (-not (Test-Path -LiteralPath (Join-Path $WeaselRoot 'data') -PathType Container)) { throw 'Weasel shared data not found' }
    return $WeaselRoot
}
