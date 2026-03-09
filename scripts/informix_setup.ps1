# ============================================================================
# Script Helper para Informix - Sistema SEFAZ
# Execute este script antes de usar comandos do Informix
# ============================================================================

# Configurar variaveis de ambiente do Informix
$env:INFORMIXDIR = "C:\Program Files\Informix.15.0.1.0"
$env:INFORMIXSERVER = "ol_informix15"
$env:INFORMIXSQLHOSTS = "$env:INFORMIXDIR\etc\sqlhosts.ol_informix15"
$env:PATH = "$env:INFORMIXDIR\bin;$env:PATH"
$env:ONCONFIG = "onconfig.ol_informix15"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  Informix Environment - Sistema SEFAZ" -ForegroundColor Yellow
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "✅ INFORMIXDIR:    $env:INFORMIXDIR" -ForegroundColor Green
Write-Host "✅ INFORMIXSERVER: $env:INFORMIXSERVER" -ForegroundColor Green
Write-Host ""
Write-Host "Comandos disponiveis:" -ForegroundColor White
Write-Host "  dbaccess          - Cliente SQL interativo" -ForegroundColor Gray
Write-Host "  dbschema          - Extrair schema de tabelas" -ForegroundColor Gray
Write-Host "  onstat            - Status do servidor" -ForegroundColor Gray
Write-Host ""
Write-Host "Exemplos:" -ForegroundColor White
Write-Host "  dbaccess sysmaster           # Acessar banco sysmaster" -ForegroundColor Gray
Write-Host "  dbaccess sysmaster 'info tables'  # Listar tabelas" -ForegroundColor Gray
Write-Host "  onstat -                     # Ver status completo" -ForegroundColor Gray
Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
