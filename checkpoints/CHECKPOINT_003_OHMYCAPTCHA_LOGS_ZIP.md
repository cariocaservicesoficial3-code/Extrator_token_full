# CHECKPOINT 003 - Integração OhMyCaptcha + Sistema de Logs/ZIP

**Data:** 2026-03-31
**Versão:** V7.2
**Autor:** Manus AI

---

## Resumo

Integração de técnicas avançadas do repositório [ohmycaptcha](https://github.com/shenhao-stu/ohmycaptcha) para resolver reCAPTCHA Enterprise de forma mais robusta, implementação de sistema de debug logs completo com compressão ZIP automática, e correção de bugs de timeout/scroll no NetHunter.

---

## Problemas Identificados (V7.0 → V7.2)

### Do Print do Usuário (NetHunter):
1. **Timeout no `page.goto` do cadastro** - `Page.goto: Timeout 30000ms exceeded` ao navegar para a página de cadastro
2. **Timeout no `Locator.click` do radio "#brasileiro"** - Elemento fora do viewport, Playwright tentava scroll mas falhava com "element is outside of the viewport"
3. **Sem logs persistentes** - Não havia como enviar logs para análise

### Causa Raiz:
- `wait_until="networkidle"` é muito lento no NetHunter (3G/4G)
- Radio buttons e checkboxes precisam de scroll explícito + force click
- reCAPTCHA Enterprise precisa de técnicas mais avançadas

---

## Soluções Implementadas

### 1. Integração OhMyCaptcha

**Fonte:** https://github.com/shenhao-stu/ohmycaptcha/blob/main/src/services/recaptcha_v3.py

| Técnica | Descrição | Impacto |
|---------|-----------|---------|
| JS Universal | Detecta `grecaptcha.enterprise \|\| grecaptcha` + injeta script se ausente | Resolve reCAPTCHA mesmo quando o script não carregou |
| Stealth JS | `navigator.webdriver=undefined`, `window.chrome` fake, `navigator.plugins` simulados | Evita detecção de bot |
| Mouse Humano | Movimentos aleatórios de mouse antes do `execute()` | Melhora score do reCAPTCHA v3 |
| Retry 3x | 3 tentativas com `asyncio.sleep(2)` entre cada | Resiliência contra falhas temporárias |
| Validação | Token deve ter `len > 20` | Evita tokens inválidos |

### 2. Correções de Timeout/Scroll

| Correção | Antes | Depois |
|----------|-------|--------|
| `wait_until` | `networkidle` (30s) | `domcontentloaded` (60s) |
| Radio/Checkbox click | `locator.click()` direto | `safe_click()` com scroll + force + JS fallback |
| Preenchimento | `locator.fill()` direto | `safe_fill()` com scroll + type simulado |
| Timeouts | 30s fixo | Configuráveis via config.py |

### 3. Sistema de Logs/ZIP

**Diretório:** `/sdcard/nh_files/logs/`

| Arquivo | Conteúdo |
|---------|----------|
| `DEBUG_LOGS_GEN_TOKENS.txt` | Log principal (tudo) |
| `PLAYWRIGHT_DEBUG.txt` | Ações do Playwright (navegação, cliques, HTML) |
| `HTTP_REQUESTS.txt` | Requests/Responses HTTP detalhados |
| `CYCLE_HISTORY.txt` | Histórico resumido de cada ciclo |
| `screenshots/` | Screenshots de debug |
| `ciclo_NNN_TIMESTAMP.zip` | ZIP por ciclo (logs + screenshots) |
| `sessao_completa_*.zip` | ZIP da sessão inteira (Ctrl+C) |

**Funções de debug implementadas:**
- `debug_pw_action()` - Ações do Playwright
- `debug_pw_navigation()` - Navegações com URL/status
- `debug_pw_element()` - Interações com elementos (selector, action, value)
- `debug_pw_screenshot()` - Screenshots salvos
- `debug_pw_html()` - Conteúdo HTML da página
- `debug_pw_js_eval()` - Avaliações JavaScript
- `debug_pw_error()` - Erros do Playwright com traceback
- `debug_request()` / `debug_response()` - HTTP detalhado
- `criar_zip_ciclo()` - ZIP automático por ciclo
- `criar_zip_sessao()` - ZIP da sessão completa

---

## Arquivos Modificados

| Arquivo | Mudanças |
|---------|----------|
| `movida_playwright.py` | Reescrito com ohmycaptcha, safe_click, safe_fill, scroll, debug |
| `main.py` | V7.2 com ZIP por ciclo, ZIP de sessão, limpar_screenshots |
| `config.py` | LOGS_DIR, timeouts configuráveis, RECAPTCHA_TIMEOUT |
| `logger.py` | Sistema completo de debug + ZIP + rotação |

---

## Próximos Passos

1. Testar no NetHunter e enviar ZIP de logs para análise
2. Ajustar seletores se necessário com base nos screenshots
3. Implementar fallback de login via API direta
4. Otimizar tempo de espera do email de confirmação
