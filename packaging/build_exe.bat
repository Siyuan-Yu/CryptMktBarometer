@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

echo ========================================
echo  CryptMktBarometer - Windows EXE 打包
echo ========================================

if not exist "venv\Scripts\python.exe" (
    echo [错误] 未找到 venv，请先在项目根目录创建虚拟环境并安装依赖。
    exit /b 1
)

echo [0/5] 释放 dist\CryptMktBarometer.exe（必须先关闭正在运行的程序）...
echo       正在结束 CryptMktBarometer.exe 进程...
taskkill /IM CryptMktBarometer.exe /F >nul 2>&1
if errorlevel 1 (
    echo       未发现运行中的 CryptMktBarometer.exe
) else (
    echo       已结束 CryptMktBarometer.exe，等待文件解锁...
)
timeout /t 2 /nobreak >nul

if exist "dist\CryptMktBarometer.exe" (
    del /F /Q "dist\CryptMktBarometer.exe" >nul 2>&1
)
if exist "dist\CryptMktBarometer.exe" (
    echo       无法直接删除，重命名为 CryptMktBarometer.exe.bak ...
    if exist "dist\CryptMktBarometer.exe.bak" del /F /Q "dist\CryptMktBarometer.exe.bak" >nul 2>&1
    move /Y "dist\CryptMktBarometer.exe" "dist\CryptMktBarometer.exe.bak" >nul 2>&1
)
if exist "dist\CryptMktBarometer.exe" (
    echo.
    echo [错误] dist\CryptMktBarometer.exe 仍被占用，无法打包。
    echo   请手动：
    echo     1. 托盘右键 - 退出程序
    echo     2. 打开任务管理器，结束 CryptMktBarometer.exe
    echo     3. 关闭正在使用该 exe 的文件夹窗口 / 杀毒扫描
    echo     4. 再重新运行本脚本
    echo.
    pause
    exit /b 1
)

call venv\Scripts\activate.bat

echo [1/5] 安装打包依赖...
pip install -q pyinstaller pystray pillow

echo [2/5] 生成图标...
python packaging\generate_icon.py
if errorlevel 1 exit /b 1

echo [3/5] 执行 PyInstaller（约 2~5 分钟）...
pyinstaller packaging\CryptMktBarometer.spec --noconfirm --clean
if errorlevel 1 (
    echo.
    echo [错误] 打包失败。若提示 PermissionError / 拒绝访问：
    echo   说明 exe 仍被占用，请完全退出程序后重试。
    pause
    exit /b 1
)

echo [4/5] 校验输出...
if not exist "dist\CryptMktBarometer.exe" (
    echo [错误] 未生成 dist\CryptMktBarometer.exe
    pause
    exit /b 1
)

echo [5/5] 完成
echo.
echo 输出文件: dist\CryptMktBarometer.exe
echo 可将 exe 复制到任意文件夹；首次运行会在同目录生成 config\ 与 data\
echo.
pause
