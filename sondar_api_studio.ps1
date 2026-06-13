# sondar_api_studio.ps1 - Sonda a API do Agent Server sem navegador.
#
# COMO RODAR (da raiz do projeto):
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\sondar_api_studio.ps1
#
# ANTES DE RODAR: troque a URL abaixo pela do seu tunel atual (do terminal do
# langgraph dev). O tunel muda a cada reinicio.

$ErrorActionPreference = "Continue"

# >>> TROQUE pela URL atual do seu tunel <<<
$base = "https://semester-communist-reserved-stevens.trycloudflare.com
"

Write-Host ""
Write-Host "============================================================"
Write-Host " SONDA DA API DO AGENT SERVER"
Write-Host " base: $base"
Write-Host "============================================================"

Write-Host ""
Write-Host "[1] O tunel responde? (GET /ok)"
try {
    $r = Invoke-RestMethod -Uri "$base/ok" -Method Get -TimeoutSec 25
    Write-Host "  OK:"
    Write-Host ($r | ConvertTo-Json -Compress)
} catch {
    Write-Host "  FALHOU:"
    Write-Host $_.Exception.Message
    Write-Host "  Se aqui falhou, o tunel esta morto. Reinicie o langgraph dev --tunnel."
}

Write-Host ""
Write-Host "[2] Grafos expostos (POST /assistants/search)"
try {
    $corpo = '{"limit":100,"offset":0}'
    $r = Invoke-RestMethod -Uri "$base/assistants/search" -Method Post -ContentType "application/json" -Body $corpo -TimeoutSec 25
    if (-not $r -or $r.Count -eq 0) {
        Write-Host "  VAZIO: o servidor nao expoe nenhum assistente."
    } else {
        foreach ($a in $r) {
            Write-Host ("  graph_id=" + $a.graph_id + " | name=" + $a.name + " | id=" + $a.assistant_id)
        }
    }
} catch {
    Write-Host "  FALHOU:"
    Write-Host $_.Exception.Message
}

Write-Host ""
Write-Host "============================================================"
Write-Host " LEITURA:"
Write-Host " [1] FALHOU         => tunel morto; reinicie langgraph dev --tunnel"
Write-Host " [2] tem assistente => SERVIDOR CERTO; problema e so a UI"
Write-Host " [2] tem agent/vazio => investigar studio.py"
Write-Host "============================================================"
Write-Host ""

Read-Host "Pressione ENTER para fechar"
