Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Get current directory
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Construct paths
pythonExe = fso.BuildPath(currentDir, ".venv\Scripts\pythonw.exe")
scriptFile = fso.BuildPath(currentDir, "Controller.pyw")

' Verify files exist
If Not fso.FileExists(pythonExe) Then
    MsgBox "Error: Python executable not found at " & pythonExe, 16, "Launch Error"
    WScript.Quit
End If

If Not fso.FileExists(scriptFile) Then
    MsgBox "Error: Script file not found at " & scriptFile, 16, "Launch Error"
    WScript.Quit
End If

' Use cmd /c start to launch the process.
' This effectively "detaches" the python process from the script host, 
' treating it as a new, independent application (like double-clicking).
' Syntax: cmd /c start "Title" /D "WorkDir" "Executable" "Arguments"
' Note: We use "pythonw.exe" so no console window will appear for the python process itself.
' The cmd window itself is hidden by the WshShell.Run 0.

command = "cmd /c start ""CyberController"" /D " & Chr(34) & currentDir & Chr(34) & " " & Chr(34) & pythonExe & Chr(34) & " " & Chr(34) & scriptFile & Chr(34)

' Run the cmd command hidden
WshShell.Run command, 0, False

Set WshShell = Nothing
Set fso = Nothing
