' First-run helper (no black console). Double-click this if start.bat flashes.
Option Explicit
Dim sh, fso, repo, pyw, py, script, logf, ts, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
repo = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = repo

If Not fso.FolderExists(repo & "\TEMP") Then fso.CreateFolder(repo & "\TEMP")
logf = repo & "\TEMP\last_launch.log"
Set ts = fso.CreateTextFile(logf, True)
ts.WriteLine "OpenSetup.vbs"
ts.WriteLine "repo=" & repo

pyw = repo & "\Runtime\pythonw.exe"
py = repo & "\Runtime\python.exe"
If Not fso.FileExists(pyw) Then pyw = repo & "\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\pythonw.exe"
If Not fso.FileExists(py) Then py = repo & "\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\python.exe"
If Not fso.FileExists(pyw) Then pyw = py

If Not fso.FileExists(pyw) Then
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
ts.WriteLine "pyw=" & pyw
ts.WriteLine "script=" & script
ts.Close

' 1 = normal window focus; False = do not wait
rc = sh.Run("""" & pyw & """ """ & script & """", 1, False)
' Cannot get GUI crash code when async; write marker
Set ts = fso.OpenTextFile(logf, 8, True)
ts.WriteLine "Run rc=" & rc & " (async start)"
ts.Close
