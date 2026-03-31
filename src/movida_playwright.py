#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AJATO TOKEN GENERATOR V7.0 - Módulo Movida Playwright
Cadastro, ativação e login via Playwright (navegador headless real).

BASEADO NO HAR REAL DE CADASTRO BEM-SUCEDIDO:
  Fluxo: GET cadastro -> validate CPF -> busca_cep -> lista-estado-cidades
         -> reCAPTCHA enterprise/reload -> POST enviar-cadastro (HTTP 303)
"""

import re
import os
import json
import time
import asyncio
import traceback
import requests
from datetime import datetime
from urllib.parse import urlencode

from config import (
    MOVIDA_BASE, BFF_BASE, CADASTRO_URL, LOGIN_URL,
    ENVIAR_CADASTRO_URL, LOGIN_SITE_URL,
    RECAPTCHA_SITE_KEY, USER_AGENT_WEBVIEW,
    CHROMIUM_ARGS, VIEWPORT, SCREENSHOTS_DIR,
    PAGE_LOAD_TIMEOUT, NAVIGATION_TIMEOUT,
    ACTIVATION_DELAY, MAX_LOGIN_RETRIES,
)
from logger import log, debug_event, debug_error, debug_write, STATS
from pessoa_generator import get_cidade_ibge


async def criar_browser(playwright):
    """Cria instância do browser Playwright otimizada para NetHunter."""
    log("PW", "Iniciando Chromium headless...")

    browser = await playwright.chromium.launch(
        headless=True,
        args=CHROMIUM_ARGS,
    )

    context = await browser.new_context(
        viewport=VIEWPORT,
        user_agent=USER_AGENT_WEBVIEW,
        locale="pt-BR",
        timezone_id="America/Sao_Paulo",
        java_script_enabled=True,
        extra_http_headers={
            "X-Requested-With": "com.netsky.vfat.pro",
        },
    )

    # Anti-detecção: remover webdriver flag
    await context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en']});
        Object.defineProperty(navigator, 'platform', {get: () => 'Linux armv8l'});

        // Override permissions
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );

        // Remove automation indicators
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
        delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
    """)

    log("OK", "Browser Chromium iniciado com sucesso!")
    return browser, context


async def screenshot_debug(page, name):
    """Salva screenshot para debug."""
    try:
        ts = datetime.now().strftime("%H%M%S")
        path = os.path.join(SCREENSHOTS_DIR, f"{ts}_{name}.png")
        await page.screenshot(path=path, full_page=False)
        log("DEBUG", f"Screenshot salvo: {name}")
        return path
    except Exception:
        return None


# ==============================================================================
# CADASTRO VIA PLAYWRIGHT
# ==============================================================================

