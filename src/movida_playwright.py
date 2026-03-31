#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AJATO TOKEN GENERATOR V7.8 - Módulo Movida Playwright
Cadastro, ativação e login via Playwright (navegador headless real).

V7.8 - MODO TESTE + FIX FALSO POSITIVO:
  - FIX CRITICO: Detecção de sucesso HTTP 200 corrigida (falso positivo eliminado)
    * "/usuario/cadastro" NOT in "/usuario/enviar-cadastro" = True (BUG!)
    * Agora verifica se response URL é EXATAMENTE a URL de envio (= falha)
    * HTTP 200 com formulário de cadastro = FALHA, não sucesso
  - FIX: Body completo logado (10000 chars) para análise detalhada
  - FIX: allow_redirects=True para capturar redirects automaticamente
  - FIX: Verifica se body contém o formulário (indica recarregamento = falha)
  - Playwright preenche o formulário (visual, com screenshots)
  - reCAPTCHA resolvido via HTTP bypass (enterprise/anchor + reload)
  - Submit feito via POST HTTP direto (bypass do JS do formulário)
  - Resolve o problema do grecaptcha.enterprise não carregar no headless

INTEGRAÇÕES:
  - OhMyCaptcha: Stealth JS, mouse humano, anti-detecção
  - V6.1: HTTP bypass enterprise/anchor + reload
  - Playwright: Preenchimento de formulário + coleta de cookies
  - HTTP POST direto: Submit real com cookies do Playwright
  - Debug completo de cada ação
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
    C, MOVIDA_BASE, BFF_BASE, CADASTRO_URL, LOGIN_URL,
    ENVIAR_CADASTRO_URL, LOGIN_SITE_URL,
    RECAPTCHA_SITE_KEY, RECAPTCHA_CO, RECAPTCHA_V,
    USER_AGENT_WEBVIEW,
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
# RESOLVER reCAPTCHA ENTERPRISE - ABORDAGEM HÍBRIDA V7.4
# ==============================================================================

