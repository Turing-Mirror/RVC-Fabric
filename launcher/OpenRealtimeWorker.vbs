' Launch headless realtime worker (no FreeSimpleGUI window).
' Used by release TM_Voice.exe so Runtime is not polluted by PyInstaller env.
' Stdout/stderr go to User_Data\logs\realtime_worker.log via cmd redirect
' (pythonw alone often discards console streams).
Option Explicit
Dim sh, fso, repo, py, pyw, script, logf, vblog, ts, rc, cmdLine
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
vblog = repo & "\User_Data\logs\realtime_worker_vbs.log"
logf = repo & "\User_Data\logs\realtime_worker.log"
Set ts = fso.CreateTextFile(vblog, True)
ts.WriteLine "OpenRealtimeWorker.vbs"
ts.WriteLine "repo=" & repo

' Prefer python.exe (stdout redirect works); hide window via cmd /c start style 0
py = repo & "\Runtime\python.exe"
pyw = repo & "\Runtime\pythonw.exe"
If Not fso.FileExists(py) Then py = pyw
If Not fso.FileExists(py) Then
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
sh.Environment("Process")("PYTHONUNBUFFERED") = "1"
On Error Resume Next
sh.Environment("Process").Remove "PYTHONHOME"
sh.Environment("Process").Remove "_MEIPASS"
On Error GoTo 0

ts.WriteLine "py=" & py
ts.WriteLine "script=" & script
ts.WriteLine "TM_USE_DML=" & sh.Environment("Process")("TM_USE_DML")
ts.WriteLine "TM_ACCEL=" & sh.Environment("Process")("TM_ACCEL")
ts.WriteLine "TM_ACCEL_RESOLVED=" & sh.Environment("Process")("TM_ACCEL_RESOLVED")
ts.Close

Dim args
args = """" & py & """ -u """ & script & """"
If sh.Environment("Process")("TM_USE_DML") = "1" Then
  args = args & " --dml"
End If

' cmd /c with redirect so crash traceback always lands in realtime_worker.log
' Window style 0 = hidden
cmdLine = "cmd.exe /c (" & args & ") >> """ & logf & """ 2>&1"
Set ts = fso.OpenTextFile(vblog, 8, True)
ts.WriteLine "cmdline=" & cmdLine
ts.Close

rc = sh.Run(cmdLine, 0, False)
Set ts = fso.OpenTextFile(vblog, 8, True)
ts.WriteLine "Run rc=" & rc & " (async)"
ts.Close
