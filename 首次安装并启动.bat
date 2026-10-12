@echo off
chcp 65001 >nul
title GIS 遥感就业情报站 - 首次安装
cd /d "%~dp0"

echo ============================================================
echo GIS 遥感就业情报站 - 首次安装
echo ============================================================
echo 本操作会在当前目录创建独立 Python 环境并安装项目依赖。
echo 请确保电脑已安装 Python 3.10 或更高版本，并保持网络连接。
echo.

if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>&1
  if errorlevel 1 (
    where python >nul 2>&1
    if errorlevel 1 (
      echo [错误] 未检测到 Python，请先安装 Python 3.10 或更高版本。
      pause
      exit /b 1
    )
    python -m venv .venv
  ) else (
    py -3 -m venv .venv
  )
  if errorlevel 1 (
    echo [错误] Python 虚拟环境创建失败。
    pause
    exit /b 1
  )
)

echo 正在安装依赖，首次安装可能需要几分钟……
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto install_failed
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto install_failed

if not exist ".env" copy ".env.example" ".env" >nul

echo.
echo 安装完成，正在启动：http://127.0.0.1:8000
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:8000'"
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
exit /b 0

:install_failed
echo.
echo [错误] 依赖安装失败，请检查网络或查看上方错误信息。
pause
exit /b 1