def _solve_recaptcha_http(action="signup"):
    """
    Resolve reCAPTCHA Enterprise via HTTP puro (bypass do V6.1).
    Funciona mesmo quando o Google bloqueia grecaptcha no headless.
    
    Fluxo:
    1. GET /recaptcha/enterprise/anchor -> extrai c-token
    2. POST /recaptcha/enterprise/reload -> extrai rresp token
    3. Fallback para /recaptcha/api2/ se enterprise falhar
    """
    log("CAPTCHA", f"[HTTP] Resolvendo reCAPTCHA via HTTP bypass (action='{action}')...")
    debug_pw_action("recaptcha_http_start", f"action={action}, key={RECAPTCHA_SITE_KEY[:15]}...")

    anchor_params = {
        "ar": "1",
        "k": RECAPTCHA_SITE_KEY,
        "co": RECAPTCHA_CO,
        "hl": "pt-BR",
        "v": RECAPTCHA_V,
        "size": "invisible",
    }

    endpoints = ["enterprise", "api2"]

    for attempt in range(3):
        for endpoint in endpoints:
            try:
                anchor_url = f"https://www.google.com/recaptcha/{endpoint}/anchor?{urlencode(anchor_params)}"
                log("CAPTCHA", f"  [{endpoint}] Tentativa {attempt+1}/3 - GET anchor...")
                debug_request("GET", anchor_url)

                cap_session = requests.Session()
                cap_session.headers.update({
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
                })

                res_anchor = cap_session.get(anchor_url, timeout=15)
                debug_response(anchor_url, res_anchor.status_code, None, res_anchor.text[:1500], f"recaptcha_anchor_{endpoint}")

                if res_anchor.status_code != 200:
                    log("WARN", f"  [{endpoint}] Anchor HTTP {res_anchor.status_code}")
                    continue

                # Extrair c-token
                c_token_match = re.search(r'id="recaptcha-token"\s*value="(.*?)"', res_anchor.text)
                if not c_token_match:
                    c_token_match = re.search(r'recaptcha-token.*?value="(.*?)"', res_anchor.text)

                if not c_token_match:
                    log("FAIL", f"  [{endpoint}] c-token nao encontrado no anchor")
                    debug_event("c-token not found", f"Response snippet: {res_anchor.text[:500]}")
                    continue

                c_token = c_token_match.group(1)
                log("CAPTCHA", f"  [{endpoint}] c-token obtido ({len(c_token)} chars)")

                # POST reload
                reload_data = {
                    "v": RECAPTCHA_V,
                    "reason": "q",
                    "c": c_token,
                    "k": RECAPTCHA_SITE_KEY,
                    "co": RECAPTCHA_CO,
                    "hl": "pt-BR",
                    "size": "invisible",
                    "chr": "",
                    "vh": "",
                    "bg": "",
                }

                reload_url = f"https://www.google.com/recaptcha/{endpoint}/reload?k={RECAPTCHA_SITE_KEY}"
                reload_headers = {
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": f"https://www.google.com/recaptcha/{endpoint}/anchor?{urlencode(anchor_params)}",
                }

                log("CAPTCHA", f"  [{endpoint}] POST reload (form-urlencoded)...")
                debug_request("POST", reload_url, reload_headers, reload_data)

                res_reload = cap_session.post(
                    reload_url,
                    data=urlencode(reload_data),
                    headers=reload_headers,
                    timeout=15
                )
                debug_response(reload_url, res_reload.status_code, None, res_reload.text[:3000], f"recaptcha_reload_{endpoint}")

                if res_reload.status_code != 200:
                    log("WARN", f"  [{endpoint}] Reload HTTP {res_reload.status_code}")
                    continue

                # Extrair token - Método 1: regex rresp
                rresp_match = re.findall(r'"rresp","(.*?)"', res_reload.text)
                if rresp_match and rresp_match[0]:
                    token = rresp_match[0]
                    log("OK", f"  [{endpoint}] reCAPTCHA HTTP RESOLVIDO! ({len(token)} chars)")
                    debug_event("reCAPTCHA HTTP solved", f"endpoint={endpoint}, token_length={len(token)}")
                    return token

                # Método 2: JSON parse
                try:
                    text = res_reload.text
                    json_start = text.find('[')
                    if json_start >= 0:
                        json_data = json.loads(text[json_start:])
                        if isinstance(json_data, list) and len(json_data) > 1 and json_data[1]:
                            token = str(json_data[1])
                            if len(token) > 50:
                                log("OK", f"  [{endpoint}] reCAPTCHA HTTP RESOLVIDO via JSON! ({len(token)} chars)")
                                debug_event("reCAPTCHA HTTP solved (JSON)", f"endpoint={endpoint}, token_length={len(token)}")
                                return token
                except (json.JSONDecodeError, IndexError, TypeError):
                    pass

                if '"rresp",null' in res_reload.text or '"rresp", null' in res_reload.text:
                    log("WARN", f"  [{endpoint}] rresp=null (token nao gerado)")
                    debug_event(f"rresp=null on {endpoint}", res_reload.text[:500])
                else:
                    log("WARN", f"  [{endpoint}] Resposta inesperada do reload")
                    debug_event(f"Unexpected reload response on {endpoint}", res_reload.text[:500])

            except Exception as e:
                log("FAIL", f"  [{endpoint}] Erro HTTP: {str(e)}")
                debug_error(f"reCAPTCHA HTTP {endpoint}: {str(e)}", traceback.format_exc())

        # Delay progressivo entre tentativas
        if attempt < 2:
            delay = (attempt + 1) * 2
            log("WARN", f"  Aguardando {delay}s antes da proxima tentativa HTTP...")
            time.sleep(delay)

    log("FAIL", "[HTTP] reCAPTCHA HTTP FALHOU apos todas as tentativas!")
    return None