async def fazer_cadastro_playwright(context, pessoa, email, senha):
    """
    Realiza cadastro na Movida usando Playwright.
    Simula interação humana real no formulário.
    Fluxo baseado no HAR real que deu HTTP 303 (sucesso).
    """
    page = await context.new_page()
    page.set_default_timeout(PAGE_LOAD_TIMEOUT)
    page.set_default_navigation_timeout(NAVIGATION_TIMEOUT)

    cpf_formatado = pessoa["cpf"]
    cpf_numeros = re.sub(r'\D', '', cpf_formatado)
    cep_raw = pessoa.get("cep", "01001-000")
    cep_numeros = re.sub(r'\D', '', cep_raw)

    try:
        # =============================================
        # PASSO 1: Carregar página de cadastro
        # =============================================
        log("STEP", "PASSO 4: Carregando pagina de cadastro...")
        await page.goto(CADASTRO_URL, wait_until="networkidle", timeout=NAVIGATION_TIMEOUT)
        await page.wait_for_selector("#formCadastro", timeout=15000)
        log("OK", "Pagina de cadastro carregada!")

        await screenshot_debug(page, "01_cadastro_loaded")

        # Aguardar reCAPTCHA Enterprise carregar
        await page.wait_for_function(
            "typeof grecaptcha !== 'undefined' && typeof grecaptcha.enterprise !== 'undefined'",
            timeout=15000
        )
        log("OK", "reCAPTCHA Enterprise carregado!")

        # =============================================
        # PASSO 2: Preencher Informações Pessoais
        # =============================================
        log("STEP", "PASSO 5: Preenchendo formulario de cadastro...")

        # Selecionar "Brasileiro"
        brasileiro_radio = page.locator("#brasileiro")
        if await brasileiro_radio.count() > 0:
            await brasileiro_radio.click()
            await asyncio.sleep(0.3)

        # CPF
        await page.locator("#cpf").click()
        await page.locator("#cpf").fill("")
        await page.locator("#cpf").type(cpf_formatado, delay=random_delay())
        await asyncio.sleep(0.5)

        # Trigger blur para validação de CPF (dispara AJAX validate)
        await page.locator("#cpf").evaluate("el => el.dispatchEvent(new Event('blur'))")
        log("DEBUG", f"CPF preenchido: {cpf_formatado}")

        # Aguardar validação AJAX do CPF
        await asyncio.sleep(1.5)

        # Nome
        await page.locator("#nome").click()
        await page.locator("#nome").type(pessoa["nome"], delay=random_delay())
        await asyncio.sleep(0.3)

        # Data de Nascimento
        await page.locator("#data_nasc").click()
        await page.locator("#data_nasc").type(pessoa["data_nasc"], delay=random_delay())
        await asyncio.sleep(0.3)

        # Telefone (opcional mas preenchemos)
        telefone = pessoa.get("telefone_fixo", "")
        if telefone:
            await page.locator("#telefone").click()
            await page.locator("#telefone").type(telefone, delay=random_delay())
            await asyncio.sleep(0.2)

        # Celular
        celular = pessoa.get("celular", "(11) 99999-9999")
        await page.locator("#celular").click()
        await page.locator("#celular").type(celular, delay=random_delay())
        await asyncio.sleep(0.3)

        # Email
        await page.locator("#email").click()
        await page.locator("#email").type(email, delay=random_delay())
        await asyncio.sleep(0.3)

        # Confirmação Email
        await page.locator("#email_conf").click()
        await page.locator("#email_conf").type(email, delay=random_delay())
        await asyncio.sleep(0.3)

        log("OK", "Informacoes pessoais preenchidas!")
        await screenshot_debug(page, "02_pessoais_ok")

        # =============================================
        # PASSO 3: Preencher Endereço
        # =============================================
        log("STEP", "Preenchendo endereco...")

        # CEP (dispara busca automática)
        await page.locator("#cep").click()
        await page.locator("#cep").fill("")
        await page.locator("#cep").type(cep_raw, delay=random_delay())
        await page.locator("#cep").evaluate("el => el.dispatchEvent(new Event('blur'))")
        log("DEBUG", f"CEP preenchido: {cep_raw}")

        # Aguardar auto-preenchimento do CEP (AJAX busca_cep)
        await asyncio.sleep(2.0)

        # Verificar se logradouro foi auto-preenchido
        logradouro_val = await page.locator("#logradouro").input_value()
        if not logradouro_val:
            # Preencher manualmente se auto-preenchimento falhou
            log("WARN", "Auto-preenchimento do CEP falhou, preenchendo manualmente...")
            await page.locator("#logradouro").fill(pessoa.get("endereco", "Rua Exemplo"))
            await page.locator("#bairro").fill(pessoa.get("bairro", "Centro"))
        else:
            log("OK", f"CEP auto-preencheu: {logradouro_val}")

        # Número
        await page.locator("#numero").click()
        await page.locator("#numero").type(str(pessoa.get("numero", "100")), delay=random_delay())
        await asyncio.sleep(0.3)

        # País (Brasil = value "1")
        pais_select = page.locator("#Pais")
        if await pais_select.count() > 0:
            await pais_select.select_option(value="1")
            await asyncio.sleep(0.3)

        # Estado
        uf_select = page.locator("#uf_sel")
        if await uf_select.count() > 0:
            estado = pessoa.get("estado", "SP")
            await uf_select.select_option(value=estado)
            await asyncio.sleep(1.0)  # Aguardar carregamento das cidades

        # Cidade (código IBGE)
        cidade_select = page.locator("#cidade_sel")
        if await cidade_select.count() > 0:
            cidade_ibge = get_cidade_ibge(pessoa.get("cidade", ""))
            try:
                await cidade_select.select_option(value=cidade_ibge)
            except Exception:
                # Tentar pelo texto da cidade
                cidade_nome = pessoa.get("cidade", "").upper()
                try:
                    await cidade_select.select_option(label=cidade_nome)
                except Exception:
                    log("WARN", f"Nao conseguiu selecionar cidade: {cidade_nome}")
            await asyncio.sleep(0.3)

        log("OK", "Endereco preenchido!")
        await screenshot_debug(page, "03_endereco_ok")

        # =============================================
        # PASSO 4: Preencher Senha
        # =============================================
        log("STEP", "Preenchendo senha...")

        await page.locator("#senha_cadastro").click()
        await page.locator("#senha_cadastro").type(senha, delay=random_delay())
        await asyncio.sleep(0.3)

        await page.locator("#senha_conf").click()
        await page.locator("#senha_conf").type(senha, delay=random_delay())
        await asyncio.sleep(0.3)

        log("OK", f"Senha preenchida: {senha}")

        # =============================================
        # PASSO 5: Checkboxes (conforme HAR real)
        # =============================================
        log("STEP", "Marcando checkboxes...")

        # ofertasFidelidade
        ofertas_cb = page.locator("#ofertasFidelidade")
        if await ofertas_cb.count() > 0:
            is_checked = await ofertas_cb.is_checked()
            if not is_checked:
                await ofertas_cb.click(force=True)
                await asyncio.sleep(0.2)

        # politicaPrivacidade
        politica_cb = page.locator("#politicaPrivacidade")
        if await politica_cb.count() > 0:
            is_checked = await politica_cb.is_checked()
            if not is_checked:
                await politica_cb.click(force=True)
                await asyncio.sleep(0.2)

        # participarFidelidade (marcar se existir)
        participar_cb = page.locator("#participarFidelidade")
        if await participar_cb.count() > 0:
            is_checked = await participar_cb.is_checked()
            if not is_checked:
                await participar_cb.click(force=True)
                await asyncio.sleep(0.2)

        # regulamentoFidelidade (marcar se existir)
        regulamento_cb = page.locator("#regulamentoFidelidade")
        if await regulamento_cb.count() > 0:
            is_checked = await regulamento_cb.is_checked()
            if not is_checked:
                await regulamento_cb.click(force=True)
                await asyncio.sleep(0.2)

        log("OK", "Checkboxes marcados!")
        await screenshot_debug(page, "04_checkboxes_ok")

        # =============================================
        # PASSO 6: Resolver reCAPTCHA Enterprise e Enviar
        # =============================================
        log("CAPTCHA", "Executando reCAPTCHA Enterprise via browser...")

        # Executar grecaptcha.enterprise.execute() no contexto do browser
        # Isso gera um token REAL que o servidor aceita
        captcha_token = await page.evaluate("""
            () => {
                return new Promise((resolve, reject) => {
                    try {
                        grecaptcha.enterprise.ready(() => {
                            grecaptcha.enterprise.execute(
                                '""" + RECAPTCHA_SITE_KEY + """',
                                {action: 'signup'}
                            ).then(token => {
                                resolve(token);
                            }).catch(err => {
                                reject(err.toString());
                            });
                        });
                    } catch(e) {
                        reject(e.toString());
                    }
                });
            }
        """)

        if not captcha_token or len(captcha_token) < 50:
            log("FAIL", f"reCAPTCHA Enterprise falhou! Token: {captcha_token}")
            await screenshot_debug(page, "05_captcha_fail")
            await page.close()
            return False

        log("OK", f"reCAPTCHA Enterprise RESOLVIDO! ({len(captcha_token)} chars)")
        debug_event("reCAPTCHA Enterprise token", f"{len(captcha_token)} chars")

        # Injetar token no formulário (campo hidden g-recaptcha-response)
        await page.evaluate(f"""
            () => {{
                // Criar ou atualizar campo hidden g-recaptcha-response
                let existing = document.querySelector('input[name="g-recaptcha-response"]') ||
                               document.querySelector('textarea[name="g-recaptcha-response"]');
                if (!existing) {{
                    existing = document.createElement('input');
                    existing.type = 'hidden';
                    existing.name = 'g-recaptcha-response';
                    document.getElementById('formCadastro').appendChild(existing);
                }}
                existing.value = `{captcha_token}`;
            }}
        """)

        log("OK", "Token reCAPTCHA injetado no formulario!")

        # =============================================
        # PASSO 7: Clicar em ENVIAR
        # =============================================
        log("STEP", "PASSO 6: Enviando cadastro...")

        await screenshot_debug(page, "05_pre_submit")

        # Interceptar a resposta do POST
        async with page.expect_navigation(
            wait_until="networkidle",
            timeout=30000
        ) as navigation:
            await page.locator("#btnEnviaDados").click()

        # Verificar resultado
        await asyncio.sleep(2)
        current_url = page.url
        page_content = await page.content()

        await screenshot_debug(page, "06_post_submit")

        # Verificar sucesso
        if "Cadastro efetuado com sucesso" in page_content:
            log("OK", "CADASTRO EFETUADO COM SUCESSO! (mensagem detectada)")
            STATS["cadastros_ok"] += 1
            await page.close()
            return True

        if "Bem vindo a Movida" in page_content or "Bem-vindo" in page_content:
            log("OK", "CADASTRO EFETUADO COM SUCESSO! (boas-vindas detectada)")
            STATS["cadastros_ok"] += 1
            await page.close()
            return True

        if "receber um e-mail para confirmar" in page_content.lower():
            log("OK", "CADASTRO EFETUADO COM SUCESSO! (confirmação email detectada)")
            STATS["cadastros_ok"] += 1
            await page.close()
            return True

        # Verificar se ainda está no formulário (falha)
        if 'name="senha_cadastro"' in page_content or 'id="formCadastro"' in page_content:
            # Verificar se tem mensagem de erro
            error_msgs = re.findall(
                r'(?:toastr\[.*?\]|toastr\.(?:error|warning))\s*\(\s*["\']([^"\']+)',
                page_content
            )
            if error_msgs:
                for msg in error_msgs:
                    log("FAIL", f"  Erro JS: {msg[:200]}")
            else:
                # Verificar mensagens de erro no HTML
                errors = re.findall(
                    r'class="[^"]*(?:error|alert-danger|text-danger)[^"]*"[^>]*>(.*?)<',
                    page_content, re.IGNORECASE
                )
                for err in errors:
                    clean = re.sub(r'<[^>]+>', '', err).strip()
                    if clean:
                        log("FAIL", f"  Erro HTML: {clean[:200]}")

            log("FAIL", "Cadastro FALHOU - formulario retornado")
            await page.close()
            return False

        # Se a URL mudou, provavelmente deu certo
        if current_url != CADASTRO_URL:
            log("OK", f"Cadastro enviado! URL mudou para: {current_url[:80]}")
            STATS["cadastros_ok"] += 1
            await page.close()
            return True

        log("WARN", "Resultado do cadastro incerto, assumindo sucesso...")
        STATS["cadastros_ok"] += 1
        await page.close()
        return True

    except Exception as e:
        log("FAIL", f"Erro no cadastro Playwright: {str(e)}")
        debug_error(f"Cadastro Playwright: {str(e)}", traceback.format_exc())
        await screenshot_debug(page, "error_cadastro")
        try:
            await page.close()
        except Exception:
            pass
        return False


