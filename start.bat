@echo off
REM ============================================================
REM Script para iniciar Backend e Frontend do Sistema SEFAZ
REM ============================================================

echo.
echo ╔══════════════════════════════════════════════════════════╗
echo ║           SISTEMA SEFAZ - INICIANDO SERVICOS            ║
echo ╚══════════════════════════════════════════════════════════╝
echo.

REM Verificar se estamos no diretorio correto
if not exist "backend\main.py" (
    echo ❌ ERRO: Execute este script na raiz do projeto sistema_sefaz
    pause
    exit /b 1
)

REM Verificar se o venv existe
if not exist ".venv\Scripts\activate.bat" (
    echo ⚠️  Ambiente virtual nao encontrado
    echo.
    echo Criando ambiente virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo ❌ Erro ao criar ambiente virtual
        pause
        exit /b 1
    )
    echo ✅ Ambiente virtual criado
    echo.
)

REM Verificar se as dependencias estao instaladas
echo Verificando dependencias...
call .venv\Scripts\activate.bat
python -c "import fastapi" 2>nul
if errorlevel 1 (
    echo.
    echo ⚠️  Dependencias do backend nao instaladas
    echo Instalando dependencias...
    pip install -r backend\requirements.txt
    if errorlevel 1 (
        echo ❌ Erro ao instalar dependencias
        pause
        exit /b 1
    )
    echo ✅ Dependencias instaladas
    echo.
)

REM Verificar node_modules do frontend
if not exist "frontend\node_modules" (
    echo.
    echo ⚠️  node_modules nao encontrado
    echo Instalando dependencias do frontend...
    npm --prefix .\frontend install
    if errorlevel 1 (
        echo ❌ Erro ao instalar dependencias do frontend
        pause
        exit /b 1
    )
    echo ✅ Dependencias do frontend instaladas
    echo.
)

echo.
echo ✅ Tudo pronto! Iniciando servidores...
echo.
echo ┌──────────────────────────────────────────────────────────┐
echo │  Backend:  http://localhost:8000                         │
echo │  Docs:     http://localhost:8000/docs                    │
echo │  Frontend: http://localhost:5173                         │
echo └──────────────────────────────────────────────────────────┘
echo.
echo 💡 Pressione Ctrl+C em ambas as janelas para parar
echo.

REM Iniciar backend em nova janela (usando script dedicado)
start "SEFAZ Backend" cmd /k "%~dp0start_backend.bat"

REM Aguardar 2 segundos para o backend iniciar
timeout /t 2 /nobreak >nul

REM Iniciar frontend em nova janela
start "SEFAZ Frontend" cmd /k "npm --prefix .\frontend run dev"

echo.
echo ✅ Servidores iniciados em janelas separadas!
echo.
echo Para parar os servidores:
echo   1. Feche as janelas "SEFAZ Backend" e "SEFAZ Frontend"
echo      OU
echo   2. Pressione Ctrl+C em cada janela
echo.

timeout /t 3 /nobreak >nul

echo Abrindo navegador...
timeout /t 5 /nobreak >nul
start http://localhost:5173

echo.
echo Pressione qualquer tecla para fechar esta janela...
pause >nul
