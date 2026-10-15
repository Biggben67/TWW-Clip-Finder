@echo off
setlocal
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
    echo Visual Studio C++ build tools were not found.
    exit /b 1
)
for /f "usebackq delims=" %%I in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VS=%%I"
if not defined VS exit /b 1
call "%VS%\VC\Auxiliary\Build\vcvars64.bat"
if errorlevel 1 exit /b 1
set "CMAKE=%VS%\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
if not exist "%CMAKE%" set "CMAKE=cmake"
"%CMAKE%" -S "%~dp0." -B "%~dp0build" -G "NMake Makefiles" -DCMAKE_BUILD_TYPE=Release -DTWW_ENGINE_SOURCE="%~dp0.."
if errorlevel 1 exit /b 1
"%CMAKE%" --build "%~dp0build" --target tww_slash_worker
if errorlevel 1 exit /b 1
if not exist "%~dp0bin" mkdir "%~dp0bin"
copy /y "%~dp0build\tww_slash_worker.exe" "%~dp0bin\tww_slash_worker.exe" >nul
exit /b %errorlevel%
