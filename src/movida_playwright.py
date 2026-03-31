#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AJATO TOKEN GENERATOR V7.2 - Módulo Movida Playwright
Cadastro, ativação e login via Playwright (navegador headless real).

INTEGRAÇÃO OHMYCAPTCHA (shenhao-stu/ohmycaptcha):
  - JS universal para reCAPTCHA v3/Enterprise com fallback de injeção
  - Stealth JS melhorado (window.chrome, navigator.plugins)
  - Mouse movement humano antes do reCAPTCHA (melhora score)
  - Retry robusto com validação de token

CORREÇÕES V7.2:
  - Timeouts aumentados (60s) para NetHunter
  - Scroll automático antes de clicar em elementos fora do viewport
  - wait_until="domcontentloaded" ao invés de "networkidle" (mais rápido)
  - force=True + JS click fallback em radio/checkbox
  - Debug completo de cada ação do Playwright
"""

import re
import os
import json
import time
import random
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
    ELEMENT_TIMEOUT, RECAPTCHA_TIMEOUT,
    ACTIVATION_DELAY, MAX_LOGIN_RETRIES,
)
from logger import (
    log, debug_event, debug_error, debug_write,
    debug_request, debug_response,
    debug_pw_action, debug_pw_navigation, debug_pw_element,
    debug_pw_screenshot, debug_pw_html, debug_pw_js_eval,
    debug_pw_error,
    STATS,
)
from pessoa_generator import get_cidade_ibge


# ==============================================================================
# OHMYCAPTCHA - JS UNIVERSAL PARA reCAPTCHA v3/Enterprise
# Fonte: https://github.com/shenhao-stu/ohmycaptcha
# ==============================================================================

# JS que detecta grecaptcha.enterprise OU grecaptcha padrão automaticamente.
# Se nenhum estiver carregado, INJETA o script do Google e tenta novamente.
_RECAPTCHA_EXECUTE_JS = """
([key, action]) => new Promise((resolve, reject) => {
    // Timeout interno de 20s para NUNCA travar
    const timer = setTimeout(() => reject(new Error('reCAPTCHA timeout interno (20s)')), 20000);

    function tryExecute(gr) {
        if (gr && typeof gr.execute === 'function') {
            try {
                gr.ready(() => {
                    gr.execute(key, {action}).then(token => {
                        clearTimeout(timer);
                        resolve(token);
                    }).catch(err => {
                        clearTimeout(timer);
                        reject(err);
                    });
                });
            } catch(e) {
                clearTimeout(timer);
                reject(e);
            }
            return true;
        }
        return false;
    }

    // Tentar grecaptcha.enterprise primeiro, depois grecaptcha padrão
    const ent = window.grecaptcha && window.grecaptcha.enterprise;
    const std = window.grecaptcha;
    if (tryExecute(ent) || tryExecute(std)) return;

    // Não encontrou - verificar se o script já está sendo carregado
    const existingScript = document.querySelector('script[src*="recaptcha/enterprise.js"]') ||
                           document.querySelector('script[src*="recaptcha/api.js"]');
    if (existingScript) {
        // Script existe mas ainda não carregou - polling a cada 500ms
        let polls = 0;
        const pollInterval = setInterval(() => {
            polls++;
            const g = (window.grecaptcha && window.grecaptcha.enterprise) || window.grecaptcha;
            if (tryExecute(g)) {
                clearInterval(pollInterval);
                return;
            }
            if (polls >= 30) { // 15s max polling
                clearInterval(pollInterval);
                clearTimeout(timer);
                reject(new Error('reCAPTCHA script existe mas nunca carregou (15s polling)'));
            }
        }, 500);
        return;
    }

    // Script não existe - injetar
    const script = document.createElement('script');
    script.src = 'https://www.google.com/recaptcha/enterprise.js?render=' + key;
    script.onerror = () => {
        clearTimeout(timer);
        reject(new Error('Falha ao carregar script reCAPTCHA Enterprise'));
    };
    script.onload = () => {
        // Polling após load pois grecaptcha pode demorar a inicializar
        let polls = 0;
        const pollInterval = setInterval(() => {
            polls++;
            const g = (window.grecaptcha && window.grecaptcha.enterprise) || window.grecaptcha;
            if (tryExecute(g)) {
                clearInterval(pollInterval);
                return;
            }
            if (polls >= 20) { // 10s max após load
                clearInterval(pollInterval);
                clearTimeout(timer);
                reject(new Error('grecaptcha undefined mesmo apos script.onload (10s)'));
            }
        }, 500);
    };
    document.head.appendChild(script);
})
"""

# Stealth JS melhorado (ohmycaptcha + customizações)
_STEALTH_JS = """
// Anti-detecção: remover webdriver
Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

// Idioma brasileiro
Object.defineProperty(navigator, 'languages', {get: () => ['pt-BR', 'pt', 'en-US', 'en']});

// Simular plugins reais (ohmycaptcha technique)
Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});

