@echo off
REM Inicia so o backend (FastAPI). Chamado pelo start.bat.
REM A configuracao (ATF, admin, etc.) vem do .env, lido na inicializacao.

REM Ir para o diretorio do projeto
cd /d "%~dp0"

echo ============================================================
echo SEFAZ Backend - Iniciando...
echo ============================================================
echo Diretorio: %CD%
echo API em http://127.0.0.1:8000 (a rede entra pelo proxy do front)
echo ============================================================
echo.

REM Ativar ambiente virtual
call .venv\Scripts\activate.bat

REM Iniciar uvicorn. --reload e modo de desenvolvimento: recarrega a cada
REM arquivo salvo. Para uso continuo, rode sem ele.
uvicorn backend.main:app --reload