async def _solve_recaptcha_browser(page, action="signup"):
    """
    Tenta resolver reCAPTCHA Enterprise via browser (JS nativo).
    Pode falhar se o Google detectar headless.
    Timeout máximo: 15s (rápido, para não atrasar o fallback HTTP).
    """
    log("CAPTCHA", "[BROWSER] Tentando resolver reCAPTCHA via JS nativo...")
    debug_pw_action("recaptcha_browser_start", f"action={action}")

    # Verificar se grecaptcha está disponível
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
        if not result:
            # Polling rápido (5s máx)
            for i in range(10):
                await asyncio.sleep(0.5)
                result = await page.evaluate(check_js)
                if result:
                    break

        if not result:
            log("WARN", "[BROWSER] grecaptcha nao disponivel no browser")
            debug_pw_action("recaptcha_browser_unavailable", "grecaptcha not found")
            return None

        log("OK", f"[BROWSER] grecaptcha.{result} detectado!")
        debug_pw_js_eval("recaptcha_browser_detect", f"type={result}", success=True)

    except Exception as e:
        debug_pw_error("recaptcha_browser_check", str(e))
        return None

    # Tentar executar (timeout curto de 15s)
    try:
        captcha_token = await asyncio.wait_for(
            page.evaluate(
                _RECAPTCHA_EXECUTE_JS,
                [RECAPTCHA_SITE_KEY, action]
            ),
            timeout=15.0
        )

        if isinstance(captcha_token, str) and len(captcha_token) > 20:
            log("OK", f"[BROWSER] reCAPTCHA RESOLVIDO via JS! ({len(captcha_token)} chars)")
            debug_pw_js_eval("recaptcha_browser_ok", f"Token: {len(captcha_token)} chars", success=True)
            return captcha_token
        else:
            log("WARN", f"[BROWSER] Token invalido: {captcha_token!r}")
            return None

    except asyncio.TimeoutError:
        log("WARN", "[BROWSER] Timeout 15s - grecaptcha nao respondeu")
        debug_pw_error("recaptcha_browser_timeout", "15s timeout")
        return None
    except Exception as e:
        log("WARN", f"[BROWSER] Erro: {str(e)[:100]}")
        debug_pw_error("recaptcha_browser_error", str(e))
        return None


