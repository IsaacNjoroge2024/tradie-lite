@echo off
echo Checking for TradingView Desktop installation...

:: Kill any existing TradingView processes to ensure debug port binds correctly
echo Closing any running TradingView instances...
taskkill /F /IM TradingView.exe >nul 2>&1

:: 1. Standard Program Files paths
if exist "C:\Program Files\TradingView\TradingView.exe" (
    echo Launching TradingView Desktop in debug mode on port 9222...
    start "" "C:\Program Files\TradingView\TradingView.exe" --remote-debugging-port=9222
    exit /b
)

if exist "%LOCALAPPDATA%\TradingView\TradingView.exe" (
    echo Launching TradingView Desktop in debug mode on port 9222...
    start "" "%LOCALAPPDATA%\TradingView\TradingView.exe" --remote-debugging-port=9222
    exit /b
)

:: 2. Windows Store (AppX) package path resolving via PowerShell
echo Checking Windows Store package...
for /f "usebackq tokens=*" %%p in (`powershell -NoProfile -Command "(Get-AppxPackage -Name '*TradingView*').InstallLocation"`) do (
    if exist "%%p\TradingView.exe" (
        echo Launching TradingView Store App in debug mode on port 9222...
        echo Path: %%p\TradingView.exe
        start "" "%%p\TradingView.exe" --remote-debugging-port=9222
        exit /b
    )
)

:: 3. Fallback to Google Chrome
echo TradingView Desktop not found.
echo Launching Google Chrome in debug mode on port 9222 pointing to TradingView chart...
if exist "C:\Program Files\Google\Chrome\Application\chrome.exe" (
    start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="%TEMP%\chrome-debug-profile" "https://www.tradingview.com/chart/"
) else (
    echo Error: Google Chrome was not found at standard path either.
    echo Please start a Chromium-based browser with: --remote-debugging-port=9222 --user-data-dir="%TEMP%\chrome-debug-profile"
)
