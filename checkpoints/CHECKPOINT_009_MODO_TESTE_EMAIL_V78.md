# CHECKPOINT 009 - MODO TESTE EMAIL + FIX FALSO POSITIVO (V7.8)

**Data**: 2026-03-31
**Versão**: V7.8
**Status**: IMPLEMENTADO - Aguardando teste do usuário

---

## DIAGNÓSTICO DO PROBLEMA (V7.7)

### Bug Identificado: FALSO POSITIVO na detecção de sucesso

O script V7.7 reportava "Cadastro SUCESSO" mas o email de confirmação **nunca chegava**. Após análise detalhada dos logs e do código, foi identificado que o cadastro **NÃO estava sendo realmente efetuado**.

### Causa Raiz

Na linha 1121 do `movida_playwright.py` V7.7:

```python
if "/usuario/cadastro" not in str(submit_resp.url):
    log("OK", f"URL mudou para {submit_resp.url} - possível sucesso!")
    STATS["cadastros_ok"] += 1
    return "sucesso"
```

**O problema**: A URL de resposta era `https://www.movida.com.br/usuario/enviar-cadastro`. O teste `"/usuario/cadastro" not in "/usuario/enviar-cadastro"` retorna **True** porque `/usuario/cadastro` **NÃO é substring** de `/usuario/enviar-cadastro` (tem `enviar-` no meio).

Resultado: O script assumia "sucesso" quando na verdade o servidor retornava HTTP 200 com a **mesma página de cadastro** (falha silenciosa).

### Evidências dos Logs

```
[10:21:15.074] [WARN] HTTP 200 sem indicadores claros
[10:21:15.077] [DEBUG] Response URL: https://www.movida.com.br/usuario/enviar-cadastro
[10:21:16.051] [OK] URL mudou para https://www.movida.com.br/usuario/enviar-cadastro - possível sucesso!
[10:21:16.055] [OK] Cadastro SUCESSO na tentativa 1!
```

O body da resposta continha o HTML completo da página de cadastro (Firebase, GTM, formulário), confirmando que o servidor simplesmente recarregou o formulário sem mensagem de erro explícita.

---

## MUDANÇAS V7.8

### 1. main.py - MODO TESTE COM EMAIL MANUAL

**Objetivo**: Desativar Emailnator temporariamente e usar email real do usuário para testar se o cadastro realmente funciona.

**Mudanças**:
- Emailnator **desativado** (import comentado)
- Novo fluxo: script pede email do usuário via `input()` no início
- Após cadastro, **para e mostra dados** para o usuário verificar email manualmente
- Se email chegar → problema era no Emailnator
- Se email NÃO chegar → confirma falso positivo do cadastro
- Se usuário colar link de confirmação → continua com ativação/login
- Banner atualizado para V7.8 MODO TESTE
- Função `pedir_email_usuario()` com validação básica e confirmação
- Função `executar_ciclo_teste()` substitui `executar_ciclo()`
- Suporte ao novo status `"incerto"` do cadastro

### 2. movida_playwright.py - FIX FALSO POSITIVO

**Mudanças críticas**:

| Aspecto | V7.7 (Bug) | V7.8 (Fix) |
|---------|-----------|------------|
| `allow_redirects` | `False` | `True` (segue redirects automaticamente) |
| Body logado | 3000 chars | 10000 chars |
| Detecção redirect | Verificava header Location | Verifica `submit_resp.history` |
| HTTP 200 unclear | Assumia sucesso se URL ≠ `/usuario/cadastro` | **Verifica se body contém formulário** |
| Formulário recarregado | Não detectado | Detectado como FALHA |
| Status "incerto" | Não existia | Novo status para HTTP 200 sem formulário e sem indicadores |

**Detecção de formulário recarregado** (NOVO):
```python
form_reloaded = any(s in resp_lower for s in [
    'id="formcadastro"',
    'id="btnenvia',
    'formcadastro',
    'enviadados',
])
```

Se o body contém o formulário de cadastro → **FALHA silenciosa confirmada** → retorna `"erro_generico"`.

**Busca de erros ocultos no body** (NOVO):
Quando formulário recarregado é detectado, o script procura por classes CSS de erro, alertas, modais e mensagens específicas para dar mais contexto sobre a falha.

**Import adicionado**: `C` (cores) importado de `config.py` para uso nas mensagens de log coloridas.

---

## ARQUIVOS MODIFICADOS

| Arquivo | Mudança |
|---------|---------|
| `src/main.py` | Reescrito para modo teste com email manual |
| `src/movida_playwright.py` | Fix falso positivo + allow_redirects + body completo |
| `checkpoints/CHECKPOINT_009_MODO_TESTE_EMAIL_V78.md` | Este arquivo |

---

## COMO TESTAR

1. Rodar o script: `python3 src/main.py`
2. Colar um email real quando solicitado
3. Aguardar o cadastro ser processado
4. Verificar a caixa de email (inbox, spam, promoções)
5. Responder ao script se o email chegou ou não

### Resultados esperados:

- **Se email CHEGAR**: O cadastro funciona! Problema é no Emailnator.
- **Se email NÃO CHEGAR + status "sucesso"**: Falso positivo parcialmente corrigido (redirect detectado mas cadastro pode ter outro problema).
- **Se status "erro_generico" com "formulário recarregado"**: Fix V7.8 funcionando! O script agora detecta corretamente que o cadastro falhou.
- **Se status "incerto"**: Cenário novo que precisa de mais investigação.

---

## PRÓXIMOS PASSOS

1. **Executar teste com email real** para confirmar diagnóstico
2. Se falso positivo confirmado:
   - Investigar por que o POST HTTP falha silenciosamente
   - Possíveis causas: token reCAPTCHA, encoding, cookie de sessão
   - Considerar usar Playwright `page.evaluate('$('#formCadastro').submit()')` ao invés de HTTP direto
3. Se email chegar:
   - Reativar Emailnator
   - Investigar por que Emailnator não recebe os emails
4. Após resolver, restaurar fluxo automático completo
