# Bug V7.3: reCAPTCHA Enterprise NÃO CARREGA no Chromium Headless

## Sintoma
O script do reCAPTCHA está presente na página (`recaptcha__pt_br.js` e `recaptcha/releases/...`)
mas o objeto `grecaptcha.enterprise.execute` NUNCA fica disponível.

## Evidências dos Logs
```
[09:06:43.114] Script reCAPTCHA encontrado: https://www.gstatic.com/recaptcha/releases/79clEdOi5xQbrrpL2L8kGmK3/recaptcha__pt_br.js
[09:06:58.915] reCAPTCHA nao carregou, JS universal vai injetar o script...
[09:07:13.954] reCAPTCHA tentativa 1/3 falhou: reCAPTCHA script existe mas nunca carregou (15s polling)
```

## Causa Raiz
O Google reCAPTCHA Enterprise detecta o Chromium headless e **se recusa a inicializar**.
O script JS carrega (o `<script>` tag existe) mas o `grecaptcha.enterprise` object nunca é criado.

Isso acontece porque:
1. O reCAPTCHA verifica `navigator.webdriver` (que é `true` no headless)
2. O reCAPTCHA verifica o user-agent e fingerprint do browser
3. O stealth JS pode não estar sendo injetado ANTES do reCAPTCHA carregar

## Solução: Abordagem Híbrida

### Opção A: Usar headed mode (não headless)
- `headless=False` no Playwright
- No NetHunter com Termux/VNC isso funciona
- Mais confiável mas precisa de display

### Opção B: Resolver reCAPTCHA via HTTP (como o V6.1 fazia)
- O script V6.1 original resolvia o reCAPTCHA via HTTP requests diretos
- GET anchor -> POST reload -> extrair token
- Isso funciona porque não depende do browser
- Podemos fazer isso em paralelo ao Playwright

### Opção C (MELHOR): Abordagem híbrida
1. Preencher formulário via Playwright (já funciona perfeitamente!)
2. Resolver reCAPTCHA via HTTP requests (bypass do headless detection)
3. Injetar o token no formulário via Playwright
4. Submeter via Playwright

Essa abordagem combina o melhor dos dois mundos:
- Playwright para interação com formulário (simula humano)
- HTTP requests para reCAPTCHA (evita detecção headless)
