@echo off
title FantaOracle
cd /d "%~dp0"
set PY=python
if exist ".venv\Scripts\python.exe" set PY=.venv\Scripts\python.exe
start "" "http://localhost:8899/viz/index.html"
%PY% scripts\fantaoracle_app.py --porta 8899
