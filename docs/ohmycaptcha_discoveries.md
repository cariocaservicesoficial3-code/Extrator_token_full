# Descobertas do OhMyCaptcha (shenhao-stu/ohmycaptcha)

## Técnicas Extraídas para Integração

### 1. JS Universal para reCAPTCHA v3/Enterprise
O `_EXECUTE_JS` do ohmycaptcha é mais robusto que o nosso:
- Detecta automaticamente `grecaptcha.enterprise` OU `grecaptcha` padrão
- Se o grecaptcha não está carregado, **injeta o script manualmente**
- Usa `window.grecaptcha?.enterprise || window.grecaptcha` (fallback automático)

### 2. Stealth JS Melhorado
- `navigator.webdriver = undefined`
- `navigator.languages = ['en-US', 'en']`
- `navigator.plugins = [1, 2, 3, 4, 5]` (NOVO - simula plugins reais)
- `window.chrome = {runtime: {}, loadTimes: () => {}, csi: () => {}}` (NOVO - simula Chrome real)

### 3. Simulação de Comportamento Humano
- **Mouse movement** antes de executar reCAPTCHA: `page.mouse.move(400, 300)` + sleep + `page.mouse.move(600, 400)`
- Isso melhora o score do reCAPTCHA v3 significativamente

### 4. Retry com Backoff
- 3 tentativas com `asyncio.sleep(2)` entre cada uma
- Validação: token deve ter `len > 20`

### 5. Script Injection Fallback
Se o grecaptcha não está na página, injeta:
```javascript
const script = document.createElement('script');
script.src = 'https://www.google.com/recaptcha/api.js?render=' + key;
document.head.appendChild(script);
```

### 6. Token Extraction (v2)
Múltiplas formas de extrair o token:
- `document.querySelector('#g-recaptcha-response')`
- `document.querySelector('[name="g-recaptcha-response"]')`
- `grecaptcha.getResponse()`

## O que vamos integrar no nosso script:
1. JS universal com fallback de injeção
2. Stealth JS melhorado com window.chrome
3. Mouse movement antes do reCAPTCHA
4. Retry robusto com validação
