@echo off
cd /d "%~dp0"
title YOUTUBE FARM

REM ---------------- caminho rapido ----------------
REM .pronto guarda o caminho do pythonw depois que as dependencias foram conferidas
REM uma vez. Sem esse cache, conferir os imports custa 6,2 SEGUNDOS a cada abertura
REM (medido) — e o app importa tudo de novo logo em seguida, entao era tempo jogado
REM fora. Com o cache, o .bat nao chama o Python nenhuma vez antes de abrir.
if not exist ".pronto" goto conferir
set "PYW="
set /p PYW=<.pronto
if not exist "%PYW%" goto conferir
start "" "%PYW%" app.py
exit /b 0

REM ---------------- primeira vez ----------------
:conferir
set "PY="
where py >nul 2>&1
if %errorlevel%==0 set "PY=py"
if not defined PY (
  where python >nul 2>&1
  if %errorlevel%==0 set "PY=python"
)
if not defined PY (
  echo.
  echo   Python nao encontrado nesta maquina.
  echo.
  echo   Instale em:  https://www.python.org/downloads/
  echo   IMPORTANTE: marque "Add Python to PATH" na primeira tela do instalador.
  echo.
  pause
  exit /b 1
)

%PY% -c "import fastapi,uvicorn,webview,anthropic,PIL" >nul 2>&1
if %errorlevel%==0 goto guardar

echo.
echo   Primeira abertura: instalando as dependencias do Python.
echo   Sao uns 30 MB, leva 1 ou 2 minutos. Nao feche esta janela.
echo.
%PY% -m pip install --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  echo.
  echo   Nao consegui instalar as dependencias.
  echo   Confira sua internet e abra o app de novo.
  echo.
  pause
  exit /b 1
)
echo.
echo   Pronto. Abrindo o app...

:guardar
REM pythonw = sem janela preta; a janela do app e' a interface.
set "PYW="
for /f "usebackq delims=" %%P in (`%PY% -c "import sys,os;print(os.path.join(os.path.dirname(sys.executable),'pythonw.exe'))"`) do set "PYW=%%P"
if not exist "%PYW%" (
  start "" %PY% app.py
  exit /b 0
)
>.pronto echo %PYW%
start "" "%PYW%" app.py
exit /b 0
