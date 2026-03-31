#!/bin/bash
# ==============================================================================
# AJATO TOKEN GENERATOR V7.0 - Instalador para Kali Linux NetHunter
# ==============================================================================

set -e

echo "╔══════════════════════════════════════════════════════════════╗"
echo "║     AJATO TOKEN GENERATOR V7.0 - INSTALADOR NETHUNTER       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# Cores
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
log_info() { echo -e "${YELLOW}[INFO]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; }

# ==============================================================================
# 1. Atualizar sistema
# ==============================================================================
log_info "Atualizando pacotes do sistema..."
apt-get update -y 2>/dev/null || pkg update -y 2>/dev/null || true
log_ok "Sistema atualizado!"

# ==============================================================================
# 2. Instalar dependências do sistema
# ==============================================================================
log_info "Instalando dependencias do sistema..."

# Dependências para Playwright/Chromium
DEPS="python3 python3-pip wget curl unzip libnss3 libnspr4 libatk1.0-0 \
      libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
      libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
      libxshmfence1 fonts-liberation libappindicator3-1"

for dep in $DEPS; do
    apt-get install -y "$dep" 2>/dev/null || true
done
log_ok "Dependencias instaladas!"

# ==============================================================================
# 3. Instalar Python packages
# ==============================================================================
log_info "Instalando pacotes Python..."
pip3 install --upgrade pip 2>/dev/null || true
pip3 install playwright requests 2>/dev/null
log_ok "Pacotes Python instalados!"

# ==============================================================================
# 4. Instalar Chromium para Playwright
# ==============================================================================
log_info "Instalando Chromium para Playwright..."
python3 -m playwright install chromium 2>/dev/null || playwright install chromium 2>/dev/null
log_ok "Chromium instalado!"

# ==============================================================================
# 5. Instalar dependências do Playwright
# ==============================================================================
log_info "Instalando dependencias do Playwright..."
python3 -m playwright install-deps chromium 2>/dev/null || true
log_ok "Dependencias do Playwright instaladas!"

# ==============================================================================
# 6. Criar diretórios
# ==============================================================================
log_info "Criando diretorios..."
mkdir -p /sdcard/nh_files/screenshots 2>/dev/null || mkdir -p ~/ajato_tokens/screenshots
log_ok "Diretorios criados!"

# ==============================================================================
# 7. Teste rápido
# ==============================================================================
log_info "Testando instalacao..."
python3 -c "from playwright.sync_api import sync_playwright; print('Playwright OK!')" 2>/dev/null
if [ $? -eq 0 ]; then
    log_ok "Instalacao concluida com sucesso!"
else
    log_fail "Erro na instalacao do Playwright!"
    exit 1
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  INSTALACAO CONCLUIDA! Para executar:                       ║"
echo "║                                                              ║"
echo "║  cd src && python3 main.py                                   ║"
echo "╚══════════════════════════════════════════════════════════════╝"
