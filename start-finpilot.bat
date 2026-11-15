@echo off
setlocal EnableExtensions
chcp 936 >nul
title FinPilot 一键启动
pushd "%~dp0" >nul

rem  用法：双击 start-finpilot.bat 即可。
rem        强制重装依赖：start-finpilot.bat --install

set "FORCE_INSTALL=0"
if /i "%~1"=="--install" set "FORCE_INSTALL=1"

echo.
echo   ==================================================
echo     FinPilot v16  一键启动
echo   ==================================================
echo.

set "PYEXE=%~dp0.venv\Scripts\python.exe"

rem ---------------- 1. 检查 / 创建虚拟环境 ----------------
if exist "%PYEXE%" goto have_venv

echo   [1/4] 未找到 .venv，正在创建虚拟环境 ...
set "PY="
where py >nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto create_venv
where python >nul 2>nul
if not errorlevel 1 set "PY=python"
if not defined PY goto no_python

:create_venv
%PY% -m venv .venv
if errorlevel 1 goto venv_failed
if not exist "%PYEXE%" goto venv_failed
echo   [1/4] 虚拟环境创建完成。
goto check_version

:have_venv
echo   [1/4] 已找到 .venv。

:check_version
"%PYEXE%" -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if errorlevel 1 goto python_too_old

rem ---------------- 2. 安装依赖 ----------------
if "%FORCE_INSTALL%"=="1" goto do_install
"%PYEXE%" -c "import fastapi, uvicorn, dotenv, httpx" >nul 2>nul
if errorlevel 1 goto do_install
echo   [2/4] 依赖已就绪，跳过安装。
goto deps_done

:do_install
echo   [2/4] 正在安装依赖（首次运行需要几分钟）...
"%PYEXE%" -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto pip_failed

:deps_done

rem ---------------- 3. 准备 .env ----------------
if exist ".env" goto env_present
if not exist ".env.example" goto no_env_example
copy /y ".env.example" ".env" >nul
echo   [3/4] 已从 .env.example 生成 .env。
goto env_ready

:env_present
echo   [3/4] 配置文件 .env 已就绪。

:env_ready
findstr /r /c:"^DEEPSEEK_API_KEY=." ".env" >nul 2>nul
if errorlevel 1 (
    echo   [提示] .env 中未填入 DEEPSEEK_API_KEY。若系统环境变量也未设置，
    echo          助手将以离线模式回答；填入密钥后重新启动即可使用 DeepSeek。
)

rem ---------------- 4. 选择端口并启动 ----------------
set "PORT=8000"
:port_loop
call :port_free %PORT%
if errorlevel 1 goto port_next
goto port_ready

:port_next
set /a PORT+=1
if %PORT% LEQ 8010 goto port_loop
echo   [错误] 8000-8010 端口均被占用，请先关闭占用端口的程序。
goto fail

:port_ready
echo   [4/4] 使用端口 %PORT%，正在启动服务 ...
echo.
echo   首页:     http://127.0.0.1:%PORT%
echo   工作台:   http://127.0.0.1:%PORT%/workspace
echo   演示页:   http://127.0.0.1:%PORT%/demo
echo   使用指南: http://127.0.0.1:%PORT%/help
echo   API 文档: http://127.0.0.1:%PORT%/docs
echo.
echo   关闭此窗口或按 Ctrl+C 即可停止服务。
echo.

rem 服务就绪后自动打开浏览器（轮询 /api/health）
start "" /min powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command "for ($i=0; $i -lt 60; $i++) { try { Invoke-WebRequest 'http://127.0.0.1:%PORT%/api/health' -UseBasicParsing -TimeoutSec 2 | Out-Null; Start-Process 'http://127.0.0.1:%PORT%/'; break } catch { Start-Sleep -Milliseconds 500 } }"

"%PYEXE%" -m uvicorn app.main:app --host 127.0.0.1 --port %PORT%
set "EXIT_CODE=%errorlevel%"

echo.
if not "%EXIT_CODE%"=="0" echo   服务异常退出（代码 %EXIT_CODE%），请查看上方日志。
echo   服务已停止。
pause
popd >nul
endlocal
exit /b 0

rem ================= 子过程 =================
:port_free
netstat -ano -p tcp | findstr /r /c:":%~1 .*LISTENING" >nul 2>nul
if errorlevel 1 exit /b 0
exit /b 1

:no_python
echo.
echo   [错误] 未检测到 Python。请先安装 Python 3.11 或更高版本，
echo          安装时勾选 "Add python.exe to PATH"，然后重新运行本脚本。
goto fail

:venv_failed
echo.
echo   [错误] 虚拟环境创建失败，请检查 Python 安装与目录写入权限。
goto fail

:python_too_old
echo.
echo   [错误] .venv 中的 Python 版本低于 3.11。请删除 .venv 文件夹后重试。
goto fail

:pip_failed
echo.
echo   [错误] 依赖安装失败。请检查网络连接，或稍后运行：start-finpilot.bat --install
goto fail

:no_env_example
echo.
echo   [错误] 缺少 .env 和 .env.example，无法准备配置。
goto fail

:fail
echo.
pause
popd >nul
endlocal
exit /b 1
