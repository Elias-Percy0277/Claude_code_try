Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

ProjectPath = "E:\claude_code_project_try\wechat_custody"
BatFile = ProjectPath & "\启动微信托管.bat"
DesktopPath = WshShell.SpecialFolders("Desktop")
ShortcutPath = DesktopPath & "\微信托管.lnk"

Set Shortcut = WshShell.CreateShortcut(ShortcutPath)
Shortcut.TargetPath = BatFile
Shortcut.WorkingDirectory = ProjectPath
Shortcut.Description = "WeChat AI Custody Service"
Shortcut.Save

WScript.Echo "Desktop shortcut created: " & ShortcutPath
