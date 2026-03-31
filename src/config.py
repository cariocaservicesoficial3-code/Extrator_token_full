#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AJATO TOKEN GENERATOR V7.1 - PLAYWRIGHT EDITION
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

# Diretórios principais
LOGS_DIR = os.path.join(BASE_DIR, "logs")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")

# Arquivos
OUTPUT_FILE = os.path.join(BASE_DIR, "tokenschkfull.txt")
DEBUG_LOG_FILE = os.path.join(LOGS_DIR, "DEBUG_LOGS_GEN_TOKENS.txt")
PW_LOG_FILE = os.path.join(LOGS_DIR, "PLAYWRIGHT_DEBUG.txt")
HTTP_LOG_FILE = os.path.join(LOGS_DIR, "HTTP_REQUESTS.txt")
CYCLE_LOG_FILE = os.path.join(LOGS_DIR, "CYCLE_HISTORY.txt")

# Criar todos os diretórios
os.makedirs(BASE_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
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
USER_AGENT_WEBVIEW = (
    "Mozilla/5.0 (Linux; Android 11; M2012K11AG Build/RQ3A.211001.001) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
    "Chrome/147.0.7727.24 Mobile Safari/537.36"
)

EMAILNATOR_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
)

# ==============================================================================
# TIMEOUTS E DELAYS
# ==============================================================================
EMAIL_CONFIRM_TIMEOUT = 120
EMAIL_POLL_FAST = 2
EMAIL_POLL_SLOW = 4
EMAIL_FAST_PHASE = 30
EMAIL_RECOVER_TIMEOUT = 60
MAX_LOGIN_RETRIES = 3
MAX_CADASTRO_RETRIES = 3
MAX_RECOVER_RETRIES = 2
ACTIVATION_DELAY = 3
MAX_REACTIVATION_ATTEMPTS = 2
MAX_INBOX_RETRIES = 3

# Playwright timeouts (AUMENTADOS para NetHunter)
PAGE_LOAD_TIMEOUT = 60000        # 60s para carregar página
NAVIGATION_TIMEOUT = 60000       # 60s para navegação
ELEMENT_TIMEOUT = 30000          # 30s para encontrar elementos
RECAPTCHA_TIMEOUT = 30000        # 30s para reCAPTCHA

# ==============================================================================
# EMAILNATOR
# ==============================================================================
EMAIL_TYPES_PRIORITY = ["dotGmail", "plusGmail", "googleMail"]

# ==============================================================================
# PLAYWRIGHT - OTIMIZAÇÕES NETHUNTER
# ==============================================================================
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
