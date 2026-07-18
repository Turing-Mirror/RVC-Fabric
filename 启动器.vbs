Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
repo = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = repo
sh.Run "wscript.exe //nologo """ & repo & "\launcher\run_hidden.vbs"" bootstrap", 0, False