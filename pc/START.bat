@echo off
rem Double-click to start sending. Extra options pass through, e.g.  START.bat --wifi
python "%~dp0sender.py" %*
pause
