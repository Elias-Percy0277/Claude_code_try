# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path

project_path = Path(r"E:\claude_code_project_try\wechat_custody")
bat_file = project_path / "start.bat"
desktop = Path.home() / "Desktop"
shortcut_path = desktop / "WeChat AI.lnk"

# Create simple bat file
bat_content = f"""@echo off
chcp 65001 >nul
cd /d "{project_path}"
echo Starting WeChat AI Custody...
python main.py
pause
"""
bat_file.write_text(bat_content, encoding="gbk")

# Create shortcut using PowerShell
import subprocess
ps_script = f"""$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('{shortcut_path}'); $s.TargetPath = '{bat_file}'; $s.WorkingDirectory = '{project_path}'; $s.Save()"""

subprocess.run(["powershell", "-Command", ps_script], capture_output=True)

print(f"Done! Shortcut: {shortcut_path}")
print(f"BAT file: {bat_file}")
