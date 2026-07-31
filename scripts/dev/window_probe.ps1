#Requires -Version 5.1
# 「进程在跑但看不见窗口」的取证。列出 rvc-fabric.exe 的每一个顶层窗口，
# 包括隐藏的、被 DWM 遮蔽的、以及跑到屏幕外的。
#
# 别拿 Get-Process 的 MainWindowHandle 下结论：它只认可见窗口，而且首次读取
# 之后会被缓存，查得早了永远是 0，分不出「没有窗口」和「窗口还没建好」。
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
    [DllImport("user32.dll")] static extern IntPtr GetWindow(IntPtr h, uint cmd);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll", EntryPoint = "GetWindowLongPtrW")]
    static extern IntPtr GetWindowLongPtr(IntPtr h, int i);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern int GetWindowTextW(IntPtr h, StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    static extern int GetClassNameW(IntPtr h, StringBuilder s, int n);
    [DllImport("dwmapi.dll")]
    static extern int DwmGetWindowAttribute(IntPtr h, int attr, out int val, int size);

    delegate bool EnumProc(IntPtr h, IntPtr p);
    [StructLayout(LayoutKind.Sequential)]
    public struct RECT { public int Left, Top, Right, Bottom; }

    const int GWL_STYLE = -16, GWL_EXSTYLE = -20;
    const uint GW_OWNER = 4;
    const int DWMWA_CLOAKED = 14;

    static string Flags(long style, long ex) {
        var f = new List<string>();
        if ((style & 0x10000000L) != 0) f.Add("WS_VISIBLE");
        if ((style & 0x20000000L) != 0) f.Add("WS_MINIMIZE");
        if ((style & 0x80000000L) != 0) f.Add("WS_POPUP");
        if ((style & 0x40000000L) != 0) f.Add("WS_CHILD");
        if ((ex & 0x00040000L) != 0) f.Add("WS_EX_APPWINDOW");   // 上任务栏
        if ((ex & 0x00000080L) != 0) f.Add("WS_EX_TOOLWINDOW");  // 不上任务栏
        if ((ex & 0x00080000L) != 0) f.Add("WS_EX_LAYERED");     // 可能整块透明
        if ((ex & 0x00000020L) != 0) f.Add("WS_EX_TRANSPARENT");
        if ((ex & 0x08000000L) != 0) f.Add("WS_EX_NOACTIVATE");
        return string.Join(" ", f.ToArray());
    }

    static string Cloak(IntPtr h) {
        int v;
        if (DwmGetWindowAttribute(h, DWMWA_CLOAKED, out v, sizeof(int)) != 0) return "?";
        // 被 DWM 遮蔽的窗口 IsWindowVisible 仍然是 true，但既不上屏也不上任务栏。
        // 2 = 外壳遮蔽，最常见的原因是窗口在另一个虚拟桌面上。
        switch (v) {
            case 0: return "否";
            case 1: return "是(应用自己)";
            case 2: return "是(外壳/在别的虚拟桌面)";
            case 4: return "是(继承自属主)";
            default: return "是(" + v + ")";
        }
    }

    public static List<string> ForPid(uint want) {
        var found = new List<string>();
        EnumWindows(delegate (IntPtr h, IntPtr p) {
            uint pid; GetWindowThreadProcessId(h, out pid);
            if (pid != want) return true;
            var title = new StringBuilder(512); GetWindowTextW(h, title, 512);
            var cls = new StringBuilder(256); GetClassNameW(h, cls, 256);
            RECT r; GetWindowRect(h, out r);
            long style = GetWindowLongPtr(h, GWL_STYLE).ToInt64();
            long ex = GetWindowLongPtr(h, GWL_EXSTYLE).ToInt64();
            IntPtr owner = GetWindow(h, GW_OWNER);
            found.Add(string.Format(
                "hwnd=0x{0:X}  类={1}  标题=\"{2}\"\n" +
                "      可见={3}  最小化={4}  DWM遮蔽={5}  属主={6}\n" +
                "      矩形=({7},{8})-({9},{10})  {11}x{12}\n" +
                "      样式={13}",
                h.ToInt64(), cls, title,
                IsWindowVisible(h), IsIconic(h), Cloak(h),
                owner == IntPtr.Zero ? "无" : ("0x" + owner.ToInt64().ToString("X")),
                r.Left, r.Top, r.Right, r.Bottom, r.Right - r.Left, r.Bottom - r.Top,
                Flags(style, ex)));
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
$cur = [System.Windows.Forms.Cursor]::Position
$curScreen = [System.Windows.Forms.Screen]::FromPoint($cur)
Write-Host ("  光标在 {0} 的 {1}" -f $curScreen.DeviceName, $cur)
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
    # 日志是跨启动追加的，只截最后一个启动横幅之后的部分，否则很容易把上一次
    # 成功启动留下的「界面已挂载」当成本次的。
    $lines = Get-Content -LiteralPath $log -Encoding UTF8
    $i = ($lines | Select-String -SimpleMatch "=== RVC Fabric" | Select-Object -Last 1).LineNumber
    if ($i) { $lines[($i - 1)..($lines.Count - 1)] | ForEach-Object { Write-Host ("  " + $_) } }
} else {
    Write-Host ("没有 {0}" -f $log)
}
