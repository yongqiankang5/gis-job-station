@echo off
chcp 65001 >nul
cd /d "%~dp0"
call .\.venv\Scripts\activate.bat
echo 浏览器会自动弹出BOSS直聘登录页
echo 扫码登录成功后，回到这个窗口按回车开始抓取
pause
python scripts\run_boss_scraper.py --login-first --keywords "GIS,遥感,测绘,地理信息" --max-pages 10
echo.
echo 抓取完成，按任意键关闭
pause
