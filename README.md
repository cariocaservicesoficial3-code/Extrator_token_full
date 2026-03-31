# Ajato Token Generator V7.0 - Playwright Edition

Este projeto é um gerador automatizado de tokens para a plataforma Movida, refatorado completamente para utilizar **Playwright** e otimizado para rodar no **Kali Linux NetHunter**.

## 🚀 Novidades da V7.0

A versão 7.0 traz uma arquitetura totalmente nova baseada na análise de um fluxo real de cadastro (HAR) capturado com sucesso:

1. **Playwright Engine**: Substitui o uso de `requests` puros no cadastro/login por um navegador headless real (Chromium).
2. **reCAPTCHA Enterprise Bypass**: O reCAPTCHA agora é resolvido nativamente pelo navegador, gerando tokens válidos e aceitos pelo servidor.
3. **Fluxo Fiel ao Real**: O script agora simula exatamente o comportamento humano:
   - Preenche o CPF e aguarda a validação via API BFF.
   - Preenche o CEP e aguarda o auto-preenchimento do endereço.
   - Seleciona o estado e aguarda o carregamento dinâmico das cidades.
4. **Emailnator Híbrido**: O módulo de email temporário agora tenta usar `requests` por ser mais rápido, mas faz fallback automático para o Playwright caso detecte proteção do Cloudflare (Erro 403).
5. **Otimização NetHunter**: Argumentos específicos do Chromium para rodar sem problemas em ambientes ARM64/Android (Termux/NetHunter).

## 📁 Estrutura do Projeto

```text
Extrator_token_full/
├── src/
│   ├── main.py                 # Script principal (orquestrador)
│   ├── config.py               # Configurações centralizadas
│   ├── logger.py               # Sistema de logs coloridos e debug
│   ├── emailnator_module.py    # Gerenciador de emails temporários
│   ├── pessoa_generator.py     # Gerador de dados (4devs)
│   └── movida_playwright.py    # Core do Playwright (Cadastro/Login)
├── docs/
│   ├── analise_formulario_movida.md
│   └── har_discoveries.md      # Descobertas da análise do HAR
├── checkpoints/                # Histórico de evolução do projeto
├── install_nethunter.sh        # Script de instalação para NetHunter
└── requirements.txt            # Dependências Python
```

## 🛠️ Instalação no Kali NetHunter

Para instalar todas as dependências necessárias no seu Kali NetHunter, basta executar o script de instalação:

```bash
chmod +x install_nethunter.sh
./install_nethunter.sh
```

## 🏃‍♂️ Como Executar

Após a instalação, navegue até a pasta `src` e execute o script principal:

```bash
cd src
python3 main.py
```

## 📝 Sistema de Checkpoints

Este projeto utiliza um sistema de **Checkpoints** para manter o histórico de evolução e contexto. Sempre que uma nova sessão for iniciada, a IA pode ler a pasta `checkpoints/` para entender exatamente o que já foi feito, quais problemas foram resolvidos e qual é a arquitetura atual.

---
*Desenvolvido com 🔥 e ⚡ para máxima performance.*
