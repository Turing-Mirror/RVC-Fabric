' Launch headless realtime worker (no FreeSimpleGUI window).
' Used by release TM_Voice.exe so Runtime is not polluted by PyInstaller env.
Option Explicit
Dim sh, fso, repo, pyw, py, script, logf, ts, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

repo = fso.GetParentFolderName(WScript.ScriptFullName)
If fso.GetFileName(repo) = "launcher" Then
  repo = fso.GetParentFolderName(repo)
End If
If Len(sh.Environment("Process")("TM_VOICE_ROOT")) > 0 Then
  repo = sh.Environment("Process")("TM_VOICE_ROOT")
End If
sh.CurrentDirectory = repo

If Not fso.FolderExists(repo & "\User_Data") Then fso.CreateFolder(repo & "\User_Data")
If Not fso.FolderExists(repo & "\User_Data\logs") Then fso.CreateFolder(repo & "\User_Data\logs")
logf = repo & "\User_Data\logs\realtime_worker_vbs.log"
Set ts = fso.CreateTextFile(logf, True)
ts.WriteLine "OpenRealtimeWorker.vbs"
ts.WriteLine "repo=" & repo

pyw = repo & "\Runtime\pythonw.exe"
py = repo & "\Runtime\python.exe"
If Not fso.FileExists(pyw) Then pyw = py
If Not fso.FileExists(pyw) Then
  ts.WriteLine "NO_RUNTIME"
  ts.Close
  WScript.Quit 1
End If

script = repo & "\tools\realtime_worker.py"
If Not fso.FileExists(script) Then
  ts.WriteLine "NO_SCRIPT"
  ts.Close
  WScript.Quit 1
End If

sh.Environment("Process")("PYTHONPATH") = repo
sh.Environment("Process")("TM_REALTIME_WORKER") = "1"
sh.Environment("Process")("TM_VOICE_ROOT") = repo
On Error Resume Next
sh.Environment("Process").Remove "PYTHONHOME"
sh.Environment("Process").Remove "_MEIPASS"
On Error GoTo 0

ts.WriteLine "pyw=" & pyw
ts.WriteLine "script=" & script
ts.Close

' Window style 0 = hidden
rc = sh.Run("""" & pyw & """ """ & script & """", 0, False)
Set ts = fso.OpenTextFile(logf, 8, True)
ts.WriteLine "Run rc=" & rc & " (async)"
ts.Close