# ==============================================================================
# ATIVAÇÃO DE CONTA VIA PLAYWRIGHT
# ==============================================================================

async def ativar_conta_playwright(context, confirmation_link, senha):
    """Ativa a conta seguindo o link de confirmação via Playwright."""
    log("STEP", "PASSO 7: Ativando conta via link de confirmacao...")
    debug_event("Ativacao iniciada", f"Link: {confirmation_link}")

    page = await context.new_page()
    page.set_default_timeout(PAGE_LOAD_TIMEOUT)

    try:
        # Seguir o link de confirmação (pode ser SendGrid redirect)
        log("DEBUG", f"Navegando para link de confirmacao...")
        await page.goto(confirmation_link, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(2)

        final_url = page.url
        log("OK", f"URL final: {final_url[:100]}...")
        await screenshot_debug(page, "07_ativacao_page")

        page_content = await page.content()

        # Extrair PessoaID
        pessoa_id = None
        id_match = re.search(r'[?&]id=(\d+)', final_url)
        if id_match:
            pessoa_id = id_match.group(1)
            log("OK", f"PessoaID extraido da URL: {pessoa_id}")

        if not pessoa_id:
            id_patterns = [
                r'name=["\']pessoaId["\'].*?value=["\'](\d+)["\']',
                r'value=["\'](\d+)["\'].*?name=["\']pessoaId["\']',
                r'pessoaId["\s:=]+["\']?(\d+)',
                r'/confirma_cadastro/?\?id=(\d+)',
            ]
            for pattern in id_patterns:
                match = re.search(pattern, page_content, re.IGNORECASE)
                if match:
                    pessoa_id = match.group(1)
                    log("OK", f"PessoaID extraido do HTML: {pessoa_id}")
                    break

        # Verificar se tem formulário de senha na página
        has_password_form = 'name="senha"' in page_content or 'confirmar_senha' in page_content

        if has_password_form and pessoa_id:
            log("STEP", "PASSO 8: Definindo senha via formulario...")

            # Preencher senha via Playwright
            senha_field = page.locator('input[name="senha"], input[id="senha"]').first
            if await senha_field.count() > 0:
                await senha_field.fill(senha)
                await asyncio.sleep(0.3)

            confirma_field = page.locator('input[name="confirmar_senha"], input[id="confirmar_senha"]').first
            if await confirma_field.count() > 0:
                await confirma_field.fill(senha)
                await asyncio.sleep(0.3)

            # Submeter
            submit_btn = page.locator('button[type="submit"], input[type="submit"]').first
            if await submit_btn.count() > 0:
                await submit_btn.click()
                await asyncio.sleep(2)

            log("OK", "Senha definida via formulario!")
            STATS["ativacoes_ok"] += 1
            await page.close()
            return True

        elif pessoa_id:
            # POST atualizar-senha via API (fallback)
            log("STEP", "PASSO 8: Definindo senha via API atualizar-senha...")
            session = requests.Session()
            session.headers.update({"User-Agent": USER_AGENT_WEBVIEW})

            # Copiar cookies do Playwright para requests
            cookies = await context.cookies()
            for cookie in cookies:
                session.cookies.set(cookie["name"], cookie["value"], domain=cookie.get("domain", ""))

            atualizar_url = f"{MOVIDA_BASE}/usuario/atualizar-senha"
            atualizar_data = {
                "pessoaId": pessoa_id,
                "senha": senha,
                "confirmar_senha": senha,
            }
            atualizar_headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Origin": MOVIDA_BASE,
                "Referer": final_url,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
            }

            resp = session.post(atualizar_url, data=atualizar_data, headers=atualizar_headers, timeout=15)
            log("API", f"atualizar-senha -> HTTP {resp.status_code}", resp.text[:300])

            if resp.status_code == 200:
                try:
                    data = resp.json()
                    if data.get("success"):
                        log("OK", "Senha definida com sucesso! Conta ATIVADA!")
                        STATS["ativacoes_ok"] += 1
                        await page.close()
                        return True
                    else:
                        msg = data.get("msg", "?")
                        log("WARN", f"atualizar-senha: {msg}")
                        if "já" in msg.lower() or "already" in msg.lower():
                            log("OK", "Conta ja estava ativada!")
                            STATS["ativacoes_ok"] += 1
                            await page.close()
                            return True
                except json.JSONDecodeError:
                    pass

        # Se chegou aqui, verificar se a página indica sucesso
        if any(x in page_content.lower() for x in ["sucesso", "ativada", "confirmada", "login"]):
            log("OK", "Ativacao aparentemente OK!")
            STATS["ativacoes_ok"] += 1
            await page.close()
            return True

        log("WARN", "Ativacao incerta, tentando login mesmo assim...")
        STATS["ativacoes_fail"] += 1
        await page.close()
        return True  # Retorna True para tentar login

    except Exception as e:
        log("FAIL", f"Erro na ativacao: {str(e)}")
        debug_error(f"Ativacao: {str(e)}", traceback.format_exc())
        try:
            await page.close()
        except Exception:
            pass
        STATS["ativacoes_fail"] += 1
        return False


