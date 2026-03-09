#!/bin/bash
# ============================================================
# Script para iniciar Backend e Frontend do Sistema SEFAZ
# ============================================================

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║           SISTEMA SEFAZ - INICIANDO SERVICOS            ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Verificar se estamos no diretório correto
if [ ! -f "backend/main.py" ]; then
    echo "❌ ERRO: Execute este script na raiz do projeto sistema_sefaz"
    exit 1
fi

# Verificar se o venv existe
if [ ! -d ".venv" ]; then
    echo "⚠️  Ambiente virtual não encontrado"
    echo ""
    echo "Criando ambiente virtual..."
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo "❌ Erro ao criar ambiente virtual"
        exit 1
    fi
    echo "✅ Ambiente virtual criado"
    echo ""
fi

# Ativar ambiente virtual
source .venv/bin/activate

# Verificar se as dependências estão instaladas
echo "Verificando dependências..."
python -c "import fastapi" 2>/dev/null
if [ $? -ne 0 ]; then
    echo ""
    echo "⚠️  Dependências do backend não instaladas"
    echo "Instalando dependências..."
    pip install -r backend/requirements.txt
    if [ $? -ne 0 ]; then
        echo "❌ Erro ao instalar dependências"
        exit 1
    fi
    echo "✅ Dependências instaladas"
    echo ""
fi

# Verificar node_modules do frontend
if [ ! -d "frontend/node_modules" ]; then
    echo ""
    echo "⚠️  node_modules não encontrado"
    echo "Instalando dependências do frontend..."
    npm --prefix ./frontend install
    if [ $? -ne 0 ]; then
        echo "❌ Erro ao instalar dependências do frontend"
        exit 1
    fi
    echo "✅ Dependências do frontend instaladas"
    echo ""
fi

echo ""
echo "✅ Tudo pronto! Iniciando servidores..."
echo ""
echo "┌──────────────────────────────────────────────────────────┐"
echo "│  Backend:  http://localhost:8000                         │"
echo "│  Docs:     http://localhost:8000/docs                    │"
echo "│  Frontend: http://localhost:5173                         │"
echo "└──────────────────────────────────────────────────────────┘"
echo ""
echo "💡 Pressione Ctrl+C para parar ambos os servidores"
echo ""

# Função para limpar processos ao sair
cleanup() {
    echo ""
    echo "Parando servidores..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    echo "✅ Servidores parados"
    exit 0
}

# Capturar Ctrl+C
trap cleanup INT TERM

# Iniciar backend em background
uvicorn backend.main:app --reload &
BACKEND_PID=$!

# Aguardar backend iniciar
sleep 3

# Iniciar frontend em background
npm --prefix ./frontend run dev &
FRONTEND_PID=$!

echo ""
echo "✅ Servidores iniciados!"
echo "   Backend PID: $BACKEND_PID"
echo "   Frontend PID: $FRONTEND_PID"
echo ""
echo "Pressione Ctrl+C para parar"
echo ""

# Aguardar mais um pouco e abrir navegador
sleep 5
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:5173
elif command -v open &> /dev/null; then
    open http://localhost:5173
fi

# Manter o script rodando
wait
