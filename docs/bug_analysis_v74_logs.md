# Análise de Bugs V7.4 - Logs do NetHunter

## Data: 2026-03-31

## Problemas Identificados

### 1. PRINCIPAL: "Documento já cadastrado" (CPF já existe)
- O reCAPTCHA HTTP bypass FUNCIONA (2190-2233 chars)
- O token é injetado no DOM com sucesso
- O formulário é submetido (click #btnEnviaDados)
- MAS o site retorna "Documento já cadastrado"
- O script usa o MESMO CPF nas 3 tentativas (não gera novo)
- SOLUÇÃO: Quando detectar "Documento já cadastrado", gerar NOVO CPF+dados e tentar novamente

### 2. SECUNDÁRIO: Erro HTML captura template strings
- Os erros capturados incluem template JS: `' + getErroValidacaoLabel() + '`
- Isso é porque o script está lendo o HTML bruto que contém templates Angular/JS
- O erro REAL é: "Documento ja cadastrado."
- SOLUÇÃO: Filtrar erros que são templates JS (contêm `getErro` ou `response.msg`)

### 3. SECUNDÁRIO: Timeout 60s no submit
- `Navigation apos submit: Timeout 60000ms exceeded`
- O submit NÃO navega para outra página (é AJAX), então o wait_for_navigation sempre dá timeout
- Isso desperdiça 60s por tentativa
- SOLUÇÃO: Ao invés de esperar navegação, esperar resposta AJAX (interceptar response ou esperar elemento de erro/sucesso)

### 4. SECUNDÁRIO: Mesmo CPF em todas as tentativas
- Tentativas 1, 2 e 3 usam o mesmo CPF 247.666.188-07
- Se o CPF já existe, tentar com o mesmo CPF é inútil
- SOLUÇÃO: Gerar novo CPF a cada tentativa quando o erro for "Documento já cadastrado"

### 5. MENOR: #brasileiro click fora do viewport
- Sempre falha no click normal, cai no JS click fallback
- Funciona via fallback, mas gera warning desnecessário
- SOLUÇÃO: Scroll para o topo antes de clicar no radio

## Prioridades de Correção
1. Gerar NOVO CPF quando "Documento já cadastrado" (CRÍTICO)
2. Substituir wait_for_navigation por espera de resposta AJAX (PERFORMANCE)
3. Filtrar template strings nos erros (QUALIDADE)
4. Fix scroll para #brasileiro (MENOR)