# ==============================================================================
# LOGIN VIA PLAYWRIGHT
# ==============================================================================

async def fazer_login_playwright(context, cpf_numeros, senha):
    """Realiza login na Movida via Playwright."""
    log("STEP", "PASSO 9: Fazendo login na Movida...")

    page = await context.new_page()
    page.set_default_timeout(PAGE_LOAD_TIMEOUT)

    try:
        # Carregar página de login
        await page.goto(LOGIN_URL, wait_until="networkidle", timeout=NAVIGATION_TIMEOUT)
        await asyncio.sleep(2)

        await screenshot_debug(page, "08_login_page")

        # Preencher CPF
        cpf_input = page.locator('input[placeholder="CPF"], input#mat-input-0, input[formcontrolname="cpf"]').first
        await cpf_input.click()
        await cpf_input.fill("")
        await cpf_input.type(cpf_numeros, delay=random_delay())
        await asyncio.sleep(0.5)

        # Preencher Senha
        senha_input = page.locator('input[placeholder="Senha"], input#mat-input-1, input[formcontrolname="senha"]').first
        await senha_input.click()
        await senha_input.fill("")
        await senha_input.type(senha, delay=random_delay())
        await asyncio.sleep(0.5)

        await screenshot_debug(page, "09_login_filled")

        # Resolver reCAPTCHA se necessário
        has_recaptcha = await page.evaluate("""
            () => typeof grecaptcha !== 'undefined' && typeof grecaptcha.enterprise !== 'undefined'
        """)

        captcha_token = None
        if has_recaptcha:
            log("CAPTCHA", "Resolvendo reCAPTCHA Enterprise para login...")
            try:
                captcha_token = await page.evaluate("""
                    () => {
                        return new Promise((resolve, reject) => {
                            grecaptcha.enterprise.ready(() => {
                                grecaptcha.enterprise.execute(
                                    '""" + RECAPTCHA_SITE_KEY + """',
                                    {action: 'login'}
                                ).then(token => resolve(token))
                                .catch(err => reject(err.toString()));
                            });
                        });
                    }
                """)
                if captcha_token and len(captcha_token) > 50:
                    log("OK", f"reCAPTCHA login resolvido! ({len(captcha_token)} chars)")
            except Exception as e:
                log("WARN", f"reCAPTCHA login falhou: {str(e)}")

        # Clicar em Entrar
        login_btn = page.locator('button:has-text("Entrar")').first
        
        # Interceptar resposta de login
        response_promise = page.wait_for_response(
            lambda r: "login_site" in r.url or "login" in r.url,
            timeout=15000
        )

        await login_btn.click()
        
        try:
            response = await response_promise
            resp_text = await response.text()
            resp_status = response.status
            
            log("API", f"login -> HTTP {resp_status}", resp_text[:300])

            if resp_status == 200:
                try:
                    data = json.loads(resp_text)
                    if data.get("success"):
                        user_token = data.get("token", "")
                        user_id = data.get("user_id", "")
                        nome = data.get("nome", "")
                        log("OK", f"Login OK! Nome: {nome}, UserID: {user_id}")
                        log("TOKEN", f"USER-TOKEN: {user_token}")

                        if user_token and len(user_token) > 10:
                            STATS["logins_ok"] += 1
                            await page.close()
                            return user_token, "ok"

                        # Tentar webcheckin/token
                        wc_token = await extrair_token_webcheckin(context, data.get("token", ""))
                        if wc_token:
                            STATS["logins_ok"] += 1
                            await page.close()
                            return wc_token, "ok"

                        STATS["logins_ok"] += 1
                        await page.close()
                        return user_token or "LOGIN_OK_NO_TOKEN", "ok"
                    else:
                        msg = data.get("msg", "").lower()
                        log("WARN", f"Login falhou: {data.get('msg', '?')}")

                        if "confirmado" in msg or "confirmar" in msg:
                            await page.close()
                            return None, "nao_confirmado"
                        if "senha" in msg or "inválido" in msg or "invalido" in msg:
                            await page.close()
                            return None, "senha_invalida"
                        if "complete" in msg:
                            await page.close()
                            return None, "incomplete_data"
                        await page.close()
                        return None, "unknown_error"
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            log("DEBUG", f"Timeout esperando resposta de login: {str(e)}")

        # Fallback: verificar se a página mudou (login via redirect)
        await asyncio.sleep(3)
        current_url = page.url
        page_content = await page.content()

        await screenshot_debug(page, "10_post_login")

        # Verificar se logou com sucesso
        if "minha-conta" in current_url or "dashboard" in current_url:
            log("OK", "Login OK via redirect!")
            # Tentar extrair token da página
            token_match = re.search(r'"token"\s*:\s*"([^"]+)"', page_content)
            if token_match:
                user_token = token_match.group(1)
                log("TOKEN", f"Token extraido da pagina: {user_token[:30]}...")
                STATS["logins_ok"] += 1
                await page.close()
                return user_token, "ok"

        STATS["logins_fail"] += 1
        await page.close()
        return None, "unknown_error"

    except Exception as e:
        log("FAIL", f"Erro no login: {str(e)}")
        debug_error(f"Login: {str(e)}", traceback.format_exc())
        try:
            await page.close()
        except Exception:
            pass
        return None, "exception"


