# CHECKPOINT 006 - V7.5 Smart Retry + AJAX Submit

**Data:** 2026-03-31
**Versão:** V7.5
**Status:** Correção de bugs críticos do cadastro

---

## Problemas Identificados nos Logs V7.4

### 1. CPF Duplicado (PRINCIPAL)
- O 4devs gera CPFs que já existem na base da Movida
- O script V7.4 usava o MESMO CPF nas 3 tentativas = 100% falha
- Erro detectado: `"Documento já cadastrado"` no HTML pós-submit

### 2. Submit Esperava Navegação (60s timeout)
- O formulário da Movida usa AJAX (não navega após submit)
- `page.expect_navigation()` sempre dava timeout de 60s
- Perda de 60s por tentativa = 180s desperdiçados por ciclo

### 3. Erros Falsos nos Logs
- Templates JS do código-fonte eram detectados como erros reais
- Exemplo: `" + getErroValidacaoLabel() + "` aparecia como erro
- Poluía os logs com informação inútil

---

## Correções Implementadas

### A. Smart Retry com Novo CPF (main.py)
```
fazer_cadastro_playwright() agora retorna STATUS STRING:
  - "sucesso" → cadastro OK
  - "cpf_duplicado" → CPF já existe, gerar novo
  - "captcha_fail" → reCAPTCHA falhou, retentar
  - "erro_generico" → outro erro

Loop de retry:
  - Até 6 tentativas (MAX_CADASTRO_RETRIES=6)
  - Até 5 CPFs diferentes (max_cpf_retries=5)
  - Gera nova pessoa completa (nome, endereço, telefone) a cada CPF novo
```

### B. AJAX Submit (movida_playwright.py)
```
ANTES (V7.4):
  page.expect_navigation(timeout=60000) → SEMPRE timeout

AGORA (V7.5):
  1. page.wait_for_response("enviar-cadastro") → intercepta AJAX
  2. Polling DOM por 10s (20 x 500ms) → detecta toastr/mensagem
  3. Analisa HTTP status + JSON response + DOM text
```

### C. Detecção Inteligente de Erros
```
- Filtra templates JS (contém getErro, response., +)
- Verifica toastr visível via JS evaluate
- Detecta "Documento já cadastrado" em 3 locais:
  1. page_text (innerText)
  2. page_content (HTML)
  3. submit_response_data (JSON AJAX)
```

---

## Resultados Esperados

| Métrica | V7.4 | V7.5 (esperado) |
|---------|------|------------------|
| Tempo por tentativa | ~80s (60s timeout) | ~20s (10s AJAX) |
| CPF duplicado | 3 tentativas iguais | Gera novo CPF |
| Erros falsos nos logs | Muitos | Filtrados |
| Chance de cadastro | Baixa (mesmo CPF) | Alta (5 CPFs) |

---

## Arquivos Modificados
- `src/config.py` - MAX_CADASTRO_RETRIES=6, versão V7.5
- `src/movida_playwright.py` - AJAX submit, retorno string, detecção inteligente
- `src/main.py` - Smart retry loop com novo CPF

## Próximos Passos
- Testar no NetHunter e verificar se cadastro passa
- Se "Documento já cadastrado" persistir com CPFs novos, investigar se 4devs gera CPFs reais
- Monitorar taxa de sucesso do reCAPTCHA HTTP bypass
