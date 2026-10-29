# Deploy Rime by calling librime directly.
#
# Why this exists: `WeaselDeployer.exe /deploy` only posts a message to the
# WeaselServer service. On some installs that service never starts the
# deployment thread, so the command returns while nothing is compiled -- and the
# schema keeps pointing at a dictionary that was never built.
#
# This script bypasses the service and drives librime itself:
#   RimeSetup -> RimeInitialize -> RimeStartMaintenance(full) -> Finalize
#
# The traits struct mirrors `RimeTraits` from librime's rime_api.h. Getting it
# wrong is subtle: a stale or mis-sized struct makes librime ignore every path
# you set and fall back to the process working directory, which "succeeds"
# while deploying into the wrong folder.
param(
    [string]$WeaselRoot,
    [string]$UserDir = (Join-Path $env:APPDATA 'Rime'),
    [switch]$FullCheck
)

$ErrorActionPreference = 'Stop'

if (-not $WeaselRoot) {
    $candidate = Get-ChildItem 'C:\Program Files\Rime' -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like 'weasel-*' } |
        Sort-Object Name -Descending |
        Select-Object -First 1
    if (-not $candidate) { throw 'Weasel not found under C:\Program Files\Rime' }
    $WeaselRoot = $candidate.FullName
}

$dll = Join-Path $WeaselRoot 'rime.dll'
if (-not (Test-Path $dll)) { throw "rime.dll not found in $WeaselRoot" }
if (-not (Test-Path (Join-Path $WeaselRoot 'data'))) { throw "shared data directory missing in $WeaselRoot" }

$env:PATH = "$WeaselRoot;" + $env:PATH

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class RimeNative
{
    // Field order and data_size follow librime/src/rime_api.h:
    //   int data_size;
    //   const char* shared_data_dir; const char* user_data_dir;
    //   const char* distribution_name; const char* distribution_code_name;
    //   const char* distribution_version; const char* app_name;
    //   const char** modules; int min_log_level; const char* log_dir;
    //   const char* prebuilt_data_dir; const char* staging_dir;
    [StructLayout(LayoutKind.Sequential)]
    public struct Traits
    {
        public int data_size;
        public IntPtr shared_data_dir;
        public IntPtr user_data_dir;
        public IntPtr distribution_name;
        public IntPtr distribution_code_name;
        public IntPtr distribution_version;
        public IntPtr app_name;
        public IntPtr modules;
        public int min_log_level;
        public IntPtr log_dir;
        public IntPtr prebuilt_data_dir;
        public IntPtr staging_dir;
    }

    [DllImport("rime.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern void RimeSetup(IntPtr traits);

    [DllImport("rime.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern void RimeInitialize(IntPtr traits);

    [DllImport("rime.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern int RimeStartMaintenance(int fullCheck);

    [DllImport("rime.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern void RimeJoinMaintenanceThread();

    [DllImport("rime.dll", CallingConvention = CallingConvention.Cdecl)]
    public static extern void RimeFinalize();

    // librime expects UTF-8. The ANSI marshaller would mangle Chinese paths.
    public static IntPtr Utf8(string value)
    {
        if (value == null) return IntPtr.Zero;
        byte[] bytes = Encoding.UTF8.GetBytes(value + "\0");
        IntPtr pointer = Marshal.AllocHGlobal(bytes.Length);
        Marshal.Copy(bytes, 0, pointer, bytes.Length);
        return pointer;
    }
}
'@

$traits = New-Object RimeNative+Traits
$size = [Runtime.InteropServices.Marshal]::SizeOf([type][RimeNative+Traits])
# RIME_STRUCT_INIT: data_size = sizeof(Traits) - sizeof(data_size)
$traits.data_size              = $size - 4
$traits.shared_data_dir        = [RimeNative]::Utf8((Join-Path $WeaselRoot 'data'))
$traits.user_data_dir          = [RimeNative]::Utf8($UserDir)
$traits.distribution_name      = [RimeNative]::Utf8('Weasel')
$traits.distribution_code_name = [RimeNative]::Utf8('weasel')
$version = (Split-Path $WeaselRoot -Leaf) -replace '^weasel-', ''
$traits.distribution_version   = [RimeNative]::Utf8($version)
$traits.app_name               = [RimeNative]::Utf8('rime.weasel')
$traits.modules                = [IntPtr]::Zero
$traits.min_log_level          = 0

$pinned = [Runtime.InteropServices.Marshal]::AllocHGlobal($size)
[Runtime.InteropServices.Marshal]::StructureToPtr($traits, $pinned, $false)

try {
    [RimeNative]::RimeSetup($pinned)
    [RimeNative]::RimeInitialize($pinned)
    $full = if ($FullCheck) { 1 } else { 0 }
    $started = [RimeNative]::RimeStartMaintenance($full)
    if ($started -ne 0) { [RimeNative]::RimeJoinMaintenanceThread() }
    [RimeNative]::RimeFinalize()
}
finally {
    [Runtime.InteropServices.Marshal]::FreeHGlobal($pinned)
}

Write-Host "deployed: $UserDir"