# ==============================================================================
# EXTRAIR TOKEN VIA WEBCHECKIN (FALLBACK)
# ==============================================================================

async def extrair_token_webcheckin(context, grant_token):
    """Extrai user-token via webcheckin/token API."""
    if not grant_token:
        return None

    log("STEP", "Extraindo user-token via webcheckin/token...")
    try:
        url_token = f"{BFF_BASE}/api/v1/webcheckin/token"
        token_data = {"_token": grant_token}
        token_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": MOVIDA_BASE,
            "Referer": f"{MOVIDA_BASE}/webcheckin/meus-cartoes",
            "User-Agent": USER_AGENT_WEBVIEW,
            "X-Requested-With": "com.netsky.vfat.pro",
        }

        resp = requests.post(url_token, json=token_data, headers=token_headers, timeout=15)
        log("API", f"webcheckin/token -> HTTP {resp.status_code}", resp.text[:300])

        if resp.status_code == 200:
            data = resp.json()
            if not data.get("error") and data.get("data", {}).get("token"):
                user_token = data["data"]["token"]
                log("TOKEN", f"USER-TOKEN EXTRAIDO! {user_token[:20]}...{user_token[-10:]}")
                return user_token
        return None
    except Exception as e:
        log("FAIL", f"Erro webcheckin/token: {str(e)}")
        return None