// Simular Chrome real (ohmycaptcha technique)
window.chrome = {runtime: {}, loadTimes: () => {}, csi: () => {}};

// Platform Android
Object.defineProperty(navigator, 'platform', {get: () => 'Linux armv8l'});

// Permissions
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission }) :
        originalQuery(parameters)
);

// Limpar marcadores de automação
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Array;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Promise;
delete window.cdc_adoQpoasnfa76pfcZLmcfl_Symbol;
"""

# JS para extrair token do reCAPTCHA (múltiplos métodos - ohmycaptcha v2 technique)
_EXTRACT_TOKEN_JS = """
() => {
    const textarea = document.querySelector('#g-recaptcha-response')
        || document.querySelector('[name="g-recaptcha-response"]')
        || document.querySelector('textarea.g-recaptcha-response');
    if (textarea && textarea.value && textarea.value.length > 20) {
        return textarea.value;
    }
    const gr = window.grecaptcha?.enterprise || window.grecaptcha;
    if (gr && typeof gr.getResponse === 'function') {
        const resp = gr.getResponse();
        if (resp && resp.length > 20) return resp;
    }
    return null;
}
"""


# ==============================================================================
# UTILITÁRIOS
# ==============================================================================

def random_delay():
    """Delay aleatório para simular digitação humana (ms)."""
    return random.randint(30, 80)


async def simulate_human_mouse(page):
    """Simula movimentos de mouse humanos (técnica ohmycaptcha - melhora score reCAPTCHA)."""
    try:
        vw = VIEWPORT["width"]
        vh = VIEWPORT["height"]
        # Movimentos aleatórios suaves
        x1, y1 = random.randint(50, vw - 50), random.randint(50, vh // 2)
        x2, y2 = random.randint(50, vw - 50), random.randint(vh // 2, vh - 50)
        x3, y3 = random.randint(50, vw - 50), random.randint(100, vh - 100)

        await page.mouse.move(x1, y1)
        await asyncio.sleep(random.uniform(0.3, 0.8))
        await page.mouse.move(x2, y2)
        await asyncio.sleep(random.uniform(0.2, 0.5))
        await page.mouse.move(x3, y3)
        await asyncio.sleep(random.uniform(0.3, 0.6))

        debug_pw_action("human_mouse", f"Moved: ({x1},{y1})->({x2},{y2})->({x3},{y3})")
    except Exception as e:
        debug_pw_error("human_mouse", str(e))


async def safe_scroll_to(page, selector):
    """Faz scroll até o elemento ficar visível no viewport."""
    try:
        await page.evaluate(f"""
            () => {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                }}
            }}
        """)
        await asyncio.sleep(0.5)
        debug_pw_action("scroll_to", f"Scrolled to: {selector}")
    except Exception as e:
        debug_pw_error("scroll_to", str(e))


async def safe_click(page, selector, force=False, scroll=True, timeout=None):
    """Click seguro com scroll automático e fallback JS."""
    timeout = timeout or ELEMENT_TIMEOUT
    try:
        if scroll:
            await safe_scroll_to(page, selector)

        locator = page.locator(selector)
        count = await locator.count()
        debug_pw_element(selector, "click", f"count={count}, force={force}")

        if count > 0:
            try:
                await locator.first.click(force=force, timeout=timeout)
                debug_pw_element(selector, "click", "OK", success=True)
                return True
            except Exception as e1:
                # Fallback: JS click
                debug_pw_error(f"click({selector})", f"Playwright click falhou: {e1}, tentando JS click")
                try:
                    result = await page.evaluate(f"""
                        () => {{
                            const el = document.querySelector('{selector}');
                            if (el) {{ el.click(); return true; }}
                            return false;
                        }}
                    """)
                    if result:
                        debug_pw_element(selector, "js_click", "OK (fallback)", success=True)
                        return True
                    else:
                        debug_pw_element(selector, "js_click", "Elemento nao encontrado via JS", success=False)
                        return False
                except Exception as e2:
                    debug_pw_error(f"js_click({selector})", str(e2))
                    return False
        else:
            debug_pw_element(selector, "click", "Elemento nao encontrado", success=False)
            return False
    except Exception as e:
        debug_pw_error(f"safe_click({selector})", str(e))
        return False


async def safe_fill(page, selector, value, use_type=False, delay=None):
    """Preenchimento seguro com scroll e debug."""
    try:
        await safe_scroll_to(page, selector)
        locator = page.locator(selector)
        count = await locator.count()

        if count > 0:
            await locator.first.click(timeout=ELEMENT_TIMEOUT)
            await locator.first.fill("", timeout=ELEMENT_TIMEOUT)

            if use_type:
                d = delay or random_delay()
                await locator.first.type(value, delay=d, timeout=ELEMENT_TIMEOUT)
            else:
                await locator.first.fill(value, timeout=ELEMENT_TIMEOUT)

            debug_pw_element(selector, "fill", value[:50], success=True)
            return True
        else:
            debug_pw_element(selector, "fill", "Elemento nao encontrado", success=False)
            return False
    except Exception as e:
        debug_pw_error(f"safe_fill({selector})", str(e))
        return False


async def screenshot_debug(page, name):
    """Salva screenshot para debug com log detalhado."""
    try:
        ts = datetime.now().strftime("%H%M%S")
        path = os.path.join(SCREENSHOTS_DIR, f"{ts}_{name}.png")
        await page.screenshot(path=path, full_page=True)
        debug_pw_screenshot(name, path)
        log("DEBUG", f"Screenshot salvo: {name}")

        # Log do HTML da página
        try:
            title = await page.title()
            url = page.url
            html = await page.content()
            debug_pw_html(title, url, html[:3000])
        except Exception:
            pass

        return path
    except Exception as e:
        debug_pw_error("screenshot", str(e))
        return None


# ==============================================================================
# RESOLVER reCAPTCHA ENTERPRISE (INTEGRAÇÃO OHMYCAPTCHA)
# ==============================================================================

async def resolver_recaptcha_enterprise(page, action="signup"):
    """
    Resolve reCAPTCHA Enterprise usando técnicas do ohmycaptcha.
    V7.3: Corrigido bug de hang infinito.
    
    1. Simula mouse humano (melhora score)
    2. Aguarda grecaptcha carregar (polling robusto)
    3. Usa JS universal com timeout interno de 20s
    4. asyncio.wait_for() para NUNCA travar o Python
    5. Valida token (len > 20)
    6. Injeta no formulário
    """
    log("CAPTCHA", "Resolvendo reCAPTCHA Enterprise (ohmycaptcha method)...")
    debug_pw_action("recaptcha_start", f"Action: {action}, SiteKey: {RECAPTCHA_SITE_KEY}")

    # 1. Simular comportamento humano (melhora score do reCAPTCHA)
    await simulate_human_mouse(page)

    # 2. Aguardar reCAPTCHA carregar com verificação mais robusta
    recaptcha_ready = False
    
    # Método 1: Verificar via JS se grecaptcha.enterprise existe
    try:
        check_js = """
        () => {
            if (window.grecaptcha && window.grecaptcha.enterprise && 
                typeof window.grecaptcha.enterprise.execute === 'function') return 'enterprise';
            if (window.grecaptcha && typeof window.grecaptcha.execute === 'function') return 'standard';
            return null;
        }
        """
        result = await page.evaluate(check_js)
        if result:
            recaptcha_ready = True
            log("OK", f"reCAPTCHA {result} detectado na pagina!")
            debug_pw_js_eval("recaptcha_detect", f"type={result}", success=True)
    except Exception as e:
        debug_pw_error("recaptcha_check_initial", str(e))

    # Método 2: Se não encontrou, verificar se o script existe e fazer polling
    if not recaptcha_ready:
        log("DEBUG", "reCAPTCHA nao pronto, verificando se script existe na pagina...")
        try:
            script_exists = await page.evaluate("""
                () => {
                    const scripts = document.querySelectorAll('script[src*="recaptcha"]');
                    return scripts.length > 0 ? Array.from(scripts).map(s => s.src).join(', ') : null;
                }
            """)
            if script_exists:
                log("DEBUG", f"Script reCAPTCHA encontrado: {script_exists[:100]}")
                debug_pw_action("recaptcha_script_found", script_exists[:100])
                # Polling por até 15s esperando carregar
                for i in range(30):
                    await asyncio.sleep(0.5)
                    check = await page.evaluate("""
                        () => {
                            if (window.grecaptcha && window.grecaptcha.enterprise && 
                                typeof window.grecaptcha.enterprise.execute === 'function') return 'enterprise';
                            if (window.grecaptcha && typeof window.grecaptcha.execute === 'function') return 'standard';
                            return null;
                        }
                    """)
                    if check:
                        recaptcha_ready = True
                        log("OK", f"reCAPTCHA {check} carregou apos {(i+1)*0.5:.1f}s de polling!")
                        debug_pw_js_eval("recaptcha_polling_ok", f"type={check}, polls={i+1}", success=True)
                        break
            else:
                log("WARN", "Nenhum script reCAPTCHA encontrado na pagina!")
                debug_pw_action("recaptcha_no_script", "Will inject via JS universal")
        except Exception as e:
            debug_pw_error("recaptcha_polling", str(e))

    if not recaptcha_ready:
        log("WARN", "reCAPTCHA nao carregou, JS universal vai injetar o script...")
        debug_pw_action("recaptcha_will_inject", "Fallback injection")

    # 3. Executar JS universal (com retry + asyncio.wait_for para NUNCA travar)
    captcha_token = None
    last_error = None

    for attempt in range(3):
        try:
            # asyncio.wait_for garante que NUNCA trava mais que 25s
            captcha_token = await asyncio.wait_for(
                page.evaluate(
                    _RECAPTCHA_EXECUTE_JS,
                    [RECAPTCHA_SITE_KEY, action]
                ),
                timeout=25.0
            )

            if isinstance(captcha_token, str) and len(captcha_token) > 20:
                log("OK", f"reCAPTCHA Enterprise RESOLVIDO! ({len(captcha_token)} chars) [tentativa {attempt+1}]")
                debug_pw_js_eval("recaptcha_execute", f"Token: {len(captcha_token)} chars, attempt: {attempt+1}", success=True)
                break
            else:
                last_error = f"Token invalido: {captcha_token!r}"
                debug_pw_error("recaptcha_execute", f"Attempt {attempt+1}: {last_error}")
                captcha_token = None

        except asyncio.TimeoutError:
            last_error = f"asyncio.wait_for timeout (25s) na tentativa {attempt+1}"
            log("WARN", f"reCAPTCHA tentativa {attempt+1}/3: TIMEOUT Python (25s)")
            debug_pw_error("recaptcha_execute", f"Attempt {attempt+1}: {last_error}")
            if attempt < 2:
                await asyncio.sleep(2)

        except Exception as e:
            last_error = str(e)
            log("WARN", f"reCAPTCHA tentativa {attempt+1}/3 falhou: {last_error[:100]}")
            debug_pw_error("recaptcha_execute", f"Attempt {attempt+1}: {last_error}")
            if attempt < 2:
                await asyncio.sleep(2)

    if not captcha_token:
        log("FAIL", f"reCAPTCHA Enterprise falhou apos 3 tentativas! Ultimo erro: {last_error}")
        return None

    # 4. Injetar token no formulário
    try:
        await page.evaluate(f"""
            () => {{
                let existing = document.querySelector('input[name="g-recaptcha-response"]') ||
                               document.querySelector('textarea[name="g-recaptcha-response"]') ||
                               document.querySelector('textarea.g-recaptcha-response');
                if (!existing) {{
                    existing = document.createElement('textarea');
                    existing.name = 'g-recaptcha-response';
                    existing.style.display = 'none';
                    const form = document.getElementById('formCadastro') || document.forms[0];
                    if (form) form.appendChild(existing);
                }}
                existing.value = `{captcha_token}`;
            }}
        """)
        debug_pw_action("inject_captcha_token", f"Injetado {len(captcha_token)} chars no form")
    except Exception as e:
        debug_pw_error("inject_captcha_token", str(e))

    return captcha_token


# ==============================================================================
# CRIAR BROWSER
# ==============================================================================

async def criar_browser(playwright):
    """Cria instância do browser Playwright otimizada para NetHunter."""
    log("PW", "Iniciando Chromium headless...")
    debug_pw_action("launch", f"Args: {len(CHROMIUM_ARGS)} flags")

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

    # Stealth JS melhorado (ohmycaptcha + custom)
    await context.add_init_script(_STEALTH_JS)

    debug_pw_action("browser_ready", f"Viewport: {VIEWPORT}, UA: {USER_AGENT_WEBVIEW[:60]}...")
    log("OK", "Browser Chromium iniciado com sucesso!")
    return browser, context


# ==============================================================================
# CADASTRO VIA PLAYWRIGHT
# ==============================================================================

async def fazer_cadastro_playwright(context, pessoa, email, senha):
    """
    Realiza cadastro na Movida usando Playwright.
    V7.2: Integração ohmycaptcha + debug completo + scroll fix.
    """
    page = await context.new_page()
    page.set_default_timeout(ELEMENT_TIMEOUT)
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
        debug_pw_navigation(CADASTRO_URL, wait_until="domcontentloaded")

        await page.goto(CADASTRO_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)

        # Aguardar o formulário aparecer
        try:
            await page.wait_for_selector("#formCadastro", timeout=30000)
        except Exception:
            log("WARN", "Formulario demorou, aguardando mais...")
            await asyncio.sleep(5)
            form_exists = await page.locator("#formCadastro").count()
            if form_exists == 0:
                log("FAIL", "Formulario de cadastro NAO encontrado!")
                await screenshot_debug(page, "error_no_form")
                await page.close()
                return False

        log("OK", "Pagina de cadastro carregada!")
        await screenshot_debug(page, "01_cadastro_loaded")

        # =============================================
        # PASSO 2: Preencher Informações Pessoais
        # =============================================
        log("STEP", "PASSO 5: Preenchendo formulario de cadastro...")

        # Selecionar "Brasileiro" (scroll + force + JS fallback)
        debug_pw_action("select_nationality", "Brasileiro")
        clicked = await safe_click(page, "#brasileiro", force=True, scroll=True)
        if not clicked:
            await safe_click(page, 'label[for="brasileiro"]', force=True, scroll=True)
        await asyncio.sleep(0.5)

        # CPF
        await safe_fill(page, "#cpf", cpf_formatado, use_type=True)
        await asyncio.sleep(0.5)

        # Trigger blur para validação AJAX do CPF
        try:
            await page.locator("#cpf").evaluate("el => el.dispatchEvent(new Event('blur'))")
            debug_pw_action("cpf_blur", "Disparado evento blur para validacao AJAX")
        except Exception:
            pass
        log("DEBUG", f"CPF preenchido: {cpf_formatado}")

        # Aguardar validação AJAX do CPF
        await asyncio.sleep(2.0)

        # Verificar se CPF foi rejeitado
        try:
            page_html = await page.content()
            if "CPF já cadastrado" in page_html or "cpf já" in page_html.lower():
                log("FAIL", "CPF ja cadastrado na Movida!")
                debug_pw_action("cpf_rejected", "CPF ja cadastrado")
                await page.close()
                return False
        except Exception:
            pass

        # Nome
        await safe_fill(page, "#nome", pessoa["nome"], use_type=True)
        await asyncio.sleep(0.3)

        # Data de Nascimento
        await safe_fill(page, "#data_nasc", pessoa["data_nasc"], use_type=True)
        await asyncio.sleep(0.3)

        # Telefone
        telefone = pessoa.get("telefone_fixo", "")
        if telefone:
            await safe_fill(page, "#telefone", telefone, use_type=True)
            await asyncio.sleep(0.2)

        # Celular
        celular = pessoa.get("celular", "(11) 99999-9999")
        await safe_fill(page, "#celular", celular, use_type=True)
        await asyncio.sleep(0.3)

        # Email
        await safe_fill(page, "#email", email, use_type=True)
        await asyncio.sleep(0.3)

        # Confirmação Email
        await safe_fill(page, "#email_conf", email, use_type=True)
        await asyncio.sleep(0.3)

        log("OK", "Informacoes pessoais preenchidas!")
        await screenshot_debug(page, "02_pessoais_ok")

        # =============================================
        # PASSO 3: Preencher Endereço
        # =============================================
        log("STEP", "Preenchendo endereco...")

        # CEP
        await safe_fill(page, "#cep", cep_raw, use_type=True)
        try:
            await page.locator("#cep").evaluate("el => el.dispatchEvent(new Event('blur'))")
            debug_pw_action("cep_blur", "Disparado evento blur para busca_cep AJAX")
        except Exception:
            pass
        log("DEBUG", f"CEP preenchido: {cep_raw}")

        # Aguardar auto-preenchimento do CEP
        await asyncio.sleep(3.0)

        # Verificar se logradouro foi auto-preenchido
        try:
            logradouro_val = await page.locator("#logradouro").input_value()
            if not logradouro_val:
                log("WARN", "Auto-preenchimento do CEP falhou, preenchendo manualmente...")
                await safe_fill(page, "#logradouro", pessoa.get("endereco", "Rua Exemplo"))
                await safe_fill(page, "#bairro", pessoa.get("bairro", "Centro"))
            else:
                log("OK", f"CEP auto-preencheu: {logradouro_val}")
                debug_pw_element("#logradouro", "auto-fill", logradouro_val)
        except Exception as e:
            debug_pw_error("logradouro_check", str(e))

        # Número
        await safe_fill(page, "#numero", str(pessoa.get("numero", "100")), use_type=True)
        await asyncio.sleep(0.3)

        # País (Brasil = value "1")
        try:
            pais_count = await page.locator("#Pais").count()
            if pais_count > 0:
                await safe_scroll_to(page, "#Pais")
                await page.locator("#Pais").select_option(value="1", timeout=ELEMENT_TIMEOUT)
                debug_pw_element("#Pais", "select", "1 (Brasil)")
                await asyncio.sleep(0.5)
        except Exception as e:
            debug_pw_error("pais_select", str(e))

        # Estado
        try:
            uf_count = await page.locator("#uf_sel").count()
            if uf_count > 0:
                estado = pessoa.get("estado", "SP")
                await safe_scroll_to(page, "#uf_sel")
                await page.locator("#uf_sel").select_option(value=estado, timeout=ELEMENT_TIMEOUT)
                debug_pw_element("#uf_sel", "select", estado)
                await asyncio.sleep(1.5)
        except Exception as e:
            debug_pw_error("uf_select", str(e))

        # Cidade (código IBGE)
        try:
            cidade_count = await page.locator("#cidade_sel").count()
            if cidade_count > 0:
                cidade_ibge = get_cidade_ibge(pessoa.get("cidade", ""))
                await safe_scroll_to(page, "#cidade_sel")
                try:
                    await page.locator("#cidade_sel").select_option(value=cidade_ibge, timeout=ELEMENT_TIMEOUT)
                    debug_pw_element("#cidade_sel", "select", f"{cidade_ibge} ({pessoa.get('cidade', '')})")
                except Exception:
                    cidade_nome = pessoa.get("cidade", "").upper()
                    try:
                        await page.locator("#cidade_sel").select_option(label=cidade_nome, timeout=ELEMENT_TIMEOUT)
                        debug_pw_element("#cidade_sel", "select_label", cidade_nome)
                    except Exception as e2:
                        log("WARN", f"Nao conseguiu selecionar cidade: {cidade_nome}")
                        debug_pw_error("cidade_select", str(e2))
                await asyncio.sleep(0.5)
        except Exception as e:
            debug_pw_error("cidade_block", str(e))

        log("OK", "Endereco preenchido!")
        await screenshot_debug(page, "03_endereco_ok")

        # =============================================
        # PASSO 4: Preencher Senha
        # =============================================
        log("STEP", "Preenchendo senha...")

        await safe_fill(page, "#senha_cadastro", senha, use_type=True)
        await asyncio.sleep(0.3)
        await safe_fill(page, "#senha_conf", senha, use_type=True)
        await asyncio.sleep(0.3)

        log("OK", f"Senha preenchida: {senha}")

        # =============================================
        # PASSO 5: Checkboxes
        # =============================================
        log("STEP", "Marcando checkboxes...")

        checkboxes = [
            ("#ofertasFidelidade", "Ofertas Fidelidade"),
            ("#politicaPrivacidade", "Politica Privacidade"),
            ("#participarFidelidade", "Participar Fidelidade"),
            ("#regulamentoFidelidade", "Regulamento Fidelidade"),
        ]

        for cb_selector, cb_name in checkboxes:
            try:
                cb_count = await page.locator(cb_selector).count()
                if cb_count > 0:
                    is_checked = await page.locator(cb_selector).is_checked()
                    if not is_checked:
                        await safe_click(page, cb_selector, force=True, scroll=True)
                        debug_pw_element(cb_selector, "check", cb_name)
                    else:
                        debug_pw_element(cb_selector, "already_checked", cb_name)
                    await asyncio.sleep(0.2)
            except Exception as e:
                debug_pw_error(f"checkbox({cb_selector})", str(e))

        log("OK", "Checkboxes marcados!")
        await screenshot_debug(page, "04_checkboxes_ok")

        # =============================================
        # PASSO 6: Resolver reCAPTCHA Enterprise (OHMYCAPTCHA)
        # =============================================
        captcha_token = await resolver_recaptcha_enterprise(page, action="signup")

        if not captcha_token:
            log("FAIL", "reCAPTCHA Enterprise falhou!")
            await screenshot_debug(page, "05_captcha_fail")
            await page.close()
            return False

        # =============================================
        # PASSO 7: Clicar em ENVIAR
        # =============================================
        log("STEP", "PASSO 6: Enviando cadastro...")
        await screenshot_debug(page, "05_pre_submit")

        # Scroll até o botão de enviar
        await safe_scroll_to(page, "#btnEnviaDados")
        await asyncio.sleep(0.5)

        # Interceptar a resposta do POST
        try:
            async with page.expect_navigation(
                wait_until="domcontentloaded",
                timeout=NAVIGATION_TIMEOUT
            ) as navigation:
                await page.locator("#btnEnviaDados").click(force=True, timeout=ELEMENT_TIMEOUT)
                debug_pw_action("submit_click", "Clicou em #btnEnviaDados")
        except Exception as e:
            log("WARN", f"Navigation apos submit: {str(e)}")
            debug_pw_error("submit_navigation", str(e))

        # Verificar resultado
        await asyncio.sleep(3)
        current_url = page.url
        page_content = await page.content()

        debug_pw_navigation(current_url, status="post-submit")
        await screenshot_debug(page, "06_post_submit")

        # Log do conteúdo pós-submit
        debug_pw_html(await page.title(), current_url, page_content[:5000])

        # Verificar sucesso
        success_indicators = [
            "Cadastro efetuado com sucesso",
            "Bem vindo a Movida",
            "Bem-vindo",
            "receber um e-mail para confirmar",
            "confirmar seu cadastro",
        ]

        for indicator in success_indicators:
            if indicator.lower() in page_content.lower():
                log("OK", f"CADASTRO EFETUADO COM SUCESSO! ('{indicator}' detectado)")
                STATS["cadastros_ok"] += 1
                await page.close()
                return True

        # Verificar se ainda está no formulário (falha)
        if 'name="senha_cadastro"' in page_content or 'id="formCadastro"' in page_content:
            error_msgs = re.findall(
                r'(?:toastr\[.*?\]|toastr\.(?:error|warning))\s*\(\s*["\']([^"\']+)',
                page_content
            )
            html_errors = re.findall(
                r'class="[^"]*(?:error|alert-danger|text-danger)[^"]*"[^>]*>(.*?)<',
                page_content, re.IGNORECASE
            )

            for msg in error_msgs:
                log("FAIL", f"  Erro JS: {msg[:200]}")
            for err in html_errors:
                clean = re.sub(r'<[^>]+>', '', err).strip()
                if clean:
                    log("FAIL", f"  Erro HTML: {clean[:200]}")

            if not error_msgs and not html_errors:
                log("FAIL", "Cadastro FALHOU - formulario retornado sem mensagem de erro visivel")

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
        debug_pw_error("cadastro_main", str(e), traceback.format_exc())
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
    log("STEP", "Ativando conta via link de confirmacao...")
    debug_pw_action("ativacao_start", f"Link: {confirmation_link[:100]}...")

    page = await context.new_page()
    page.set_default_timeout(ELEMENT_TIMEOUT)

    try:
        debug_pw_navigation(confirmation_link, wait_until="domcontentloaded")
        await page.goto(confirmation_link, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)
        await asyncio.sleep(3)

        final_url = page.url
        log("OK", f"URL final: {final_url[:100]}...")
        debug_pw_navigation(final_url, status="loaded")
        await screenshot_debug(page, "07_ativacao_page")

        page_content = await page.content()

        # Extrair PessoaID
        pessoa_id = None
        id_match = re.search(r'[?&]id=(\d+)', final_url)
        if id_match:
            pessoa_id = id_match.group(1)
            log("OK", f"PessoaID extraido da URL: {pessoa_id}")
            debug_pw_action("pessoa_id_from_url", pessoa_id)

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
                    debug_pw_action("pessoa_id_from_html", pessoa_id)
                    break

        has_password_form = 'name="senha"' in page_content or 'confirmar_senha' in page_content

        if has_password_form and pessoa_id:
            log("STEP", "Definindo senha via formulario...")
            debug_pw_action("password_form_detected", f"PessoaID: {pessoa_id}")

            senha_field = page.locator('input[name="senha"], input[id="senha"]').first
            if await senha_field.count() > 0:
                await senha_field.fill(senha)
                debug_pw_element('input[name="senha"]', "fill", "***")
                await asyncio.sleep(0.3)

            confirma_field = page.locator('input[name="confirmar_senha"], input[id="confirmar_senha"]').first
            if await confirma_field.count() > 0:
                await confirma_field.fill(senha)
                debug_pw_element('input[name="confirmar_senha"]', "fill", "***")
                await asyncio.sleep(0.3)

            submit_btn = page.locator('button[type="submit"], input[type="submit"]').first
            if await submit_btn.count() > 0:
                await submit_btn.click()
                debug_pw_action("password_submit", "Clicou submit")
                await asyncio.sleep(2)

            log("OK", "Senha definida via formulario!")
            STATS["ativacoes_ok"] += 1
            await page.close()
            return True

        elif pessoa_id:
            log("STEP", "Definindo senha via API atualizar-senha...")
            debug_pw_action("api_password_fallback", f"PessoaID: {pessoa_id}")

            session = requests.Session()
            session.headers.update({"User-Agent": USER_AGENT_WEBVIEW})

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

            debug_request("POST", atualizar_url, atualizar_headers, atualizar_data)
            resp = session.post(atualizar_url, data=atualizar_data, headers=atualizar_headers, timeout=15)
            debug_response(atualizar_url, resp.status_code, dict(resp.headers), resp.text[:500], "atualizar-senha")

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

        if any(x in page_content.lower() for x in ["sucesso", "ativada", "confirmada", "login"]):
            log("OK", "Ativacao aparentemente OK!")
            STATS["ativacoes_ok"] += 1
            await page.close()
            return True

        log("WARN", "Ativacao incerta, tentando login mesmo assim...")
        STATS["ativacoes_fail"] += 1
        await page.close()
        return True

    except Exception as e:
        log("FAIL", f"Erro na ativacao: {str(e)}")
        debug_pw_error("ativacao_main", str(e), traceback.format_exc())
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
    """Realiza login na Movida via Playwright. V7.2: Debug completo + ohmycaptcha."""
    log("STEP", "Fazendo login na Movida...")
    debug_pw_action("login_start", f"CPF: {cpf_numeros}")

    page = await context.new_page()
    page.set_default_timeout(ELEMENT_TIMEOUT)

    try:
        debug_pw_navigation(LOGIN_URL, wait_until="domcontentloaded")
        await page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=NAVIGATION_TIMEOUT)
        await asyncio.sleep(3)

        await screenshot_debug(page, "08_login_page")

        # Preencher CPF
        cpf_selectors = [
            'input[placeholder="CPF"]',
            'input#mat-input-0',
            'input[formcontrolname="cpf"]',
            'input[type="text"]',
        ]
        cpf_filled = False
        for sel in cpf_selectors:
            try:
                count = await page.locator(sel).count()
                if count > 0:
                    await safe_fill(page, sel, cpf_numeros, use_type=True)
                    cpf_filled = True
                    break
            except Exception:
                continue

        if not cpf_filled:
            log("FAIL", "Nao encontrou campo de CPF no login!")
            debug_pw_error("login_cpf", "Nenhum seletor de CPF encontrado")
            await screenshot_debug(page, "error_login_no_cpf")
            await page.close()
            return None, "no_cpf_field"

        await asyncio.sleep(0.5)

        # Preencher Senha
        senha_selectors = [
            'input[placeholder="Senha"]',
            'input#mat-input-1',
            'input[formcontrolname="senha"]',
            'input[type="password"]',
        ]
        senha_filled = False
        for sel in senha_selectors:
            try:
                count = await page.locator(sel).count()
                if count > 0:
                    await safe_fill(page, sel, senha, use_type=True)
                    senha_filled = True
                    break
            except Exception:
                continue

        if not senha_filled:
            log("FAIL", "Nao encontrou campo de Senha no login!")
            debug_pw_error("login_senha", "Nenhum seletor de senha encontrado")
            await screenshot_debug(page, "error_login_no_senha")
            await page.close()
            return None, "no_senha_field"

        await asyncio.sleep(0.5)
        await screenshot_debug(page, "09_login_filled")

        # Resolver reCAPTCHA Enterprise para login (ohmycaptcha method)
        captcha_token = await resolver_recaptcha_enterprise(page, action="login")
        if captcha_token:
            log("OK", f"reCAPTCHA login resolvido! ({len(captcha_token)} chars)")
        else:
            log("WARN", "reCAPTCHA login falhou, tentando login sem token...")

        # Clicar em Entrar
        login_btn = page.locator('button:has-text("Entrar")').first
        debug_pw_action("login_click", "Clicando em Entrar")

        # Interceptar resposta de login
        response_promise = page.wait_for_response(
            lambda r: "login_site" in r.url or "login" in r.url,
            timeout=15000
        )

        await login_btn.click(timeout=ELEMENT_TIMEOUT)

        try:
            response = await response_promise
            resp_text = await response.text()
            resp_status = response.status

            debug_response(response.url, resp_status, None, resp_text[:1000], "login_response")
            log("API", f"login -> HTTP {resp_status}", resp_text[:300])

            if resp_status == 200:
                try:
                    data = json.loads(resp_text)
                    debug_event("login_response_json", json.dumps(data, ensure_ascii=False)[:500])

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
                        debug_event("login_fail_msg", data.get("msg", "?"))

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
                    debug_pw_error("login_json_parse", f"Nao e JSON: {resp_text[:200]}")
        except Exception as e:
            log("DEBUG", f"Timeout esperando resposta de login: {str(e)}")
            debug_pw_error("login_response_wait", str(e))

        # Fallback: verificar se a página mudou
        await asyncio.sleep(3)
        current_url = page.url
        page_content = await page.content()

        debug_pw_navigation(current_url, status="post-login")
        await screenshot_debug(page, "10_post_login")

        if "minha-conta" in current_url or "dashboard" in current_url:
            log("OK", "Login OK via redirect!")
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
        debug_pw_error("login_main", str(e), traceback.format_exc())
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
    debug_pw_action("webcheckin_start", f"Grant token: {grant_token[:30]}...")

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

        debug_request("POST", url_token, token_headers, token_data)
        resp = requests.post(url_token, json=token_data, headers=token_headers, timeout=15)
        debug_response(url_token, resp.status_code, dict(resp.headers), resp.text[:500], "webcheckin/token")

        log("API", f"webcheckin/token -> HTTP {resp.status_code}", resp.text[:300])

        if resp.status_code == 200:
            data = resp.json()
            if not data.get("error") and data.get("data", {}).get("token"):
                user_token = data["data"]["token"]
                log("TOKEN", f"USER-TOKEN EXTRAIDO! {user_token[:20]}...{user_token[-10:]}")
                debug_event("webcheckin_token_ok", f"Token: {user_token[:40]}...")
                return user_token
        return None
    except Exception as e:
        log("FAIL", f"Erro webcheckin/token: {str(e)}")
        debug_pw_error("webcheckin", str(e), traceback.format_exc())
        return None


# ==============================================================================
# RECUPERAÇÃO DE SENHA (FALLBACK)
# ==============================================================================

async def recuperar_senha(context, emailnator, cpf_numeros, email, nova_senha):
    """Recuperação de senha via API + email."""
    log("STEP", "RECUPERACAO DE SENHA: Iniciando fluxo...")
    debug_pw_action("recuperacao_start", f"CPF: {cpf_numeros}")
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

        debug_request("POST", url_recuperar, recuperar_headers, recuperar_data)
        resp = requests.post(url_recuperar, json=recuperar_data, headers=recuperar_headers, timeout=15)
        debug_response(url_recuperar, resp.status_code, dict(resp.headers), resp.text[:500], "recuperar-senha")

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

        from config import EMAIL_RECOVER_TIMEOUT
        link = await emailnator.wait_for_email_async(
            sender_filter="movida",
            timeout=EMAIL_RECOVER_TIMEOUT,
            link_pattern="redefinir-senha"
        )

        if not link:
            link = await emailnator.wait_for_email_async(
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
        debug_pw_error("recuperacao_main", str(e), traceback.format_exc())
        return False
