@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ==============================================
echo  GIS就业情报站 - 一键更新数据
echo ==============================================
echo.

cd /d "%~dp0"

:: ========== 配置区：第一次用请改这里 ==========
set GIT_REMOTE=origin
set GIT_BRANCH=main
:: ============================================

echo [1/6] 激活虚拟环境...
call .\.venv\Scripts\activate.bat
if errorlevel 1 (
    echo ❌ 虚拟环境启动失败，请先运行"首次安装并启动.bat"
    pause
    exit /b 1
)

echo.
echo [2/6] 备份当前数据库...
if not exist "backups" mkdir backups
copy /y "data\gis_jobs.db" "backups\gis_jobs_%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%.db" >nul
echo ✅ 备份完成

echo.
echo [3/6] 抓取BOSS岗位数据...
echo ⚠️  注意：会弹出浏览器窗口，如果遇到验证码请手动完成
echo ⚠️  抓取频率不要太高，建议每周1次即可
pause
python scripts\run_boss_scraper.py --login-first --keywords "GIS,遥感,测绘,地理信息" --max-pages 20
if errorlevel 1 (
    echo ⚠️  抓取过程有错误，但继续执行后续步骤
)

echo.
echo [4/6] 清洗、去重、重新评分...
python scripts\run_clean.py
if errorlevel 1 (
    echo ❌ 清洗失败，请检查错误
    pause
    exit /b 1
)

echo.
echo [5/6] 导出小程序静态数据...
python scripts\export_miniprogram_data.py
if errorlevel 1 (
    echo ❌ 导出失败
    pause
    exit /b 1
)

echo.
echo [6/6] 提交数据更新到Git仓库...
git add miniprogram/data/ data/gis_jobs.db
git diff --staged --quiet
if errorlevel 1 (
    git commit -m "自动更新数据: %date% %time%"
    echo 📤 推送到远程仓库...
    git push %GIT_REMOTE% %GIT_BRANCH%
    if errorlevel 1 (
        echo ⚠️  Git推送失败，请检查网络或仓库权限
    ) else (
        echo ✅ 数据已提交并推送
    )
) else (
    echo ℹ️  没有数据变更，跳过提交
)

echo.
echo ==============================================
echo  ✅ 全部完成！
echo ==============================================
echo.
echo 下一步：
echo 1. 打开微信开发者工具，重新预览即可看到新数据
echo 2. 如果配置了线上CDN，用户打开小程序会自动拉最新数据
echo.
pause
