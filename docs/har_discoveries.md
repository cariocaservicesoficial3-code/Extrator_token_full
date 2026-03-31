# Descobertas Críticas do HAR - Cadastro com Sucesso

## Fluxo Cronológico Real (do HAR)

1. **GET /usuario/cadastro** - Carrega página e obtém PHPSESSID
2. **GET recaptcha/enterprise/anchor** - Carrega reCAPTCHA Enterprise
3. **POST bff-b2c/api/v2/customer/data/register/validate** - Valida CPF (AJAX)
4. **GET /busca_cep/{cep}** - Auto-preenche endereço pelo CEP
5. **POST /cep/lista-estado-cidades** - Carrega lista de cidades do estado
6. **POST recaptcha/enterprise/reload** - Resolve reCAPTCHA (gera token)
7. **POST /usuario/enviar-cadastro** - Envia formulário (HTTP 303 = sucesso!)
8. **GET /usuario/cadastro** - Redirect de volta com mensagem de sucesso

## Campos Exatos do POST enviar-cadastro (que deu 303)

| Campo | Valor Exemplo |
|-------|--------------|
| g-recaptcha-response | [token longo do enterprise] |
| isLoginSocial | (vazio) |
| requester | (vazio) |
| tokenRequester | (vazio) |
| partnership | (vazio) |
| user_token | (vazio) |
| nationality | Brasileiro |
| nacionalidade | 2 |
| cpf | 134.750.166-56 (COM pontuação) |
| nome | Carlos Eduardo |
| IDNacionalidade | 1007 |
| data_nasc | 04/02/1965 |
| telefone | (19) 9928-9225 |
| celular | (19) 99289-2251 |
| email | carlos_eduardo_darosa@gmail.com |
| email_conf | carlos_eduardo_darosa@gmail.com |
| cep | 13613-240 (COM hífen) |
| logradouro | Sylvio Zapacosta |
| numero | 409 |
| complemento | (vazio) |
| bairro | Jardim Portal do Bosque |
| Pais | 1 |
| uf | SP |
| cidade | 3526704 (código IBGE) |
| senha_cadastro | F#4R40el3Q |
| senha_conf | F#4R40el3Q |
| ofertasFidelidade | 1 |
| politicaPrivacidade | on |

## Diferenças Críticas vs Script V6.1

1. **NÃO tem participarFidelidade=1** - O HAR real NÃO envia esse campo!
2. **NÃO tem regulamentoFidelidade=1** - O HAR real NÃO envia esse campo!
3. **Tem user_token** (vazio) - Campo hidden que o script V6.1 não envia
4. **reCAPTCHA Enterprise** - Token gerado pelo browser real via enterprise/reload
5. **Validação de CPF via BFF** - Chamada AJAX antes do cadastro
6. **Busca CEP** - Auto-preenchimento via API antes do submit

## User-Agent Real

```
Mozilla/5.0 (Linux; Android 11; M2012K11AG Build/RQ3A.211001.001) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/147.0.7727.24 Mobile Safari/537.36
```

## Headers Críticos

- `x-requested-with: com.netsky.vfat.pro` (WebView do app)
- `sec-ch-ua: "Android WebView";v="147", "Not.A/Brand";v="8", "Chromium";v="147"`
- `sec-fetch-site: same-origin`
- `sec-fetch-mode: navigate`
- `sec-fetch-dest: document`

## Conclusão

O problema principal do script V6.1 é que o reCAPTCHA Enterprise precisa ser resolvido por um browser real. O bypass via HTTP requests gera tokens inválidos. Com Playwright, o browser real resolve o reCAPTCHA automaticamente.
