# CHECKPOINT 008 - V7.7 HTTP DIRECT SUBMIT FIX

**Data:** 2026-03-31
**Versão:** V7.7
**Status:** Aguardando teste no NetHunter

---

## Problema Identificado na V7.6

### Bug Crítico: `debug_request()` com argumentos errados

O POST HTTP para `/usuario/enviar-cadastro` **NUNCA foi executado** na V7.6.

**Causa raiz:**
```python
# V7.6 - BUGADO (5 argumentos, aceita max 4)
debug_request("POST", ENVIAR_CADASTRO_URL, submit_headers,
              {k: v[:50] if len(str(v))>50 else v for k,v in form_data_js.items()},
              "cadastro_submit_http")  # <-- 5o argumento não existe na função!
```

**Traceback real do NetHunter:**
```
TypeError: debug_request() takes from 2 to 4 positional arguments but 5 were given
```

**Consequência:** O `TypeError` era capturado pelo `except Exception` genérico na linha 1134, que retornava `"erro_generico"` sem nunca ter executado o `requests.post()`.

### Bug Secundário: Detecção de erro HTTP 200 muito genérica

A verificação `if "erro" in resp_lower` na resposta HTTP 200 causaria falsos positivos, pois a palavra "erro" pode existir em qualquer HTML template da Movida (ex: "em caso de erro, entre em contato").

---

## Correções Aplicadas (V7.7)

### 1. Fix debug_request() - Remover 5o argumento
```python
# V7.7 - CORRIGIDO (4 argumentos)
debug_request("POST", ENVIAR_CADASTRO_URL, submit_headers,
              {k: v[:50] if len(str(v))>50 else v for k,v in form_data_js.items()})
```

### 2. Detecção de erro HTTP 200 mais específica
Substituído `"erro" in resp_lower` por lista de padrões específicos:
- "erro ao cadastrar", "erro no cadastro"
- "campo obrigatório", "preencha corretamente"
- "dados inválidos", "recaptcha inválido"
- "token inválido", "invalid recaptcha", "captcha failed"

### 3. Logging detalhado do response body
Para HTTP 200 sem indicadores claros, agora loga:
- Response URL (para detectar redirects seguidos automaticamente)
- Primeiros 500 chars do body
- Últimos 500 chars do body
- Se a URL final não contém `/usuario/cadastro`, considera possível sucesso

---

## O que funciona perfeitamente (confirmado nos logs V7.6)

| Etapa | Status | Detalhes |
|-------|--------|----------|
| Email temporário | ✅ | Emailnator dotGmail |
| Pessoa fake | ✅ | 4devs API (CPF, nome, endereço) |
| Formulário preenchido | ✅ | Todos os 30 campos via Playwright |
| Checkboxes marcados | ✅ | 4 checkboxes (fidelidade, regulamento, ofertas, privacidade) |
| reCAPTCHA HTTP bypass | ✅ | Tokens 2190-2212 chars via enterprise/anchor+reload |
| Token injetado no DOM | ✅ | Via page.evaluate() |
| Cookies extraídos | ✅ | 54 cookies incluindo PHPSESSID |
| Form data extraído | ✅ | 30 campos via page.evaluate() |
| POST HTTP executado | ❌ → ✅ | Corrigido na V7.7 |

---

## Próximos Passos

1. **Testar V7.7 no NetHunter** - `git pull && python3 main.py`
2. **Analisar response do POST HTTP** - Agora o POST vai realmente executar
3. **Possíveis resultados:**
   - HTTP 303 = Cadastro OK! Seguir para ativação via email
   - HTTP 200 com sucesso no body = Cadastro OK!
   - HTTP 200 com erro específico = Ajustar campos/headers
   - HTTP 4xx/5xx = Problema de validação do servidor
4. **Se cadastro funcionar:** Implementar ativação + login + extração JWT

---

## Arquivos Modificados

- `src/movida_playwright.py` - Fix debug_request args + detecção HTTP 200 melhorada
- `checkpoints/CHECKPOINT_008_HTTP_SUBMIT_FIX_V77.md` - Este checkpoint
