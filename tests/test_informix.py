#!/usr/bin/env python3
"""
Script de teste para verificar a conexao com Informix.

Execute este script para testar se a configuracao do Informix esta correta
e se o banco de dados esta acessivel.

Uso:
    python tests/test_informix.py
"""

import sys
from pathlib import Path

# Adiciona o diretorio raiz do projeto ao path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend import informix_db
from backend import external_api


def check_configuration():
    """Testa se as configuracoes do Informix estao presentes."""
    print("=" * 70)
    print("TESTE 1: Verificando configuracoes do Informix")
    print("=" * 70)
    
    conn = informix_db.get_informix_connection()
    
    if not conn.is_configured():
        print("❌ FALHOU: Configuracoes do Informix incompletas no .env")
        print("\nVerifique se as seguintes variaveis estao definidas:")
        print("  - INFORMIX_SERVER")
        print("  - INFORMIX_DATABASE")
        print("  - INFORMIX_HOST")
        print("  - INFORMIX_USER")
        print("  - INFORMIX_PASSWORD")
        print("\nO sistema continuara usando dados MOCK.")
        return False
    
    print("✅ Configuracoes presentes:")
    print(f"   Servidor: {conn.server}")
    print(f"   Banco: {conn.database}")
    print(f"   Host: {conn.host}:{conn.port}")
    print(f"   Usuario: {conn.user}")
    return True


def check_connection():
    """Testa a conexao com o banco."""
    print("\n" + "=" * 70)
    print("TESTE 2: Testando conexao com o banco Informix")
    print("=" * 70)
    
    conn = informix_db.get_informix_connection()
    connection = conn.connect()
    
    if not connection:
        print("❌ FALHOU: Nao foi possivel conectar ao Informix")
        print("\nPossiveis causas:")
        print("  1. Servidor Informix nao esta rodando")
        print("  2. Driver ODBC nao instalado")
        print("  3. Credenciais incorretas")
        print("  4. Firewall bloqueando a porta")
        print("\nO sistema continuara usando dados MOCK.")
        return False
    
    print("✅ Conexao estabelecida com sucesso!")
    conn.close()
    return True


def check_query():
    """Testa uma query simples."""
    print("\n" + "=" * 70)
    print("TESTE 3: Testando query na tabela ordens_servico")
    print("=" * 70)
    
    try:
        ordens = external_api.listar_ordens_servico()
        
        if not ordens:
            print("⚠️  AVISO: Query executada, mas nenhuma OS encontrada")
            print("   Verifique se a tabela 'ordens_servico' existe e tem dados")
            return False
        
        print(f"✅ Query executada com sucesso!")
        print(f"   Total de OS encontradas: {len(ordens)}")
        print(f"\n   Primeiros registros:")
        for os in ordens[:3]:
            print(f"   - {os['numero']}: {os['razao_social']} ({os['status']})")
        
        return True
    
    except Exception as e:
        print(f"❌ FALHOU: Erro ao executar query")
        print(f"   Erro: {e}")
        print("\nPossiveis causas:")
        print("  1. Tabela 'ordens_servico' nao existe")
        print("  2. Nomes de colunas diferentes do esperado")
        print("  3. Permissoes insuficientes no banco")
        return False


def check_specific_query():
    """Testa query por numero especifico."""
    print("\n" + "=" * 70)
    print("TESTE 4: Testando busca por numero especifico")
    print("=" * 70)
    
    try:
        os = external_api.consultar_os_por_numero("OS-2026-001")
        
        if not os:
            print("⚠️  AVISO: OS-2026-001 nao encontrada")
            print("   Execute o script database/schema_informix.sql para popular o banco")
            return False
        
        print(f"✅ Busca especifica funcionando!")
        print(f"   OS encontrada: {os['numero']}")
        print(f"   Razao Social: {os['razao_social']}")
        print(f"   Status: {os['status']}")
        print(f"   Prioridade: {os['prioridade']}")
        
        return True
    
    except Exception as e:
        print(f"❌ FALHOU: Erro ao buscar OS especifica")
        print(f"   Erro: {e}")
        return False


def main():
    """Executa todos os testes."""
    print("\n")
    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║         TESTE DE CONEXAO INFORMIX - Sistema SEFAZ                 ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    print()
    
    results = []
    
    # Teste 1: Configuracao
    results.append(("Configuracao", check_configuration()))
    
    if not results[0][1]:
        print("\n" + "=" * 70)
        print("CONCLUSAO: Configure o Informix no .env antes de continuar")
        print("=" * 70)
        return
    
    # Teste 2: Conexao
    results.append(("Conexao", check_connection()))
    
    if not results[1][1]:
        print("\n" + "=" * 70)
        print("CONCLUSAO: Verifique a instalacao do Informix e do driver ODBC")
        print("=" * 70)
        return
    
    # Teste 3: Query basica
    results.append(("Query Basica", check_query()))
    
    # Teste 4: Query especifica
    results.append(("Query Especifica", check_specific_query()))
    
    # Resumo
    print("\n" + "=" * 70)
    print("RESUMO DOS TESTES")
    print("=" * 70)
    
    for name, result in results:
        status = "✅ PASSOU" if result else "❌ FALHOU"
        print(f"{name:.<50} {status}")
    
    total = len(results)
    passed = sum(1 for _, r in results if r)
    
    print(f"\nTotal: {passed}/{total} testes passaram")
    
    if passed == total:
        print("\n🎉 SUCESSO! Tudo funcionando perfeitamente!")
        print("   O sistema esta pronto para usar o Informix.")
    elif passed >= 2:
        print("\n⚠️  PARCIAL: Conexao OK, mas verifique o schema do banco")
        print("   Execute: dbaccess sefaz_test database/schema_informix.sql")
    else:
        print("\n❌ FALHOU: Sistema usara dados MOCK")
        print("   Consulte TESTE_LOCAL_INFORMIX.md para instrucoes completas")
    
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nTeste cancelado pelo usuario.")
    except Exception as e:
        print(f"\n\n❌ ERRO INESPERADO: {e}")
        import traceback
        traceback.print_exc()
