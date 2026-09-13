@echo off
title FantaOracle - primo avvio su questo PC
cd /d "%~dp0"
echo.
echo  FantaOracle: preparo l'ambiente in "%~dp0"
echo  (consiglio: questa cartella stia sul disco del PC, non sulla chiavetta)
echo.
where python >nul 2>&1
if errorlevel 1 (
  echo  Python non trovato. Installa Python 3.12 da https://www.python.org/downloads/
  echo  spuntando "Add python.exe to PATH", poi rilancia questo file.
  pause
  exit /b 1
)
python installa.py
if errorlevel 1 (
  echo.
  echo  Installazione non riuscita: leggi le righe sopra.
  pause
  exit /b 1
)
echo.
echo  Pronto. Apro il menu: le prossime volte basta FantaOracle.bat
call FantaOracle.bat
