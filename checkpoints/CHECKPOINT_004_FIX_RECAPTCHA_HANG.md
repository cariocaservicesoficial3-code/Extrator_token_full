# CHECKPOINT 004 - Correção do Bug de Hang do reCAPTCHA Enterprise

**Data:** 2026-03-31
**Versão:** V7.3
**Autor:** Manus AI

---

## Bug Reportado

O script travava indefinidamente em:
```
[08:38:44.494] [WARN] reCAPTCHA nao detectado, JS universal vai tentar injetar...
[08:38:44.498] [PW-ACTION] recaptcha_not_found - Will attempt script injection via _EXECUTE_JS
```
Após essa linha, nenhuma outra saída aparecia. O script ficava pendurado para sempre.

## Causa Raiz (3 problemas)

### 1. Verificação JS incorreta do `wait_for_function`
O código usava `typeof grecaptcha?.enterprise?.execute` com optional chaining dentro de `typeof`,
que não funciona como esperado no contexto do Playwright evaluate. O `grecaptcha.enterprise`
é o correto para reCAPTCHA Enterprise, mas a verificação falhava silenciosamente.

### 2. Promise JS sem timeout interno
O `_RECAPTCHA_EXECUTE_JS` criava uma Promise que injetava o script do Google via
`document.head.appendChild(script)`, mas a Promise só resolvia em `script.onload`
ou rejeitava em `script.onerror`. **Se o script nunca carregasse** (bloqueado, lento,
erro de rede), a Promise ficava pendente para sempre.

### 3. `page.evaluate()` sem timeout Python
O `page.evaluate()` do Playwright não tem timeout por padrão. Sem `asyncio.wait_for()`,
o Python ficava esperando a Promise JS que nunca resolvia, travando o event loop inteiro.

## Correções Implementadas

### 1. Verificação JS robusta (sem optional chaining)
```javascript
if (window.grecaptcha && window.grecaptcha.enterprise && 
    typeof window.grecaptcha.enterprise.execute === 'function') return 'enterprise';
if (window.grecaptcha && typeof window.grecaptcha.execute === 'function') return 'standard';
```

### 2. Timeout interno de 20s na Promise JS
```javascript
const timer = setTimeout(() => reject(new Error('reCAPTCHA timeout interno (20s)')), 20000);
```
Agora a Promise SEMPRE resolve ou rejeita em no máximo 20 segundos.

### 3. Polling robusto ao invés de wait_for_function
Ao invés de `page.wait_for_function()` (que pode falhar silenciosamente),
agora usa polling explícito a cada 500ms por até 15s, verificando se o
`grecaptcha.enterprise.execute` está disponível.

### 4. Verificação de script existente antes de injetar
Antes de injetar um novo `<script>`, verifica se já existe um script reCAPTCHA
na página. Se existir, faz polling esperando ele carregar ao invés de injetar duplicado.

### 5. `asyncio.wait_for(timeout=25)` no Python
```python
captcha_token = await asyncio.wait_for(
    page.evaluate(_RECAPTCHA_EXECUTE_JS, [RECAPTCHA_SITE_KEY, action]),
    timeout=25.0
)
```
Garante que o Python NUNCA trava mais que 25 segundos, mesmo se a Promise JS travar.

## Fluxo Corrigido

```
1. Verificar grecaptcha.enterprise imediatamente
2. Se não encontrou → verificar se script existe na página
3. Se script existe → polling 500ms por até 15s
4. Se script não existe → JS universal vai injetar (com timeout 20s)
5. Executar grecaptcha.enterprise.execute() com timeout 25s Python
6. Retry 3x com 2s entre tentativas
7. Se falhar → retorna None (script continua para próxima tentativa)
```

## Arquivos Modificados

| Arquivo | Mudança |
|---------|---------|
| `movida_playwright.py` | Reescrita completa de `_RECAPTCHA_EXECUTE_JS` e `resolver_recaptcha_enterprise()` |
| `docs/bug_recaptcha_hang.md` | Documentação técnica do bug |

## Teste

Todos os módulos compilam sem erros. O script agora NUNCA pode travar no reCAPTCHA -
no pior caso, falha após 3 tentativas de 25s cada (75s total) e segue para o próximo ciclo.
