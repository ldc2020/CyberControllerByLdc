Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
' 获取当前脚本所在的目录
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
' 设置工作目录为脚本所在目录，确保能找到 cybercontroller.bat
WshShell.CurrentDirectory = currentDir
WshShell.Run chr(34) & "cybercontroller.bat" & Chr(34), 0
Set WshShell = Nothing