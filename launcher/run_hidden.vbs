' ASCII-only VBS (UTF-8 Chinese breaks VBScript string parsing)
' Usage: wscript //nologo launcher\run_hidden.vbs [bootstrap|app]
Option Explicit
Dim sh, fso, dir, mode, pyw, script, cmd, outFile, ts, line, p
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

dir = fso.GetParentFolderName(WScript.ScriptFullName)
If fso.GetFileName(dir) = "launcher" Then
  dir = fso.GetParentFolderName(dir)
End If
sh.CurrentDirectory = dir

mode = "bootstrap"
If WScript.Arguments.Count >= 1 Then mode = LCase(Trim(WScript.Arguments(0)))

If mode = "app" Or mode = "main" Then
  script = dir & "\launcher\main_app.py"
Else
  script = dir & "\launcher\bootstrap.py"
End If

If Not fso.FileExists(script) Then
  MsgBox "Script not found:" & vbCrLf & script, 16, "RVC launch failed"
  WScript.Quit 1
End If

pyw = ""
If fso.FileExists(dir & "\Runtime\pythonw.exe") Then pyw = dir & "\Runtime\pythonw.exe"
If pyw = "" And fso.FileExists(dir & "\runtime\pythonw.exe") Then pyw = dir & "\runtime\pythonw.exe"
If pyw = "" And fso.FileExists(dir & "\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\pythonw.exe") Then pyw = dir & "\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\pythonw.exe"
If pyw = "" And fso.FileExists(dir & "\Runtime\python.exe") Then pyw = dir & "\Runtime\python.exe"
If pyw = "" And fso.FileExists(dir & "\runtime\python.exe") Then pyw = dir & "\runtime\python.exe"
If pyw = "" And fso.FileExists(dir & "\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\python.exe") Then pyw = dir & "\RVCMAX\RVCMAX_Nvidia_xiaoyuan\Runtime\python.exe"

If pyw = "" Then
  outFile = sh.ExpandEnvironmentStrings("%TEMP%\rvc_where_py.txt")
  sh.Run "cmd /c where pythonw > """ & outFile & """ 2>nul", 0, True
  If fso.FileExists(outFile) Then
    Set ts = fso.OpenTextFile(outFile, 1, False)
    Do While Not ts.AtEndOfStream
      line = Trim(ts.ReadLine)
      If Len(line) > 0 And fso.FileExists(line) Then
        pyw = line
        Exit Do
      End If
    Loop
    ts.Close
  End If
End If

If pyw = "" Then
  outFile = sh.ExpandEnvironmentStrings("%TEMP%\rvc_where_py.txt")
  sh.Run "cmd /c where python > """ & outFile & """ 2>nul", 0, True
  If fso.FileExists(outFile) Then
    Set ts = fso.OpenTextFile(outFile, 1, False)
    Do While Not ts.AtEndOfStream
      line = Trim(ts.ReadLine)
      If Len(line) > 0 And fso.FileExists(line) Then
        p = fso.GetParentFolderName(line) & "\pythonw.exe"
        If fso.FileExists(p) Then
          pyw = p
        Else
          pyw = line
        End If
        Exit Do
      End If
    Loop
    ts.Close
  End If
End If

If pyw = "" Then
  MsgBox "Python not found (pythonw.exe)." & vbCrLf & vbCrLf & _
    "Do one of the following:" & vbCrLf & _
    "1) Install Python 3.9-3.10 and check Add python.exe to PATH" & vbCrLf & _
    "2) Put embeddable runtime at Runtime\pythonw.exe" & vbCrLf & vbCrLf & _
    "Folder:" & vbCrLf & dir, 48, "RVC launch failed"
  WScript.Quit 1
End If

On Error Resume Next
cmd = """" & pyw & """ """ & script & """"
sh.Run cmd, 0, False
If Err.Number <> 0 Then
  MsgBox "Launch error: " & Err.Description & vbCrLf & vbCrLf & _
    "Command:" & vbCrLf & cmd, 16, "RVC launch failed"
  WScript.Quit 1
End If
WScript.Quit 0
