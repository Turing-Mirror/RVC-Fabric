Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
repo = fso.GetParentFolderName(fso.GetParentFolderName(here))
sh.CurrentDirectory = repo
sh.Run "wscript.exe //nologo """ & repo & "\launcher\run_hidden.vbs"" bootstrap", 0, False