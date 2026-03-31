# Ajato Token Generator V7.2 - Playwright + OhMyCaptcha

Este projeto é um gerador automatizado de tokens para a plataforma Movida, refatorado completamente para utilizar **Playwright** e otimizado para rodar no **Kali Linux NetHunter**.

## 🚀 Novidades da V7.2

### Integração OhMyCaptcha
Técnicas avançadas do [ohmycaptcha](https://github.com/shenhao-stu/ohmycaptcha) integradas:
- **JS Universal**: Detecta `grecaptcha.enterprise` ou `grecaptcha` automaticamente + injeta script se ausente
- **Stealth JS Melhorado**: `navigator.webdriver=undefined`, `window.chrome` fake, `navigator.plugins` simulados
- **Mouse Humano**: Movimentos aleatórios antes do reCAPTCHA para melhorar score
- **Retry 3x**: Com validação de token (`len > 20`)

### Sistema de Debug Logs Completo
- Logs detalhados em `/sdcard/nh_files/logs/`
- **ZIP automático por ciclo** (logs + screenshots)
- **ZIP de sessão completa** ao encerrar (Ctrl+C)
- Debug de Playwright: navegação, cliques, HTML, JS eval, erros
- Debug HTTP: requests/responses detalhados

### Correções de Bugs
- Timeout no `page.goto` → `wait_until="domcontentloaded"` + timeout 60s
- Timeout no click de radio/checkbox → `safe_click()` com scroll + force + JS fallback
- Preenchimento de campos → `safe_fill()` com scroll + type simulado

## 📁 Estrutura do Projeto

```text
Extrator_token_full/
├── src/
│   ├── main.py                 # Script principal (orquestrador)
│   ├── config.py               # Configurações centralizadas
│   ├── logger.py               # Sistema de logs + ZIP
│   ├── emailnator_module.py    # Gerenciador de emails temporários
│   ├── pessoa_generator.py     # Gerador de dados (4devs)
│   └── movida_playwright.py    # Core Playwright + OhMyCaptcha
├── docs/
│   ├── analise_formulario_movida.md
│   ├── har_discoveries.md
│   └── ohmycaptcha_discoveries.md
├── checkpoints/                # Histórico de evolução do projeto
├── install_nethunter.sh        # Script de instalação para NetHunter
└── requirements.txt            # Dependências Python
```

## 📋 Logs Gerados

| Arquivo | Conteúdo |
|---------|----------|
| `DEBUG_LOGS_GEN_TOKENS.txt` | Log principal (tudo) |
| `PLAYWRIGHT_DEBUG.txt` | Ações do Playwright |
| `HTTP_REQUESTS.txt` | Requests/Responses HTTP |
| `CYCLE_HISTORY.txt` | Histórico de ciclos |
| `screenshots/` | Screenshots de debug |
| `ciclo_NNN_*.zip` | ZIP por ciclo |
| `sessao_completa_*.zip` | ZIP da sessão |

## 🛠️ Instalação no Kali NetHunter

```bash
chmod +x install_nethunter.sh
./install_nethunter.sh
```

## 🏃‍♂️ Como Executar

```bash
cd src
python3 main.py
```

## 📝 Sistema de Checkpoints

Este projeto utiliza um sistema de **Checkpoints** para manter o histórico de evolução e contexto. Sempre que uma nova sessão for iniciada, a IA pode ler a pasta `checkpoints/` para entender exatamente o que já foi feito, quais problemas foram resolvidos e qual é a arquitetura atual.

### Checkpoints Disponíveis:
- **001**: Análise inicial do script V6.1 + diagnóstico dos problemas
- **002**: Refatoração completa com Playwright + descobertas do HAR
- **003**: Integração OhMyCaptcha + Sistema de Logs/ZIP + Correções

---
*Desenvolvido com 🔥 e ⚡ para máxima performance.*
