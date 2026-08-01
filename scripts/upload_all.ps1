# -*- coding: utf-8 -*-
# 读取 Windows 凭据管理器里的 cnb-release:rw，设好 CNB_TOKEN，然后跑上传。
# 令牌全程留在本机，不会出现在任何输出里。
$ErrorActionPreference = "Stop"

Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class WinCred {
    [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern bool CredRead(string target, int type, int reservedFlag, out IntPtr credentialPtr);
    [DllImport("advapi32.dll", SetLastError = true)]
    public static extern void CredFree(IntPtr buffer);
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct CREDENTIAL {
        public int Flags;
        public int Type;
        public IntPtr TargetName;
        public IntPtr Comment;
        public long LastWritten;
        public int CredentialBlobSize;
        public IntPtr CredentialBlob;
        public int Persist;
        public int AttributeCount;
        public IntPtr Attributes;
        public IntPtr TargetAlias;
        public IntPtr UserName;
    }
    public static string ReadPassword(string target) {
        IntPtr ptr = IntPtr.Zero;
        if (!CredRead(target, 1, 0, out ptr)) return null;
        try {
            CREDENTIAL c = (CREDENTIAL)Marshal.PtrToStructure(ptr, typeof(CREDENTIAL));
            if (c.CredentialBlob == IntPtr.Zero) return null;
            byte[] bytes = new byte[c.CredentialBlobSize];
            Marshal.Copy(c.CredentialBlob, bytes, 0, c.CredentialBlobSize);
            return Encoding.Unicode.GetString(bytes);
        } finally { CredFree(ptr); }
    }
}
'@

if (-not $env:CNB_TOKEN) {
    $pw = [WinCred]::ReadPassword('cnb-release:rw')
    if (-not $pw) {
        Write-Error "Cannot read cnb-release:rw credential and CNB_TOKEN is not set"
        exit 1
    }
    [Environment]::SetEnvironmentVariable('CNB_TOKEN', $pw, 'Process')
    Write-Output "CNB_TOKEN set from credential manager ($($pw.Length) chars)"
} else {
    Write-Output "CNB_TOKEN environment variable already set"
}

Set-Location $PSScriptRoot\..

# Assets to upload: tag, file path, corresponding yaml (optional)
$assets = @(
    # amd runtime (nvidia/nvidia50 already on Release, skip)
    @("RVC-runtime", "CNB-GIT-RELEASE\runtime\amd\runtime-amd-2026.07.21.tar", "CNB-GIT-RELEASE\catalog-src\runtimes\amd.yaml"),
    # engine-core
    @("engine-core", "CNB-GIT-RELEASE\assets\core\engine-core-260722.zip", "CNB-GIT-RELEASE\catalog-src\engine-core.yaml"),
    # setup
    @("setup", "CNB-GIT-RELEASE\setup\RVC_Fabric_Setup.exe", "CNB-GIT-RELEASE\catalog-src\setup.yaml"),
    # vbcable
    @("vbcable", "CNB-GIT-RELEASE\vbcable\vbcable-setup.zip", "CNB-GIT-RELEASE\catalog-src\vbcable.yaml")
)

foreach ($a in $assets) {
    $tag, $file, $yaml = $a
    if (-not (Test-Path $file)) { Write-Warning "Skipping $file (not found)"; continue }
    $cmd = "python scripts\publish_asset.py --tag $tag --file `"$file`""
    if ($yaml -and (Test-Path $yaml)) { $cmd += " --write-yaml `"$yaml`"" }
    Write-Output ""
    Write-Output "=== $tag : $(Split-Path $file -Leaf) ==="
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) { Write-Error "$tag upload failed"; exit $LASTEXITCODE }
}

# Voice packs (each has its own yaml)
$voices = @(
    @("voices", "CNB-GIT-RELEASE\voices\Anon\Anon-v1.zip", "CNB-GIT-RELEASE\catalog-src\voices\Anon.yaml"),
    @("voices", "CNB-GIT-RELEASE\voices\Rana\Rana-v1.zip", "CNB-GIT-RELEASE\catalog-src\voices\Rana.yaml"),
    @("voices", "CNB-GIT-RELEASE\voices\Soyo\Soyo-v1.zip", "CNB-GIT-RELEASE\catalog-src\voices\Soyo.yaml"),
    @("voices", "CNB-GIT-RELEASE\voices\Taki\Taki-v1.zip", "CNB-GIT-RELEASE\catalog-src\voices\Taki.yaml"),
    @("voices", "CNB-GIT-RELEASE\voices\Tomori\Tomori-v1.zip", "CNB-GIT-RELEASE\catalog-src\voices\Tomori.yaml"),
    @("voices", "CNB-GIT-RELEASE\voices\guanguan\guanguan-v2.zip", "CNB-GIT-RELEASE\catalog-src\voices\guanguan.yaml"),
    @("voices", "CNB-GIT-RELEASE\voices\keruan\keruan-v2.zip", "CNB-GIT-RELEASE\catalog-src\voices\keruan.yaml"),
    @("voices", "CNB-GIT-RELEASE\voices\kiki\kiki-v2.zip", "CNB-GIT-RELEASE\catalog-src\voices\kiki.yaml"),
    @("voices", "CNB-GIT-RELEASE\voices\youzhanv2-xi\youzhanv2-xi-v2.zip", "CNB-GIT-RELEASE\catalog-src\voices\youzhanv2-xi.yaml")
)

foreach ($v in $voices) {
    $tag, $file, $yaml = $v
    $cmd = "python scripts\publish_asset.py --tag $tag --file `"$file`""
    if ($yaml -and (Test-Path $yaml)) { $cmd += " --write-yaml `"$yaml`"" }
    Write-Output ""
    Write-Output "=== $tag : $(Split-Path $file -Leaf) ==="
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) { Write-Error "$(Split-Path $file -Leaf) upload failed"; exit $LASTEXITCODE }
}

# shell-patches (batch upload, no yaml)
$patches = Get-ChildItem "CNB-GIT-RELEASE\shell-patches\*.zip"
if ($patches) {
    $cmd = "python scripts\publish_asset.py --tag shell-patches"
    foreach ($p in $patches) { $cmd += " --file `"$p`"" }
    Write-Output ""
    Write-Output "=== shell-patches : $($patches.Count) files ==="
    Invoke-Expression $cmd
    if ($LASTEXITCODE -ne 0) { Write-Error "shell-patches upload failed"; exit $LASTEXITCODE }
}

Write-Output ""
Write-Output "=== All uploads complete ==="
Write-Output "Next steps:"
Write-Output "  python scripts\build_catalog.py check --strict"
Write-Output "  python scripts\build_catalog.py build --diff"
