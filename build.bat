@echo off
REM ============================================================
REM  卡牌游戏日常任务自动化 — 打包脚本
REM  要求: pip install pyinstaller
REM ============================================================

echo.
echo   请选择打包模式:
echo     1 = 开发调试 (带控制台, 不压缩, 快速)
echo     2 = 最终打包 (无控制台, 压缩, 单文件)
echo.

set /p choice="输入 1 或 2: "

if "%choice%"=="1" goto debug
if "%choice%"=="2" goto release
echo 无效选择 & pause & exit /b

:debug
echo.
echo === 开发调试模式 ===
pyinstaller gui.spec ^
    --noconfirm ^
    --console ^
    --debug=all ^
    --clean
echo.
echo 输出: dist/I'm Yours.exe (含控制台, 可看错误)
pause
exit /b

:release
echo.
echo === 最终打包模式 ===
pyinstaller gui.spec ^
    --noconfirm ^
    --windowed ^
    --clean
echo.
echo ============================================================
echo   打包完成！
echo   输出: dist/I'm Yours.exe
echo.
echo   部署时需要放到 exe 同目录的文件:
echo     - config.yaml      (配置文件)
echo     - platform-tools\   (含 adb.exe)
echo     - logs\             (日志目录, 自动创建)
echo ============================================================
pause
exit /b
