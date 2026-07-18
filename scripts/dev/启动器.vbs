' Redirect Chinese-named entry to ASCII launcher
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
sh.Run "wscript.exe //nologo """ & dir & "\launcher\run_hidden.vbs"" bootstrap", 0, False
