Dim fso, scriptDir
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "cmd /c cd /d """ & scriptDir & """ && python -u price_check.py >> apteka.log 2>&1", 0, False
