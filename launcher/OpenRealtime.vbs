' Launch advanced realtime panel (gui_v1) without black console.
' Used by release TM_Voice.exe so child Runtime is not polluted by PyInstaller env.
Option Explicit
Dim sh, fso, repo, pyw, py, script, logf, ts, rc
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Prefer package root: parent of this script when under launcher\, else script folder
repo = fso.GetParentFolderName(WScript.ScriptFullName)
If fso.GetFileName(repo) = "launcher" Then
  repo = fso.GetParentFolderName(repo)
End If
' Allow override from parent process
If Len(sh.Environment("Process")("TM_VOICE_ROOT")) > 0 Then
  repo = sh.Environment("Process")("TM_VOICE_ROOT")
End If
sh.CurrentDirectory = repo

If Not fso.FolderExists(repo & "\User_Data") Then fso.CreateFolder(repo & "\User_Data")
If Not fso.FolderExists(repo & "\User_Data\logs") Then fso.CreateFolder(repo & "\User_Data\logs")
logf = repo & "\User_Data\logs\realtime_gui_vbs.log"
Set ts = fso.CreateTextFile(logf, True)
ts.WriteLine "OpenRealtime.vbs"
ts.WriteLine "repo=" & repo

pyw = repo & "\Runtime\pythonw.exe"
py = repo & "\Runtime\python.exe"
If Not fso.FileExists(pyw) Then pyw = py
If Not fso.FileExists(pyw) Then
  ts.WriteLine "NO_RUNTIME"
  ts.Close
  MsgBox "Runtime\pythonw.exe not found under:" & vbCrLf & repo, 16, "RVC Fabric"
  WScript.Quit 1
End If

script = repo & "\gui_v1.py"
If Not fso.FileExists(script) Then
  ts.WriteLine "NO_SCRIPT"
  ts.Close
  MsgBox "gui_v1.py not found under:" & vbCrLf & repo, 16, "RVC Fabric"
  WScript.Quit 1
End If

' Clean interpreter pollution for embedded Runtime (PyInstaller parent)
sh.Environment("Process")("PYTHONPATH") = repo
On Error Resume Next
sh.Environment("Process").Remove "PYTHONHOME"
sh.Environment("Process").Remove "_MEIPASS"
On Error GoTo 0

ts.WriteLine "pyw=" & pyw
ts.WriteLine "script=" & script
ts.Close

' Style 0 = hide console if Runtime fell back to python.exe; pythonw has no console.
' FreeSimpleGUI still creates its own window.
rc = sh.Run("""" & pyw & """ """ & script & """", 0, False)
Set ts = fso.OpenTextFile(logf, 8, True)
ts.WriteLine "Run rc=" & rc & " (async)"
ts.Close
