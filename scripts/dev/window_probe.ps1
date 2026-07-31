#Requires -Version 5.1
# 「进程在跑但看不见窗口」的取证。列出 rvc-fabric.exe 的每一个顶层窗口，
# 包括隐藏的和跑到屏幕外的——Get-Process 的 MainWindowHandle 只认可见窗口，
# 隐藏窗口和「查得太早被缓存住的 0」它分不出来，所以别拿它下结论。
#
# 用法：powershell -ExecutionPolicy Bypass -File scripts\dev\window_probe.ps1
$ErrorActionPreference = "Continue"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$sig = @'
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public class WinProbe {
    [DllImport("user32.dll")] static extern bool EnumWindows(EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll")] static extern bool IsIconic(IntPtr h);
    [DllImport("user32.dll")] static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);

    delegate bool EnumProc(IntPtr h, IntPtr p);
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }

    public static List<string> ForPid(uint want) {
        var found = new List<string>();
        EnumWindows(delegate (IntPtr h, IntPtr p) {
            uint pid; GetWindowThreadProcessId(h, out pid);
            if (pid != want) return true;
            var title = new StringBuilder(512); GetWindowTextW(h, title, 512);
            var cls = new StringBuilder(256); GetClassNameW(h, cls, 256);
            RECT r; GetWindowRect(h, out r);
            found.Add(string.Format(
                "hwnd=0x{0:X}  可见={1,-5} 最小化={2,-5} 矩形=({3},{4})-({5},{6}) {7}x{8}  类={9}  标题=\"{10}\"",
                h.ToInt64(), IsWindowVisible(h), IsIconic(h),
                r.Left, r.Top, r.Right, r.Bottom, r.Right - r.Left, r.Bottom - r.Top,
                cls, title));
            return true;
        }, IntPtr.Zero);
        return found;
    }
}
'@
Add-Type -TypeDefinition $sig -Language CSharp

Write-Host "== 显示器 =="
Add-Type -AssemblyName System.Windows.Forms
foreach ($s in [System.Windows.Forms.Screen]::AllScreens) {
    Write-Host ("  {0}{1}  边界 {2}  工作区 {3}" -f $s.DeviceName,
        $(if ($s.Primary) { " (主)" } else { "" }), $s.Bounds, $s.WorkingArea)
}
Write-Host ""

$procs = @(Get-Process -Name "rvc-fabric" -ErrorAction SilentlyContinue)
if ($procs.Count -eq 0) {
    Write-Host "没找到 rvc-fabric.exe —— 进程根本没起来，问题不在窗口上。"
    exit 1
}
# 多个进程本身就是线索：上一次 tauri dev 没退干净，新的那个可能压根没建窗口。
if ($procs.Count -gt 1) {
    Write-Host ("注意：有 {0} 个 rvc-fabric.exe 在跑，上一次运行大概没退干净。" -f $procs.Count)
    Write-Host ""
}

foreach ($p in $procs) {
    Write-Host ("== pid {0}  启动于 {1} ==" -f $p.Id, $p.StartTime)
    $wins = [WinProbe]::ForPid([uint32]$p.Id)
    if ($wins.Count -eq 0) {
        Write-Host "  这个进程一个顶层窗口都没有 —— 窗口没建起来。"
    } else {
        foreach ($w in $wins) { Write-Host ("  " + $w) }
    }
    Write-Host ""
}

$log = Join-Path (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) "User_Data\logs\shell.log"
if (Test-Path $log) {
    Write-Host "== shell.log 最后一次启动 =="
    # 日志是跨启动追加的，只截最后一个 === 启动 === 之后的部分，
    # 否则很容易把上一次成功启动的 "界面已挂载" 当成本次的。
    $lines = Get-Content -LiteralPath $log -Encoding UTF8
    $i = ($lines | Select-String -SimpleMatch "启动（pid" | Select-Object -Last 1).LineNumber
    if (-not $i) { $i = ($lines | Select-String -SimpleMatch "=== RVC Fabric" | Select-Object -Last 1).LineNumber }
    if ($i) { $lines[($i - 1)..($lines.Count - 1)] | ForEach-Object { Write-Host ("  " + $_) } }
} else {
    Write-Host ("没有 {0}" -f $log)
}
