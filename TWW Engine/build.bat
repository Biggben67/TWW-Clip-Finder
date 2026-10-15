@echo off
rem Configure and build with MSVC, then run the suite.
setlocal
set VS=C:\Program Files\Microsoft Visual Studio\2022\Community
call "%VS%\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
if errorlevel 1 (
  echo build.bat: vcvars64.bat failed. Is Visual Studio 2022 Community at "%VS%"?
  exit /b 1
)
set PATH=%VS%\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja;%PATH%
cd /d %~dp0
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo || exit /b 1
cmake --build build || exit /b 1
build\tests\tww_engine_tests.exe %*
