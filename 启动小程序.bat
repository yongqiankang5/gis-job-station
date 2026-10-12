@echo off
chcp 65001 >nul
title GIS 遥感就业情报站
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo [错误] 未找到项目 Python 环境：.venv\Scripts\python.exe
  echo 请先按照 README.md 完成依赖安装。
  pause
  exit /b 1
)

echo 正在启动 GIS 遥感就业情报站……
echo 浏览器将自动打开：http://127.0.0.1:8000
echo 关闭本窗口即可停止服务。
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo.
echo 服务已停止。
pause
