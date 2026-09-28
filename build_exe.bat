@echo off
setlocal

echo ================================================
echo   %~n0 - Gerador de executavel do TikVoice
echo ================================================
echo.

REM Verifica se o PyInstaller esta instalado; instala se necessario.
python -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo Instalando o PyInstaller...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo.
        echo ERRO: nao foi possivel instalar o PyInstaller.
        echo Verifique se o Python e o pip estao no PATH.
        pause
        exit /b 1
    )
)

echo.
echo Gerando o executavel (isso pode levar 1-2 minutos)...
echo.

REM Usamos "python -m PyInstaller" em vez do comando "pyinstaller" direto,
REM pois o atalho de linha de comando as vezes fica numa pasta que nao
REM esta no PATH do Windows. Chamando via "python -m" isso nao importa.
python -m PyInstaller --noconfirm --onefile --windowed --name "TikVoice" app_gui.py

if errorlevel 1 (
    echo.
    echo ERRO: a geracao do executavel falhou. Veja as mensagens acima.
    pause
    exit /b 1
)

echo.
echo ================================================
echo Pronto! O executavel foi gerado em:
echo   dist\TikVoice.exe
echo.
echo Voce pode copiar esse arquivo para qualquer pasta
echo e rodar sem precisar instalar Python ou bibliotecas.
echo ================================================
echo.
pause
