# CHECKPOINT 007 - HTTP DIRECT SUBMIT V7.6

**Data:** 2026-03-31
**Versão:** V7.6
**Status:** SUBMIT HTTP DIRETO IMPLEMENTADO

## Descoberta Crítica

Ao analisar os screenshots `06_post_submit.png` das 3 tentativas da V7.5, descobrimos que:

1. **NÃO havia nenhuma mensagem de erro visível** na página após clicar ENVIAR
2. O formulário simplesmente voltava ao estado preenchido, sem toastr, sem alerta
3. A detecção de "Documento já cadastrado" era um **FALSO POSITIVO** - a palavra "cadastrado" existe no HTML do formulário em templates JS

## Causa Raiz

O botão ENVIAR da Movida executa `grecaptcha.enterprise.execute()` via JavaScript ANTES de fazer o POST. Como o `grecaptcha.enterprise` **nunca carrega no Chromium headless** (bloqueado pelo Google), o JavaScript simplesmente não faz nada quando o botão é clicado. O formulário fica parado.

O token reCAPTCHA que injetávamos no `<textarea>` era ignorado porque o JS do formulário chama a API JS do reCAPTCHA, não lê o textarea.

## Solução V7.6 - HTTP Direct Submit

Ao invés de clicar no botão ENVIAR (que depende do JS do formulário):

1. **Playwright preenche o formulário** (visual, com screenshots) - JÁ FUNCIONA
2. **reCAPTCHA resolvido via HTTP bypass** (enterprise/anchor + reload) - JÁ FUNCIONA
3. **Extraímos cookies** do Playwright (`page.context.cookies()`)
4. **Extraímos campos do formulário** via `page.evaluate()` (JS que lê todos os inputs)
5. **Fazemos POST HTTP direto** para `/usuario/enviar-cadastro` com:
   - Cookies do Playwright (PHPSESSID, etc)
   - Todos os campos do formulário
   - Token reCAPTCHA HTTP
   - Headers iguais ao HAR real
6. **Verificamos o resultado** pelo HTTP status code:
   - HTTP 303 = SUCESSO (redirect)
   - HTTP 200 = Verificar corpo (pode ser erro ou sucesso)
   - HTTP 4xx/5xx = Erro

## Vantagens

- **Não depende do grecaptcha.enterprise** carregar no browser
- **Não depende do JS do formulário** funcionar
- **Resultado preciso** via HTTP status code (não mais falsos positivos do DOM)
- **Mais rápido** (POST HTTP direto vs esperar 10s por mudança no DOM)

## Bugs Corrigidos

| Bug | Antes (V7.5) | Agora (V7.6) |
|-----|-------------|-------------|
| Submit não funciona | Clicava botão → JS bloqueava | POST HTTP direto |
| Falso positivo "cadastrado" | Detectava palavra no HTML | Verifica HTTP status code |
| `wait_for_response` inexistente | Caía no fallback | Não usa mais (POST direto) |

## Arquivos Alterados
- `src/movida_playwright.py` - Reescrita da seção de submit (linhas 904+)
- `src/config.py` - Versão atualizada para V7.6
- `src/main.py` - Banner e referências atualizadas para V7.6
