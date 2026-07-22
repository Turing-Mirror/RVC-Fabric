' Launch headless realtime worker with a clean Runtime environment.
' Used by frozen 变声器.exe so host Python 3.13 / PyInstaller never pollutes Runtime 3.9.
Option Explicit
Dim sh, fso, repo, py, script, logf, vblog, ts, rc, cmdLine, env
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
Set env = sh.Environment("Process")

repo = fso.GetParentFolderName(WScript.ScriptFullName)
If fso.GetFileName(repo) = "launcher" Then
  repo = fso.GetParentFolderName(repo)
End If
If Len(env("TM_VOICE_ROOT")) > 0 Then
  repo = env("TM_VOICE_ROOT")
End If
sh.CurrentDirectory = repo

If Not fso.FolderExists(repo & "\User_Data") Then fso.CreateFolder(repo & "\User_Data")
If Not fso.FolderExists(repo & "\User_Data\logs") Then fso.CreateFolder(repo & "\User_Data\logs")
vblog = repo & "\User_Data\logs\realtime_worker_vbs.log"
logf = repo & "\User_Data\logs\realtime_worker.log"
Set ts = fso.CreateTextFile(vblog, True)
ts.WriteLine "OpenRealtimeWorker.vbs"
ts.WriteLine "repo=" & repo

' Prefer python.exe so cmd redirect captures traceback; hide window via Run style 0
py = repo & "\Runtime\python.exe"
If Not fso.FileExists(py) Then py = repo & "\Runtime\pythonw.exe"
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

' --- scrub host / PyInstaller / conda pollution (must match win_util spirit) ---
Dim dropList, i, k
dropList = Array( _
  "PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP", "PYTHONEXECUTABLE", "PYTHONUSERBASE", _
  "PYTHONWARNINGS", "PYTHONDONTWRITEBYTECODE", "PYTHONNOUSERSITE", "PYTHONUNBUFFERED", _
  "_MEIPASS", "_PYI_APPLICATION_HOME_DIR", "_PYI_ARCHIVE_FILE", _
  "TCL_LIBRARY", "TK_LIBRARY", "TIX_LIBRARY", _
  "VIRTUAL_ENV", "CONDA_PREFIX", "CONDA_DEFAULT_ENV", "CONDA_PYTHON_EXE", "CONDA_SHLVL", _
  "PIP_TARGET", "UV_PROJECT", "UV_PYTHON", "POETRY_ACTIVE", _
  "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE" _
)
On Error Resume Next
For i = 0 To UBound(dropList)
  env.Remove dropList(i)
Next
On Error GoTo 0

' Clean assignment for Runtime child
env("PYTHONPATH") = repo
env("TM_REALTIME_WORKER") = "1"
env("TM_VOICE_ROOT") = repo
env("PYTHONUNBUFFERED") = "1"
env("PYTHONNOUSERSITE") = "1"
' PATH: Runtime first (DLL load), then package root, then system PATH as inherited
Dim path0
path0 = repo & "\Runtime;" & repo & ";" & env("PATH")
env("PATH") = path0

ts.WriteLine "py=" & py
ts.WriteLine "script=" & script
ts.WriteLine "TM_USE_DML=" & env("TM_USE_DML")
ts.WriteLine "TM_ACCEL=" & env("TM_ACCEL")
ts.WriteLine "TM_ACCEL_RESOLVED=" & env("TM_ACCEL_RESOLVED")
ts.WriteLine "PYTHONPATH=" & env("PYTHONPATH")
ts.Close

Dim args
' Quote every path segment — install dirs may contain spaces (e.g. E:\RVC Fabric)
args = """" & py & """ -u """ & script & """"
If env("TM_USE_DML") = "1" Then
  args = args & " --dml"
End If

cmdLine = "cmd.exe /c (" & args & ") >> """ & logf & """ 2>&1"
Set ts = fso.OpenTextFile(vblog, 8, True)
ts.WriteLine "cmdline=" & cmdLine
ts.Close

rc = sh.Run(cmdLine, 0, False)
Set ts = fso.OpenTextFile(vblog, 8, True)
ts.WriteLine "Run rc=" & rc & " (async)"
ts.Close
