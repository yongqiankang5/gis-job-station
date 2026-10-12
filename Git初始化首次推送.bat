@echo off
chcp 65001 >nul
echo ==============================================
echo  GIS就业情报站 - Git首次初始化
echo ==============================================
echo.

cd /d "%~dp0"

echo [1/5] 初始化Git仓库...
git init
git branch -M main

echo.
echo [2/5] 配置用户信息...
git config user.name "yongqiankang5"
git config user.email "your-email@example.com"
echo ✅ 用户名已设置为 yongqiankang5
echo ⚠️  请把上面的邮箱改成你自己的GitHub邮箱

echo.
echo [3/5] 添加所有文件...
git add .

echo.
echo [4/5] 提交本地版本...
git commit -m "首次提交: GIS就业情报站小程序版"

echo.
echo [5/5] 关联远程仓库并推送...
echo ⚠️  请先在GitHub上新建一个名为 gis-job-station 的仓库！
echo.
set /p confirm="确认仓库已创建，按回车继续..."

git remote add origin https://github.com/yongqiankang5/gis-job-station.git
git push -u origin main

echo.
echo ==============================================
echo  ✅ Git初始化完成！
echo ==============================================
echo.
echo 下一步：
echo 1. 打开 https://github.com/yongqiankang5/gis-job-station/settings/pages
echo 2. Source 选择 main 分支根目录，保存
echo 3. 等1分钟就能访问线上数据了
echo.
pause
