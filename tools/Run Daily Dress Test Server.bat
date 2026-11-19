@echo off
setlocal

rem This only affects this launcher. It does not change Modrinth or Windows.
set "DD_TEST_JAVA=C:\Program Files\Eclipse Adoptium\jdk-25.0.3.9-hotspot"
if not exist "%DD_TEST_JAVA%\bin\java.exe" (
    echo Daily Dress test mode needs Java 25 at:
    echo %DD_TEST_JAVA%
    echo Update this launcher if Java was installed somewhere else.
    pause
    exit /b 1
)

set "JAVA_HOME=%DD_TEST_JAVA%"
pushd "%~dp0.."
for /f "tokens=2 delims==" %%V in ('findstr /b "minecraft_version=" gradle.properties') do set "DD_MC_VERSION=%%V"
set "DD_TEST_SERVER=%~dp0..\dev-workspace\%DD_MC_VERSION%\server"
if not exist "%DD_TEST_SERVER%" mkdir "%DD_TEST_SERVER%"
if not exist "%DD_TEST_SERVER%\server.properties" copy /Y "%~dp0Daily Dress Test Server.properties" "%DD_TEST_SERVER%\server.properties" >nul
call gradlew.bat --no-daemon runServer
set "DD_EXIT=%ERRORLEVEL%"
popd
if not "%DD_EXIT%"=="0" pause
exit /b %DD_EXIT%