async def resolver_recaptcha_enterprise(page, action="signup"):
    """
    Resolver reCAPTCHA Enterprise - ABORDAGEM HÍBRIDA V7.4.
    
    Estratégia:
    1. Simula mouse humano (melhora score)
    2. Tenta resolver via browser JS (rápido, 15s timeout)
    3. Se falhar, usa HTTP bypass puro do V6.1 (sempre funciona)
    4. Injeta o token no DOM do Playwright
    """
    log("CAPTCHA", "="*60)
    log("CAPTCHA", "RESOLVENDO reCAPTCHA Enterprise (HIBRIDO V7.4)")
    log("CAPTCHA", f"  Action: {action} | SiteKey: {RECAPTCHA_SITE_KEY[:20]}...")
    log("CAPTCHA", "="*60)
    debug_pw_action("recaptcha_hybrid_start", f"action={action}")

    # 1. Simular comportamento humano (melhora score)
    await simulate_human_mouse(page)

    captcha_token = None

    # ==========================================
    # MÉTODO 1: Tentar via Browser JS (rápido)
    # ==========================================
    log("CAPTCHA", "[1/2] Tentando resolver via Browser JS...")
    captcha_token = await _solve_recaptcha_browser(page, action)

    if captcha_token:
        log("OK", f"reCAPTCHA resolvido via BROWSER! ({len(captcha_token)} chars)")
    else:
        # ==========================================
        # MÉTODO 2: HTTP Bypass (V6.1 - sempre funciona)
        # ==========================================
        log("CAPTCHA", "[2/2] Browser falhou, usando HTTP bypass (V6.1)...")
        captcha_token = _solve_recaptcha_http(action)

        if captcha_token:
            log("OK", f"reCAPTCHA resolvido via HTTP BYPASS! ({len(captcha_token)} chars)")
        else:
            log("FAIL", "reCAPTCHA FALHOU em AMBOS os métodos!")
            debug_pw_error("recaptcha_hybrid_fail", "Both browser and HTTP methods failed")
            return None

    # ==========================================
    # INJETAR TOKEN NO DOM DO PLAYWRIGHT
    # ==========================================
    try:
        # Escapar o token para uso seguro no JS
        safe_token = captcha_token.replace('\\', '\\\\').replace('`', '\\`').replace('$', '\\$')
        await page.evaluate(f"""
            () => {{
                // Procurar campo existente
                let existing = document.querySelector('textarea[name="g-recaptcha-response"]')
                    || document.querySelector('input[name="g-recaptcha-response"]')
                    || document.querySelector('textarea.g-recaptcha-response')
                    || document.querySelector('#g-recaptcha-response');
                
                if (!existing) {{
                    // Criar campo hidden no formulário
                    existing = document.createElement('textarea');
                    existing.name = 'g-recaptcha-response';
                    existing.id = 'g-recaptcha-response';
                    existing.style.display = 'none';
                    const form = document.getElementById('formCadastro') || document.forms[0];
                    if (form) form.appendChild(existing);
                    else document.body.appendChild(existing);
                }}
                existing.value = `{safe_token}`;
                
                // Também setar em todos os textareas de reCAPTCHA (pode haver múltiplos)
                document.querySelectorAll('textarea[name="g-recaptcha-response"]').forEach(el => {{
                    el.value = `{safe_token}`;
                }});
            }}
        """)
        log("OK", f"Token injetado no DOM! ({len(captcha_token)} chars)")
        debug_pw_action("inject_captcha_token", f"Injetado {len(captcha_token)} chars no form")
    except Exception as e:
        log("WARN", f"Erro ao injetar token no DOM: {str(e)[:100]}")
        debug_pw_error("inject_captcha_token", str(e))
        # Não retorna None aqui - o token ainda pode funcionar via submit

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
            return "captcha_fail"

        # =============================================
        # PASSO 7: SUBMIT HTTP DIRETO (V7.6)
        # O JS do formulário chama grecaptcha.enterprise.execute
        # que não funciona no headless. Então fazemos o POST
        # HTTP diretamente usando cookies do Playwright.
        # =============================================
        log("STEP", "PASSO 6: Enviando cadastro via HTTP DIRETO (V7.6)...")
        await screenshot_debug(page, "05_pre_submit")

        # 1. Extrair cookies do Playwright para usar no requests
        cookies_list = await page.context.cookies()
        cookies_dict = {c["name"]: c["value"] for c in cookies_list}
        debug_event("cookies_extracted", f"{len(cookies_dict)} cookies: {', '.join(cookies_dict.keys())}")

        # 2. Extrair todos os campos do formulário via JS
        form_data_js = await page.evaluate("""
            () => {
                const form = document.getElementById('formCadastro');
                if (!form) return null;
                const data = {};
                const inputs = form.querySelectorAll('input, select, textarea');
                for (const el of inputs) {
                    const name = el.name || el.id;
                    if (!name) continue;
                    if (el.type === 'radio') {
                        if (el.checked) data[name] = el.value;
                    } else if (el.type === 'checkbox') {
                        if (el.checked) data[name] = el.value || 'on';
                    } else {
                        data[name] = el.value || '';
                    }
                }
                return data;
            }
        """)

        if not form_data_js:
            log("FAIL", "Nao conseguiu extrair dados do formulario!")
            await page.close()
            return "erro_generico"

        debug_event("form_data_extracted", f"{len(form_data_js)} campos: {json.dumps({k: v[:30] if len(str(v))>30 else v for k,v in form_data_js.items()}, ensure_ascii=False)}")

        # 3. Injetar o token reCAPTCHA nos dados do formulário
        form_data_js["g-recaptcha-response"] = captcha_token

        # 4. Garantir campos obrigatórios do HAR (que podem faltar)
        form_data_js.setdefault("isLoginSocial", "")
        form_data_js.setdefault("requester", "")
        form_data_js.setdefault("tokenRequester", "")
        form_data_js.setdefault("partnership", "")
        form_data_js.setdefault("user_token", "")
        form_data_js.setdefault("nationality", "Brasileiro")
        form_data_js.setdefault("nacionalidade", "2")
        form_data_js.setdefault("IDNacionalidade", "1007")

        # Extrair UF e cidade dos selects (que podem não estar no form_data)
        try:
            uf_val = await page.locator("#uf_sel").input_value()
            form_data_js["uf"] = uf_val
        except Exception:
            form_data_js.setdefault("uf", pessoa.get("estado", "SP"))

        try:
            cidade_val = await page.locator("#cidade_sel").input_value()
            form_data_js["cidade"] = cidade_val
        except Exception:
            form_data_js.setdefault("cidade", get_cidade_ibge(pessoa.get("cidade", "")))

        # Remover campos indesejados que podem causar erro
        for key_to_remove in ["senha_conf_visible", "senha_cadastro_visible"]:
            form_data_js.pop(key_to_remove, None)

        # 5. Fazer o POST HTTP direto
        log("API", f"POST {ENVIAR_CADASTRO_URL}")
        log("DEBUG", f"  Campos: {len(form_data_js)} | Token reCAPTCHA: {len(captcha_token)} chars")
        log("DEBUG", f"  CPF: {form_data_js.get('cpf', '?')} | Nome: {form_data_js.get('nome', '?')}")
        log("DEBUG", f"  Email: {form_data_js.get('email', '?')} | CEP: {form_data_js.get('cep', '?')}")

        submit_headers = {
            "User-Agent": USER_AGENT_WEBVIEW,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": MOVIDA_BASE,
            "Referer": CADASTRO_URL,
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "navigate",
            "sec-fetch-dest": "document",
        }

        debug_request("POST", ENVIAR_CADASTRO_URL, submit_headers,
                      {k: v[:50] if len(str(v))>50 else v for k,v in form_data_js.items()})

        try:
            submit_resp = requests.post(
                ENVIAR_CADASTRO_URL,
                data=form_data_js,
                headers=submit_headers,
                cookies=cookies_dict,
                allow_redirects=True,  # V7.8: seguir redirects automaticamente
                timeout=30
            )

            resp_status = submit_resp.status_code
            resp_text = submit_resp.text[:10000]  # V7.8: body completo para análise
            resp_headers = dict(submit_resp.headers)
            final_url = str(submit_resp.url)
            redirect_history = [r.status_code for r in submit_resp.history]  # V7.8: histórico de redirects

            log("DEBUG", f"  Redirect history: {redirect_history}")
            log("DEBUG", f"  Final URL: {final_url}")

            debug_response(ENVIAR_CADASTRO_URL, resp_status, resp_headers, resp_text[:3000], "cadastro_submit_http")
            log("API", f"cadastro-submit -> HTTP {resp_status} (final URL: {final_url[:100]})")

            # V7.8: Verificar se houve redirect (allow_redirects=True agora)
            redirect_url = ""
            if redirect_history:
                log("OK", f"Houve redirect(s): {redirect_history}")
                redirect_url = final_url
                debug_event("cadastro_redirect", f"history={redirect_history} -> {final_url}")
            else:
                log("DEBUG", "Nenhum redirect detectado")

            # =============================================
            # V7.8: DETECÇÃO DE RESULTADO DO POST HTTP
            # (allow_redirects=True - redirects já foram seguidos)
            # =============================================

            # V7.8: Se houve redirect na history, o servidor fez 303/302
            # Isso indica SUCESSO no cadastro!
            if redirect_history and any(s in (301, 302, 303) for s in redirect_history):
                log("OK", f"CADASTRO EFETUADO COM SUCESSO! (redirect {redirect_history} -> {final_url[:100]})")
                debug_event("cadastro_sucesso", f"redirects={redirect_history} -> {final_url}")
                STATS["cadastros_ok"] += 1

                # Verificar conteúdo da página final
                resp_lower = resp_text.lower()
                if "sucesso" in resp_lower or "confirmar" in resp_lower or "e-mail" in resp_lower:
                    log("OK", "Confirmacao de cadastro detectada na pagina final!")
                elif "documento" in resp_lower and "cadastrado" in resp_lower:
                    log("WARN", "Redirect indica CPF duplicado!")
                    await page.close()
                    return "cpf_duplicado"

                await screenshot_debug(page, "06_post_submit")
                await page.close()
                return "sucesso"

            # HTTP 200 = verificar corpo para determinar resultado
            elif resp_status == 200:
                resp_lower = resp_text.lower()

                # V7.8: PRIMEIRO verificar se é o formulário de cadastro recarregado
                # Se o body contém o formulário, o cadastro FALHOU silenciosamente
                form_reloaded = any(s in resp_lower for s in [
                    'id="formcadastro"',
                    'id="btnenvia',
                    'formcadastro',
                    'enviadados',
                ])

                if form_reloaded:
                    log("WARN", f"{C.BG_R}{C.W} HTTP 200 COM FORMULARIO RECARREGADO = CADASTRO FALHOU! {C.R}")
                    log("WARN", "O servidor retornou a mesma pagina de cadastro (falha silenciosa)")
                    log("DEBUG", f"  Final URL: {final_url}")
                    log("DEBUG", f"  Body contem formulario: SIM")

                    # Tentar encontrar mensagem de erro oculta no body
                    # Procurar por alertas, modals, mensagens de erro
                    error_hints = []
                    for pattern in [
                        'class="erro"', 'class="error"', 'class="alert"',
                        'class="msg-erro"', 'class="mensagem-erro"',
                        'class="invalid-feedback"', 'class="field-validation-error"',
                        'movmodal', 'movmodal', 'alertify',
                        'documento já cadastrado', 'documento ja cadastrado',
                        'cpf já cadastrado', 'cpf ja cadastrado',
                        'já possui cadastro', 'ja possui cadastro',
                        'recaptcha', 'captcha',
                        'campo obrigat', 'preencha',
                    ]:
                        if pattern in resp_lower:
                            # Extrair contexto ao redor do match
                            idx = resp_lower.find(pattern)
                            context_start = max(0, idx - 100)
                            context_end = min(len(resp_text), idx + len(pattern) + 200)
                            error_hints.append(f"[{pattern}] -> ...{resp_text[context_start:context_end]}...")

                    if error_hints:
                        log("DEBUG", f"  Possiveis indicadores de erro encontrados:")
                        for hint in error_hints[:5]:
                            log("DEBUG", f"    {hint[:200]}")
                        debug_event("cadastro_form_reload_errors", str(error_hints)[:2000])

                        # Verificar CPF duplicado especificamente
                        if any('cadastrado' in h.lower() or 'duplicado' in h.lower() for h in error_hints):
                            log("WARN", "CPF DUPLICADO detectado no formulario recarregado!")
                            await screenshot_debug(page, "06_post_submit")
                            await page.close()
                            return "cpf_duplicado"
                    else:
                        log("DEBUG", "  Nenhum indicador de erro especifico encontrado no body")
                        log("DEBUG", f"  Body primeiros 1000 chars: {resp_text[:1000]}")
                        log("DEBUG", f"  Body ultimos 1000 chars: {resp_text[-1000:]}")

                    debug_event("cadastro_form_reload", f"URL={final_url} | body_len={len(resp_text)}")
                    await screenshot_debug(page, "06_post_submit")
                    await page.close()
                    return "erro_generico"

                # Verificar sucesso REAL no corpo (pagina diferente do formulario)
                success_in_body = any(s in resp_lower for s in [
                    "cadastro efetuado com sucesso",
                    "bem vindo", "bem-vindo",
                    "confirmar seu cadastro",
                    "e-mail de confirma",
                    "verifique seu e-mail",
                    "enviamos um e-mail",
                    "conta criada",
                ])
                if success_in_body:
                    matched_success = [s for s in [
                        "cadastro efetuado com sucesso", "bem vindo", "bem-vindo",
                        "confirmar seu cadastro", "e-mail de confirma",
                        "verifique seu e-mail", "enviamos um e-mail", "conta criada",
                    ] if s in resp_lower]
                    log("OK", f"CADASTRO EFETUADO COM SUCESSO! (detectado no corpo: {matched_success})")
                    STATS["cadastros_ok"] += 1
                    await screenshot_debug(page, "06_post_submit")
                    await page.close()
                    return "sucesso"

                # Verificar CPF duplicado no corpo
                cpf_dup_in_body = any(s in resp_lower for s in [
                    "documento já cadastrado", "documento ja cadastrado",
                    "cpf já cadastrado", "cpf ja cadastrado",
                    "já possui cadastro", "ja possui cadastro",
                ])
                if cpf_dup_in_body:
                    log("WARN", "CPF DUPLICADO detectado na resposta HTTP!")
                    debug_event("cpf_duplicado_http", resp_text[:500])
                    await screenshot_debug(page, "06_post_submit")
                    await page.close()
                    return "cpf_duplicado"

                # Verificar erro de validação ESPECÍFICO
                error_patterns = [
                    "erro ao cadastrar", "erro no cadastro",
                    "campo obrigatório", "campo obrigatorio",
                    "preencha corretamente", "dados inválidos", "dados invalidos",
                    "recaptcha inválido", "recaptcha invalido",
                    "token inválido", "token invalido",
                    "invalid recaptcha", "captcha failed",
                ]
                error_in_body = any(s in resp_lower for s in error_patterns)
                if error_in_body:
                    matched = [s for s in error_patterns if s in resp_lower]
                    log("FAIL", f"Erro de validacao no cadastro: {matched}")
                    log("DEBUG", f"  Response body (500 chars): {resp_text[:500]}")
                    debug_event("cadastro_erro_validacao", resp_text[:500])
                    await screenshot_debug(page, "06_post_submit")
                    await page.close()
                    return "erro_generico"

                # V7.8: HTTP 200 sem formulário e sem indicadores claros
                # Pode ser uma página intermediária - logar TUDO para análise
                log("WARN", f"HTTP 200 sem formulario e sem indicadores claros")
                log("DEBUG", f"  Final URL: {final_url}")
                log("DEBUG", f"  Body length: {len(resp_text)} chars")
                log("DEBUG", f"  Body primeiros 1500 chars: {resp_text[:1500]}")
                log("DEBUG", f"  Body ultimos 1500 chars: {resp_text[-1500:]}")
                debug_event("cadastro_http200_unclear", resp_text[:3000])
                await screenshot_debug(page, "06_post_submit")
                await page.close()

                # V7.8: NÃO assumir sucesso! Retornar como incerto para investigação
                log("WARN", "Retornando como 'incerto' - NAO assumir sucesso sem evidencia")
                return "incerto"

            # HTTP 4xx/5xx = erro
            else:
                log("FAIL", f"Cadastro falhou com HTTP {resp_status}")
                debug_event("cadastro_http_error", f"HTTP {resp_status}: {resp_text[:500]}")

                if resp_status == 422:
                    log("FAIL", "HTTP 422 - Erro de validacao do servidor")
                    # Tentar parsear JSON de erro
                    try:
                        err_json = json.loads(resp_text)
                        log("FAIL", f"  Detalhes: {json.dumps(err_json, ensure_ascii=False)[:300]}")
                    except Exception:
                        pass

                await screenshot_debug(page, "06_post_submit")
                await page.close()
                return "erro_generico"

        except requests.exceptions.Timeout:
            log("FAIL", "Timeout no POST HTTP do cadastro (30s)")
            await screenshot_debug(page, "06_post_submit")
            await page.close()
            return "erro_generico"
        except Exception as e:
            log("FAIL", f"Erro no POST HTTP do cadastro: {str(e)}")
            debug_pw_error("http_submit", str(e), traceback.format_exc())
            await screenshot_debug(page, "06_post_submit")
            await page.close()
            return "erro_generico"

    except Exception as e:
        log("FAIL", f"Erro no cadastro Playwright: {str(e)}")
        debug_pw_error("cadastro_main", str(e), traceback.format_exc())
        await screenshot_debug(page, "error_cadastro")
        try:
            await page.close()
        except Exception:
            pass
        return "erro_generico"


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
