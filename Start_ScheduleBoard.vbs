Option Explicit

Dim fileSystem, projectRoot, pythonwPath, scriptPath, shell
Set fileSystem = CreateObject("Scripting.FileSystemObject")
projectRoot = fileSystem.GetParentFolderName(WScript.ScriptFullName)
pythonwPath = fileSystem.BuildPath(projectRoot, ".venv\Scripts\pythonw.exe")
scriptPath = fileSystem.BuildPath(projectRoot, "sch_gantt_main.py")

If Not fileSystem.FileExists(pythonwPath) Then
    MsgBox "Python was not found: " & pythonwPath, 16, "Schedule-board"
    WScript.Quit 1
End If

If Not fileSystem.FileExists(scriptPath) Then
    MsgBox "Python script was not found: " & scriptPath, 16, "Schedule-board"
    WScript.Quit 1
End If

If WScript.Arguments.Named.Exists("validate") Then WScript.Quit 0

Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = projectRoot
shell.Run Chr(34) & pythonwPath & Chr(34) & " " & Chr(34) & scriptPath & Chr(34), 1, False
