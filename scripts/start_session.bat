@echo off
echo Starting Tradie Lite session...

:: Start browser/TradingView in debug mode
call "%~dp0launch_tradingview_debug.bat"

:: Start data bridge in a new window
start "Tradie Lite Data Bridge" cmd /k call "%~dp0start_data_bridge.bat"

:: Start Claude Code with absolute MCP config path
start "Claude Code" cmd /k "cd /d "%~dp0.." && claude --mcp-config "%~dp0..\claude-config\mcp.json""

echo Tradie Lite is ready. Open TradingView (in debug browser) and Claude Code.
