@echo off
REM Script para iniciar o Backend com configuracoes do Informix

REM Ir para o diretorio do projeto
cd /d "%~dp0"

REM Configurar ambiente Informix
set "INFORMIXDIR=C:\Program Files\Informix.15.0.1.0_CSDK"
set "INFORMIXSQLHOSTS=%~dp0sqlhosts"
set "INFORMIXSERVER=ol_informix15"

REM Mostrar configuracoes
echo ============================================================
echo SEFAZ Backend - Iniciando...
echo ============================================================
echo Diretorio: %CD%
echo INFORMIXDIR: %INFORMIXDIR%
echo INFORMIXSQLHOSTS: %INFORMIXSQLHOSTS%
echo INFORMIXSERVER: %INFORMIXSERVER%
echo ============================================================
echo.

REM Ativar ambiente virtual
call .venv\Scripts\activate.bat

REM Iniciar uvicorn
uvicorn backend.main:app --reload
