#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AJATO TOKEN GENERATOR V7.0 - PLAYWRIGHT EDITION
Configurações centralizadas.
"""

import os
import platform

# ==============================================================================
# DETECÇÃO DE AMBIENTE
# ==============================================================================
IS_NETHUNTER = os.path.exists("/sdcard") or "android" in platform.platform().lower()
IS_TERMUX = "com.termux" in os.environ.get("PREFIX", "")

# ==============================================================================
# DIRETÓRIOS
# ==============================================================================
if IS_NETHUNTER:
    BASE_DIR = "/sdcard/nh_files"
else:
    BASE_DIR = os.path.join(os.path.expanduser("~"), "ajato_tokens")

OUTPUT_FILE = os.path.join(BASE_DIR, "tokenschkfull.txt")
DEBUG_LOG_FILE = os.path.join(BASE_DIR, "DEBUG_LOGS_GEN_TOKENS.txt")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")

os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# ==============================================================================
# MOVIDA
# ==============================================================================
MOVIDA_BASE = "https://www.movida.com.br"
BFF_BASE = "https://bff-b2c.movidacloud.com.br"
CADASTRO_URL = f"{MOVIDA_BASE}/usuario/cadastro"
LOGIN_URL = f"{MOVIDA_BASE}/usuario/login"
ENVIAR_CADASTRO_URL = f"{MOVIDA_BASE}/usuario/enviar-cadastro"
LOGIN_SITE_URL = f"{MOVIDA_BASE}/login_site"

# reCAPTCHA Enterprise config (extraído do HAR real)
RECAPTCHA_SITE_KEY = "6LeHBDAmAAAAAO1dMLM3aW7knyUDFzByq8Z8WI9E"

# ==============================================================================
# USER-AGENTS (do HAR real que funcionou)
# ==============================================================================
# User-Agent do WebView Android que deu sucesso no HAR
USER_AGENT_WEBVIEW = (
    "Mozilla/5.0 (Linux; Android 11; M2012K11AG Build/RQ3A.211001.001) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
    "Chrome/147.0.7727.24 Mobile Safari/537.36"
)

# User-Agent para Emailnator (Chrome desktop)
EMAILNATOR_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)

# ==============================================================================
# TIMEOUTS E DELAYS
# ==============================================================================
EMAIL_CONFIRM_TIMEOUT = 120      # Timeout para email de confirmação (segundos)
EMAIL_POLL_FAST = 2              # Poll rápido nos primeiros 30s
EMAIL_POLL_SLOW = 4              # Poll lento depois de 30s
EMAIL_FAST_PHASE = 30            # Duração da fase rápida
EMAIL_RECOVER_TIMEOUT = 60       # Timeout para email de recuperação
MAX_LOGIN_RETRIES = 3            # Tentativas de login
MAX_CADASTRO_RETRIES = 3         # Tentativas de cadastro
MAX_RECOVER_RETRIES = 2          # Tentativas de recuperação de senha
ACTIVATION_DELAY = 3             # Delay entre ativação e login
MAX_REACTIVATION_ATTEMPTS = 2    # Tentativas de reativação
MAX_INBOX_RETRIES = 3            # Retries para get_messages()
PAGE_LOAD_TIMEOUT = 30000        # Timeout para carregamento de página (ms)
NAVIGATION_TIMEOUT = 30000       # Timeout para navegação (ms)

# ==============================================================================
# EMAILNATOR
# ==============================================================================
EMAIL_TYPES_PRIORITY = ["dotGmail", "plusGmail", "googleMail"]

# ==============================================================================
# PLAYWRIGHT - OTIMIZAÇÕES NETHUNTER
# ==============================================================================
# Argumentos do Chromium otimizados para ARM64/NetHunter
CHROMIUM_ARGS = [
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--disable-extensions",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-breakpad",
    "--disable-component-extensions-with-background-pages",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-domain-reliability",
    "--disable-features=TranslateUI",
    "--disable-hang-monitor",
    "--disable-ipc-flooding-protection",
    "--disable-popup-blocking",
    "--disable-prompt-on-repost",
    "--disable-renderer-backgrounding",
    "--disable-sync",
    "--force-color-profile=srgb",
    "--metrics-recording-only",
    "--no-first-run",
    "--password-store=basic",
    "--use-mock-keychain",
    "--single-process",
    "--disable-blink-features=AutomationControlled",
]

# Viewport mobile (simula Android WebView)
VIEWPORT = {"width": 412, "height": 915}

# ==============================================================================
# CORES TERMINAL
# ==============================================================================
class C:
    R = "\033[0m"
    B = "\033[1m"
    G = "\033[92m"
    RD = "\033[91m"
    Y = "\033[93m"
    CY = "\033[96m"
    MG = "\033[95m"
    W = "\033[97m"
    DIM = "\033[2m"
    BG_G = "\033[42m"
    BG_R = "\033[41m"
    BG_Y = "\033[43m"
