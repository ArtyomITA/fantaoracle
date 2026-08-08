@echo off
title FantaOracle
cd /d "%~dp0"
start "" "http://localhost:8899/viz/index.html"
python scripts\fantaoracle_app.py --porta 8899
