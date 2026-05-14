@echo off
title FreeCAD Python Dependencies Installer

echo ============================================
echo   FreeCAD Python Dependencies Installer
echo ============================================
echo.

set "PYTHON_EXE="

if exist "C:\Program Files\FreeCAD 1.1\bin\python.exe" (
    set "PYTHON_EXE=C:\Program Files\FreeCAD 1.1\bin\python.exe"
    goto :found
)
if exist "C:\Program Files\FreeCAD 1.0\bin\python.exe" (
    set "PYTHON_EXE=C:\Program Files\FreeCAD 1.0\bin\python.exe"
    goto :found
)
if exist "C:\Program Files\FreeCAD\bin\python.exe" (
    set "PYTHON_EXE=C:\Program Files\FreeCAD\bin\python.exe"
    goto :found
)
if exist "C:\Program Files (x86)\FreeCAD 1.1\bin\python.exe" (
    set "PYTHON_EXE=C:\Program Files (x86)\FreeCAD 1.1\bin\python.exe"
    goto :found
)
if exist "C:\Program Files (x86)\FreeCAD\bin\python.exe" (
    set "PYTHON_EXE=C:\Program Files (x86)\FreeCAD\bin\python.exe"
    goto :found
)

echo [ERROR] FreeCAD python.exe not found!
echo.
echo Please input full path to python.exe:
echo   Example: C:\Program Files\FreeCAD 1.1\bin\python.exe
echo.
set /p "PYTHON_EXE=python.exe path: "

if not exist "%PYTHON_EXE%" (
    echo [ERROR] File not found: %PYTHON_EXE%
    pause
    exit /b 1
)

:found
echo [OK] Python: %PYTHON_EXE%
echo.

echo [1/2] Upgrading pip...
"%PYTHON_EXE%" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.

echo [2/2] Installing websockets==13.1 ...
"%PYTHON_EXE%" -m pip install websockets==13.1 -i https://pypi.tuna.tsinghua.edu.cn/simple
echo.

if %errorlevel% equ 0 (
    echo ============================================
    echo   Install SUCCESS!
    echo ============================================
) else (
    echo ============================================
    echo   Install FAILED, check errors above
    echo ============================================
)

echo.
pause
