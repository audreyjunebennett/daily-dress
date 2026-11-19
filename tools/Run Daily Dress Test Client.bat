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
call gradlew.bat --no-daemon runClient
set "DD_EXIT=%ERRORLEVEL%"
popd
if not "%DD_EXIT%"=="0" pause
exit /b %DD_EXIT%
