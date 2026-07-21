' First-run helper — silent launch (no black console). Double-click this, or use start.bat.
Option Explicit
Dim sh, fso, repo, pyw, py, script, logf, ts, rc, winStyle, cmd
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
repo = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = repo

If Not fso.FolderExists(repo & "\TEMP") Then fso.CreateFolder(repo & "\TEMP")
logf = repo & "\TEMP\last_launch.log"
Set ts = fso.CreateTextFile(logf, True)
ts.WriteLine "OpenSetup.vbs"
ts.WriteLine "repo=" & repo

pyw = ""
py = ""
If fso.FileExists(repo & "\Runtime\pythonw.exe") Then pyw = repo & "\Runtime\pythonw.exe"
If fso.FileExists(repo & "\Runtime\python.exe") Then py = repo & "\Runtime\python.exe"
If pyw = "" And fso.FileExists(repo & "\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\pythonw.exe") Then
  pyw = repo & "\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\pythonw.exe"
End If
If py = "" And fso.FileExists(repo & "\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\python.exe") Then
  py = repo & "\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\python.exe"
End If
If pyw = "" Then pyw = py

If pyw = "" Or Not fso.FileExists(pyw) Then
  ts.WriteLine "NO_RUNTIME"
  ts.Close
  MsgBox "Runtime\pythonw.exe not found." & vbCrLf & "Run scripts\sync_from_rvcmax.bat first.", 16, "Turing Mirror"
  WScript.Quit 1
End If

script = repo & "\launcher\bootstrap.py"
If Not fso.FileExists(script) Then
  ts.WriteLine "NO_SCRIPT"
  ts.Close
  MsgBox "Missing launcher\bootstrap.py", 16, "Turing Mirror"
  WScript.Quit 1
End If

sh.Environment("Process")("PYTHONPATH") = repo
sh.Environment("Process")("TM_VOICE_ROOT") = repo
On Error Resume Next
sh.Environment("Process").Remove "PYTHONHOME"
sh.Environment("Process").Remove "_MEIPASS"
On Error GoTo 0

winStyle = 0
cmd = """" & pyw & """ """ & script & """"
ts.WriteLine "pyw=" & pyw
ts.WriteLine "script=" & script
ts.WriteLine "winStyle=" & winStyle
ts.Close

rc = sh.Run(cmd, winStyle, False)
Set ts = fso.OpenTextFile(logf, 8, True)
ts.WriteLine "Run rc=" & rc & " (async start)"
ts.Close
WScript.Quit 0