# ==============================================================================
# RECUPERAÇÃO DE SENHA (FALLBACK)
# ==============================================================================

async def recuperar_senha(context, emailnator, cpf_numeros, email, nova_senha):
    """Recuperação de senha via API + email."""
    log("STEP", "RECUPERACAO DE SENHA: Iniciando fluxo...")
    STATS["senhas_recuperadas"] += 1

    try:
        url_recuperar = f"{BFF_BASE}/api/v1/usuario/recuperar-senha"
        recuperar_data = {"cpf": cpf_numeros, "tipo": "email"}
        recuperar_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": MOVIDA_BASE,
            "User-Agent": USER_AGENT_WEBVIEW,
        }

        resp = requests.post(url_recuperar, json=recuperar_data, headers=recuperar_headers, timeout=15)
        log("API", f"recuperar-senha -> HTTP {resp.status_code}", resp.text[:300])

        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                log("OK", "Email de recuperacao solicitado!")
            else:
                log("FAIL", f"recuperar-senha falhou: {data}")
                return False
        else:
            log("FAIL", f"recuperar-senha HTTP {resp.status_code}")
            return False

        # Aguardar email de recuperação
        from config import EMAIL_RECOVER_TIMEOUT
        link = emailnator.wait_for_email(
            sender_filter="movida",
            timeout=EMAIL_RECOVER_TIMEOUT,
            link_pattern="redefinir-senha"
        )

        if not link:
            link = emailnator.wait_for_email(
                sender_filter="movida",
                timeout=20,
                link_pattern="sendgrid"
            )

        if not link:
            log("FAIL", "Email de recuperacao nao chegou!")
            return False

        log("OK", f"Link de recuperacao: {link[:80]}...")
        return await ativar_conta_playwright(context, link, nova_senha)

    except Exception as e:
        log("FAIL", f"Erro na recuperacao: {str(e)}")
        debug_error(f"Recuperacao: {str(e)}", traceback.format_exc())
        return False


# ==============================================================================
# UTILITÁRIOS
# ==============================================================================

def random_delay():
    """Delay aleatório para simular digitação humana (ms)."""
    import random
    return random.randint(30, 80)
