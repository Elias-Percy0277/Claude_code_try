# PowerShell 脚本 - 创建桌面快捷方式
$ProjectPath = "E:\claude_code_project_try\wechat_custody"
$BatFile = Join-Path $ProjectPath "启动微信托管.bat"
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $DesktopPath "微信托管.lnk"

# 创建 WScript.Shell 对象
$WScriptShell = New-Object -ComObject WScript.Shell

# 创建快捷方式
$Shortcut = $WScriptShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $BatFile
$Shortcut.WorkingDirectory = $ProjectPath
$Shortcut.Description = "微信AI托管服务 - 一键启动"
$Shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,25"

# 保存快捷方式
$Shortcut.Save()

# 清理 COM 对象
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($Shortcut) | Out-Null
[System.Runtime.Interopservices.Marshal]::ReleaseComObject($WScriptShell) | Out-Null

Write-Host "桌面快捷方式已创建: $ShortcutPath" -ForegroundColor Green
