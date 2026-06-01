Dim WshShell, fso, ProjectPath, BatFile, DesktopPath, ShortcutPath, Shortcut

Set WshShell = WScript.CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

ProjectPath = "E:\claude_code_project_try\wechat_custody"
BatFile = ProjectPath & "\启动微信托管.bat"
DesktopPath = WshShell.SpecialFolders("Desktop")

' Create shortcut
ShortcutPath = DesktopPath & "\微信托管.lnk"
Set Shortcut = WshShell.CreateShortcut(ShortcutPath)

Shortcut.TargetPath = BatFile
Shortcut.WorkingDirectory = ProjectPath
Shortcut.Description = "微信AI托管服务"
Shortcut.IconLocation = "cmd.exe,0"
Shortcut.Save

MsgBox "桌面快捷方式已创建！" & vbCrLf & ShortcutPath, 64, "创建成功"
