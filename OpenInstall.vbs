' Dev helper: product Setup is Inno Setup (dist\RVC_Fabric_Setup.exe).
' This VBS only opens the 启动器 for environment provision while developing.
Option Explicit
Dim sh, fso, repo, msg
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
repo = fso.GetParentFolderName(WScript.ScriptFullName)

msg = "正式安装请使用 Inno Setup 打出的安装器：" & vbCrLf & _
  "  dist\RVC_Fabric_Setup.exe" & vbCrLf & vbCrLf & _
  "打包：python scripts\build_setup.py" & vbCrLf & _
  "脚本：installer\RVC_Fabric_Setup.iss" & vbCrLf & vbCrLf & _
  "是否打开「启动器」做环境补全调试？"

If MsgBox(msg, vbYesNo + vbInformation, "RVC Fabric Setup") = vbNo Then
  WScript.Quit 0
End If

' Reuse OpenSetup.vbs (bootstrap)
If fso.FileExists(repo & "\OpenSetup.vbs") Then
  sh.Run "wscript.exe //nologo """ & repo & "\OpenSetup.vbs""", 0, False
Else
  MsgBox "Missing OpenSetup.vbs", 16, "RVC Fabric"
  WScript.Quit 1
End If
WScript.Quit 0
