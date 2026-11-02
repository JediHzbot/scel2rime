# Internal worker: run only in a child PowerShell process.
param([Parameter(Mandatory=$true)][string]$WeaselRoot,[Parameter(Mandatory=$true)][string]$UserDir,[Parameter(Mandatory=$true)][string]$LogDir)
$ErrorActionPreference='Stop'
$dll=Join-Path $WeaselRoot 'rime.dll'
$env:PATH="$WeaselRoot;" + $env:PATH
$nativeCode = @'
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
$dllLiteral = '"' + $dll.Replace('\','\\').Replace('"','\"') + '"'
$nativeCode = $nativeCode.Replace('"rime.dll"', $dllLiteral)
Add-Type -TypeDefinition $nativeCode
$traits=New-Object RimeNative+Traits
$size=[Runtime.InteropServices.Marshal]::SizeOf([type][RimeNative+Traits])
$traits.data_size=$size - 4
$traits.shared_data_dir=[RimeNative]::Utf8((Join-Path $WeaselRoot 'data'))
$traits.user_data_dir=[RimeNative]::Utf8($UserDir)
$traits.distribution_name=[RimeNative]::Utf8('Weasel')
$traits.distribution_code_name=[RimeNative]::Utf8('weasel')
$traits.distribution_version=[RimeNative]::Utf8((Split-Path $WeaselRoot -Leaf))
$traits.app_name=[RimeNative]::Utf8('rime.scel2rime')
$traits.log_dir=[RimeNative]::Utf8($LogDir)
$pinned=[Runtime.InteropServices.Marshal]::AllocHGlobal($size)
[Runtime.InteropServices.Marshal]::StructureToPtr($traits,$pinned,$false)
$initialized=$false
try {
    [RimeNative]::RimeSetup($pinned)
    [RimeNative]::RimeInitialize($pinned)
    $initialized=$true
    if ([RimeNative]::RimeStartMaintenance(1) -eq 0) { throw 'Full maintenance did not start' }
    [RimeNative]::RimeJoinMaintenanceThread()
} finally {
    if ($initialized) { [RimeNative]::RimeFinalize() }
    [Runtime.InteropServices.Marshal]::FreeHGlobal($pinned)
    foreach ($field in @('shared_data_dir','user_data_dir','distribution_name','distribution_code_name','distribution_version','app_name','log_dir')) {
        if ($traits.$field -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::FreeHGlobal($traits.$field) }
    }
}
