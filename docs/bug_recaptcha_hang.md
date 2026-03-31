# Bug: reCAPTCHA Enterprise Trava o Script

## Sintoma
O script trava em `[08:38:44.494] reCAPTCHA nao detectado, JS universal vai tentar injetar...`
e nunca mais avança. O Ctrl+C gera o ZIP mas o ciclo nunca completa.

## Causa Raiz

### 1. `wait_for_function` falha (30s timeout)
```python
await page.wait_for_function(
    "(typeof grecaptcha !== 'undefined' && typeof grecaptcha.execute === 'function') "
    "|| (typeof grecaptcha !== 'undefined' && typeof grecaptcha?.enterprise?.execute === 'function')",
    timeout=RECAPTCHA_TIMEOUT  # 30000ms
)
```
O reCAPTCHA Enterprise usa `grecaptcha.enterprise.execute`, NÃO `grecaptcha.execute`.
A verificação JS está errada - `grecaptcha?.enterprise?.execute` com optional chaining 
dentro de `typeof` não funciona como esperado no evaluate.

### 2. `page.evaluate(_RECAPTCHA_EXECUTE_JS)` trava indefinidamente
Quando `grecaptcha` não existe, o JS injeta o script via `document.head.appendChild(script)`.
Mas a Promise só resolve em `script.onload` ou rejeita em `script.onerror`.
**NÃO HÁ TIMEOUT INTERNO** - se o script nunca carregar (bloqueado, lento), a Promise fica pendente para sempre.
E `page.evaluate()` não tem timeout por padrão.

### 3. Sem `asyncio.wait_for()` envolvendo o evaluate
O código Python não envolve o `page.evaluate` com nenhum timeout, então trava o event loop.

## Solução

1. Corrigir a verificação JS para detectar `grecaptcha.enterprise` corretamente
2. Adicionar timeout interno na Promise JS (setTimeout de 15s)
3. Envolver `page.evaluate` com `asyncio.wait_for(timeout=20)` 
4. Verificar se o script já existe antes de injetar duplicado
5. Usar `page.wait_for_function` com verificação mais simples e robusta
6. Adicionar fallback: esperar o iframe do reCAPTCHA aparecer como sinal de carregamento
