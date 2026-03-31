#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AJATO TOKEN GENERATOR V6.1 - NETHUNTER EDITION
================================================
Migrado e otimizado para Kali Linux NetHunter.
V6.1: reCAPTCHA ENTERPRISE fix + campos fidelidade + cadastro V3.0.

CHANGELOG V5.0 (EMAILNATOR FIX EDITION):
  ============================================================
  PROBLEMA IDENTIFICADO (V4.0):
    O cadastro na Movida funcionava (HTTP 303), mas o email de
    confirmação NUNCA era interceptado pelo Emailnator.
    A inbox só mostrava "ADSVPN" (spam) e o email da Movida
    nunca aparecia, causando timeout de 90s em TODOS os ciclos.
  ============================================================

  CAUSA RAIZ (comparação com script A0AUTO que funciona):
    1. O A0AUTO usa requests.Session() com cookies persistentes
       para o Emailnator, e extrai o XSRF-TOKEN diretamente dos
       cookies do objeto Session (não do header Set-Cookie).
    2. Nosso script V4.0 extraía o XSRF-TOKEN do header Set-Cookie
       via regex, o que é FRÁGIL e pode falhar silenciosamente.
    3. O A0AUTO trata HTTP 419 (token expirado) com re-extração
       automática do XSRF-TOKEN e retry imediato.
    4. O A0AUTO usa get_message_content() para ler o conteúdo
       COMPLETO de cada email (passando messageID), enquanto nosso
       script V4.0 fazia isso mas com headers potencialmente
       desatualizados após HTTP 500.
    5. O A0AUTO usa quopri.decodestring() para decodificar
       conteúdo quoted-printable dos emails, o que é ESSENCIAL
       para extrair URLs do SendGrid que vêm encoded.

  CORREÇÕES V5.0:
    - FIX CRÍTICO: XSRF-TOKEN agora extraído dos cookies do Session
      (igual ao A0AUTO), não mais do header Set-Cookie via regex
    - FIX CRÍTICO: Tratamento de HTTP 419 com re-extração automática
      do XSRF-TOKEN e retry (igual ao A0AUTO)
    - FIX CRÍTICO: Tratamento de HTTP 500 com retry + delay
    - FIX CRÍTICO: Decodificação quoted-printable (quopri) no
      conteúdo dos emails para extrair URLs SendGrid corretamente
    - FIX: Retry robusto no get_messages() (até 3 tentativas com
      re-extração de XSRF entre cada uma)
    - FIX: extract_links() agora decodifica quopri antes de buscar
    - FIX: Polling mais agressivo nos primeiros 30s (2s) e depois
      relaxa para 4s (evita perder email que chega rápido)
    - MELHORIA: Log detalhado de cada poll com contagem de mensagens
    - MELHORIA: Detecção de email Movida ampliada (vetormovida,
      noreply, sendgrid, fidelidade, cadastro)
    - MELHORIA: Fallback para buscar link #6 (método do A0AUTO)
      quando o padrão sendgrid não encontra o link de confirmação
"""

import json
import re
import sys
import os
import time
import random
import string
import requests
import traceback
import unicodedata
import quopri
from datetime import datetime
from urllib.parse import unquote, quote, urlencode, urlparse, parse_qs

# ==============================================================================
# CONFIGURAÇÕES - NETHUNTER
# ==============================================================================
BASE_DIR = "/sdcard/nh_files"
OUTPUT_FILE = os.path.join(BASE_DIR, "tokenschkfull.txt")
DEBUG_LOG_FILE = os.path.join(BASE_DIR, "DEBUG_LOGS_GEN_TOKENS.txt")

# Criar diretório se não existir
os.makedirs(BASE_DIR, exist_ok=True)

API_TOKEN_FIXO = "vdjY4igsZah60bNMyadQIg=="
MOVIDA_BASE = "https://www.movida.com.br"
BFF_BASE = "https://bff-b2c.movidacloud.com.br"

# reCAPTCHA config
RECAPTCHA_SITE_KEY = "6LeHBDAmAAAAAO1dMLM3aW7knyUDFzByq8Z8WI9E"
RECAPTCHA_CO = "aHR0cHM6Ly93d3cubW92aWRhLmNvbS5icjo0NDM."
RECAPTCHA_V = "qm3PSRIx10pekcnS9DjGnjPW"

# Timeouts otimizados V5.0
EMAIL_CONFIRM_TIMEOUT = 90       # V6.0: 90s (V3.0 usava 60s, damos margem extra)
EMAIL_POLL_FAST = 2              # Poll rápido nos primeiros 30s
EMAIL_POLL_SLOW = 4              # Poll lento depois de 30s
EMAIL_FAST_PHASE = 30            # Duração da fase rápida
EMAIL_RECOVER_TIMEOUT = 50       # Timeout para email de recuperação
MAX_LOGIN_RETRIES = 3            # Tentativas de login
MAX_RECOVER_RETRIES = 2
ACTIVATION_DELAY = 3             # Delay entre ativação e login
MAX_REACTIVATION_ATTEMPTS = 2    # Tentativas de reativação
MAX_INBOX_RETRIES = 3            # Retries para get_messages() em caso de erro

# Tipos de email Emailnator - ordem de prioridade
EMAIL_TYPES_PRIORITY = ["dotGmail", "plusGmail", "googleMail"]

# User-Agent IDÊNTICO ao A0AUTO (Chrome 135 Windows)
EMAILNATOR_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"

# User-Agent para Movida (Android WebView - IDENTICO ao V3.0 que funciona!)
USER_AGENT = "Mozilla/5.0 (Linux; Android 16; M2012K11AG Build/BP4A.251205.006) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/145.0.7632.159 Mobile Safari/537.36"

# Cores para terminal
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

# Contadores globais
STATS = {
    "tokens_gerados": 0,
    "cadastros_ok": 0,
    "cadastros_fail": 0,
    "emails_timeout": 0,
    "emails_recebidos": 0,
    "senhas_recuperadas": 0,
    "ativacoes_ok": 0,
    "ativacoes_fail": 0,
    "reativacoes": 0,
    "inbox_errors": 0,
    "start_time": time.time()
}

CURRENT_CYCLE = {"num": 0, "email": "", "cpf": "", "nome": ""}

# ==============================================================================
# SISTEMA DE DEBUG LOGS EM ARQUIVO
# ==============================================================================

def debug_write(text):
    try:
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            clean = re.sub(r'\033\[[0-9;]*m', '', str(text))
            f.write(clean + "\n")
    except Exception as e:
        print(f"  [DEBUG FILE ERROR] {e}")

def debug_separator(title=""):
    lines = "=" * 80
    debug_write(f"\n{lines}")
    if title:
        debug_write(f"  {title}")
        debug_write(lines)
    debug_write("")

def debug_session_start(cycle_num, email, cpf, nome):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    debug_separator(f"CICLO #{cycle_num} | {ts}")
    debug_write(f"Email: {email}")
    debug_write(f"CPF: {cpf}")
    debug_write(f"Nome: {nome}")
    debug_write("")

def debug_request(method, url, headers=None, body=None):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    debug_write(f"[{ts}] >>> REQUEST: {method} {url}")
    if headers:
        debug_write("  HEADERS:")
        for k, v in headers.items():
            if k == "g-recaptcha-response" or (isinstance(v, str) and len(v) > 500):
                debug_write(f"    {k}: {v[:80]}...({len(v)} chars)")
            else:
                debug_write(f"    {k}: {v}")
    if body:
        if isinstance(body, dict):
            debug_write("  BODY (dict):")
            for k, v in body.items():
                v_str = str(v)
                if len(v_str) > 200:
                    debug_write(f"    {k}: {v_str[:200]}...({len(v_str)} chars)")
                else:
                    debug_write(f"    {k}: {v_str}")
        elif isinstance(body, str):
            if len(body) > 2000:
                debug_write(f"  BODY (raw, {len(body)} chars):")
                debug_write(f"    {body[:2000]}...")
            else:
                debug_write(f"  BODY (raw): {body}")
        elif isinstance(body, bytes):
            debug_write(f"  BODY (bytes, {len(body)} bytes): {body[:200]}")
    debug_write("")

def debug_response(url, status_code, headers=None, body="", label=""):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    tag = f" [{label}]" if label else ""
    debug_write(f"[{ts}] <<< RESPONSE{tag}: HTTP {status_code} | {url}")
    if headers:
        debug_write("  RESPONSE HEADERS:")
        for k, v in headers.items():
            debug_write(f"    {k}: {v}")
    if body:
        body_str = str(body)
        debug_write(f"  RESPONSE BODY ({len(body_str)} chars):")
        if len(body_str) > 10000:
            debug_write(f"    {body_str[:10000]}")
            debug_write(f"    ... [TRUNCATED, total {len(body_str)} chars]")
        else:
            debug_write(f"    {body_str}")
    debug_write("")

def debug_event(event, detail=""):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    debug_write(f"[{ts}] [EVENT] {event}")
    if detail:
        debug_write(f"    {detail}")

def debug_error(error, tb=""):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    debug_write(f"[{ts}] [ERROR] {error}")
    if tb:
        debug_write(f"  TRACEBACK:\n{tb}")

# ==============================================================================
# LOGGER - TERMINAL + ARQUIVO
# ==============================================================================

def log(level, msg, detail=""):
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    colors = {
        "INFO": C.CY, "OK": C.G, "FAIL": C.RD, "WARN": C.Y,
        "API": C.MG, "EMAIL": C.CY, "CAPTCHA": C.MG,
        "TOKEN": C.G, "DEBUG": C.DIM, "STEP": C.W
    }
    c = colors.get(level, C.W)
    prefix = f"{C.B}[{ts}]{C.R} {c}[{level:7s}]{C.R}"
    print(f"{prefix} {msg}")
    if detail:
        detail_show = detail[:300] + "..." if len(detail) > 300 else detail
        print(f"           {C.DIM}{detail_show}{C.R}")

    debug_write(f"[{ts}] [{level:7s}] {msg}")
    if detail:
        debug_write(f"           {detail[:500]}")

def log_separator(title=""):
    print(f"\n{C.MG}{C.B}{'='*60}{C.R}")
    if title:
        print(f"{C.MG}{C.B}  {title}{C.R}")
        print(f"{C.MG}{C.B}{'='*60}{C.R}")

def log_stats():
    elapsed = time.time() - STATS["start_time"]
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    taxa = 0
    if STATS["cadastros_ok"] > 0:
        taxa = int(STATS["tokens_gerados"] / STATS["cadastros_ok"] * 100)
    stats_line = (
        f"Tokens: {STATS['tokens_gerados']} | "
        f"Cadastros OK: {STATS['cadastros_ok']} | "
        f"Ativacoes OK: {STATS['ativacoes_ok']} | "
        f"Emails OK: {STATS['emails_recebidos']} | "
        f"Fails: {STATS['cadastros_fail']} | "
        f"Email Timeout: {STATS['emails_timeout']} | "
        f"Inbox Erros: {STATS['inbox_errors']} | "
        f"Reativacoes: {STATS['reativacoes']} | "
        f"Taxa: {taxa}% | "
        f"Tempo: {mins}m{secs}s"
    )
    print(f"\n{C.CY}{C.B}[STATS]{C.R} "
          f"Tokens: {C.G}{STATS['tokens_gerados']}{C.R} | "
          f"Cadastros: {C.G}{STATS['cadastros_ok']}{C.R} | "
          f"Ativacoes: {C.G}{STATS['ativacoes_ok']}{C.R} | "
          f"Emails: {C.G}{STATS['emails_recebidos']}{C.R} | "
          f"Fails: {C.RD}{STATS['cadastros_fail']}{C.R} | "
          f"Timeout: {C.Y}{STATS['emails_timeout']}{C.R} | "
          f"InboxErr: {C.Y}{STATS['inbox_errors']}{C.R} | "
          f"Reativ: {C.Y}{STATS['reativacoes']}{C.R} | "
          f"Taxa: {C.G}{taxa}%{C.R} | "
          f"Tempo: {mins}m{secs}s\n")
    debug_write(f"\n[STATS] {stats_line}\n")

# ==============================================================================
# GERADOR DE SENHA SEGURA
# ==============================================================================

def gerar_senha():
    """Gera senha que atende requisitos Movida: min 8 chars, upper+lower+digit+especial."""
    especiais = "!@#$%&*?"
    senha = [
        random.choice(string.ascii_lowercase),
        random.choice(string.ascii_lowercase),
        random.choice(string.ascii_uppercase),
        random.choice(string.ascii_uppercase),
        random.choice(string.digits),
        random.choice(string.digits),
        random.choice(especiais),
    ]
    tamanho = random.randint(12, 16)
    pool = string.ascii_letters + string.digits + especiais
    while len(senha) < tamanho:
        senha.append(random.choice(pool))
    random.shuffle(senha)
    return "".join(senha)

# ==============================================================================
# EMAILNATOR V5.0 - REESCRITO BASEADO NO A0AUTO QUE FUNCIONA
# ==============================================================================
# Diferenças críticas em relação à V4.0:
# 1. XSRF-TOKEN extraído dos cookies do Session (não do header Set-Cookie)
# 2. Tratamento de HTTP 419 com re-extração automática
# 3. Tratamento de HTTP 500 com retry
# 4. Decodificação quopri no conteúdo dos emails
# 5. Retry robusto em get_messages()
# ==============================================================================

class Emailnator:
    def __init__(self):
        self.base_url = "https://www.emailnator.com"
        self.user_agent = EMAILNATOR_UA
        self.xsrf_token = None
        self.email = None
        self.reset_session()

    def reset_session(self):
        """Reseta a sessão HTTP (igual ao A0AUTO)."""
        self.session = requests.Session()
        self.xsrf_token = None
        self.email = None
        log("DEBUG", "Emailnator: sessao resetada")

    def extract_xsrf_token(self):
        """
        Extrai XSRF-TOKEN fazendo GET na página principal.
        MÉTODO IDÊNTICO AO A0AUTO: lê dos cookies do Session, não do header.
        """
        try:
            headers = {
                'User-Agent': self.user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            }
            response = self.session.get(self.base_url, headers=headers, timeout=30)
            debug_response(self.base_url, response.status_code, None, "", "emailnator_xsrf_GET")

            # MÉTODO A0AUTO: Extrair XSRF-TOKEN dos cookies do Session
            for cookie in self.session.cookies:
                if cookie.name == 'XSRF-TOKEN':
                    self.xsrf_token = unquote(cookie.value)
                    log("DEBUG", f"XSRF-TOKEN extraido dos cookies ({len(self.xsrf_token)} chars)")
                    debug_event("XSRF-TOKEN from cookies", f"{len(self.xsrf_token)} chars")
                    return True

            # Fallback: tentar do response.cookies
            for cookie in response.cookies:
                if cookie.name == 'XSRF-TOKEN':
                    self.xsrf_token = unquote(cookie.value)
                    log("DEBUG", f"XSRF-TOKEN extraido do response.cookies ({len(self.xsrf_token)} chars)")
                    return True

            log("WARN", "XSRF-TOKEN nao encontrado nos cookies!")
            debug_event("XSRF-TOKEN NOT FOUND", f"Cookies: {[c.name for c in self.session.cookies]}")
            return False
        except Exception as e:
            log("FAIL", f"extract_xsrf_token erro: {str(e)}")
            debug_error(f"extract_xsrf_token: {str(e)}", traceback.format_exc())
            return False

    def _get_headers(self):
        """Headers para requests ao Emailnator (idêntico ao A0AUTO)."""
        h = {
            'Content-Type': 'application/json',
            'Origin': 'https://www.emailnator.com',
            'Referer': 'https://www.emailnator.com/',
            'User-Agent': self.user_agent,
            'X-Requested-With': 'XMLHttpRequest',
        }
        if self.xsrf_token:
            h['X-XSRF-TOKEN'] = self.xsrf_token
        return h

    def generate_email(self, email_type="dotGmail"):
        """
        Gera email temporário via Emailnator.
        Fluxo idêntico ao A0AUTO: extract_xsrf_token() + POST generate-email.
        """
        if not self.extract_xsrf_token():
            log("FAIL", "Nao foi possivel obter XSRF-TOKEN!")
            return None

        try:
            url = f"{self.base_url}/generate-email"
            payload = {"email": [email_type]}
            headers = self._get_headers()

            log("DEBUG", f"Emailnator: gerando com tipo '{email_type}'")
            debug_request("POST", url, headers, payload)
            resp = self.session.post(url, json=payload, headers=headers, timeout=30)
            debug_response(url, resp.status_code, dict(resp.headers), resp.text[:500], "generate_email")

            # Atualizar XSRF-TOKEN dos cookies após cada request
            self._refresh_xsrf_from_cookies()

            if resp.status_code == 200:
                result = resp.json()
                # A0AUTO trata tanto dict com 'email' quanto list direto
                if isinstance(result, dict) and 'email' in result:
                    emails = result['email']
                    self.email = emails[0] if isinstance(emails, list) else emails
                elif isinstance(result, list):
                    self.email = result[0]
                else:
                    log("FAIL", f"generate-email resposta inesperada: {result}")
                    return None

                log("API", f"generate-email -> HTTP {resp.status_code}", resp.text[:200])
                log("OK", f"Email gerado ({email_type}): {self.email}")
                return self.email

            log("FAIL", f"generate-email HTTP {resp.status_code}", resp.text[:200])
            return None
        except Exception as e:
            log("FAIL", f"Emailnator generate: {str(e)}")
            debug_error(f"Emailnator generate: {str(e)}", traceback.format_exc())
            return None

    def _refresh_xsrf_from_cookies(self):
        """Atualiza XSRF-TOKEN dos cookies do Session (método A0AUTO)."""
        for cookie in self.session.cookies:
            if cookie.name == 'XSRF-TOKEN':
                new_token = unquote(cookie.value)
                if new_token != self.xsrf_token:
                    self.xsrf_token = new_token
                    log("DEBUG", f"XSRF-TOKEN atualizado via cookies ({len(self.xsrf_token)} chars)")
                return

    def get_messages(self):
        """
        Lista mensagens da inbox.
        V5.0: Retry com re-extração de XSRF em caso de HTTP 419/500.
        Método idêntico ao A0AUTO com tratamento de erros robusto.
        """
        if not self.email:
            return None

        for retry in range(MAX_INBOX_RETRIES):
            try:
                # Garantir que temos XSRF-TOKEN válido
                if not self.xsrf_token:
                    self.extract_xsrf_token()

                url = f"{self.base_url}/message-list"
                payload = {"email": self.email}
                headers = self._get_headers()

                resp = self.session.post(url, json=payload, headers=headers, timeout=30)

                # Atualizar XSRF-TOKEN dos cookies
                self._refresh_xsrf_from_cookies()

                # HTTP 419 = XSRF token expirado (tratamento A0AUTO)
                if resp.status_code == 419:
                    log("WARN", f"message-list HTTP 419 (XSRF expirado), re-extraindo token... (retry {retry+1}/{MAX_INBOX_RETRIES})")
                    debug_event("INBOX 419", f"retry={retry+1}")
                    STATS["inbox_errors"] += 1
                    self.extract_xsrf_token()
                    # Retry imediato com novo token
                    headers = self._get_headers()
                    resp = self.session.post(url, json=payload, headers=headers, timeout=30)
                    self._refresh_xsrf_from_cookies()

                # HTTP 500 = Erro interno do Emailnator (retry com delay)
                if resp.status_code == 500:
                    log("WARN", f"message-list HTTP 500, aguardando 2s e retentando... (retry {retry+1}/{MAX_INBOX_RETRIES})")
                    debug_event("INBOX 500", f"retry={retry+1}, body={resp.text[:200]}")
                    STATS["inbox_errors"] += 1
                    time.sleep(2)
                    # Re-extrair XSRF antes de retry
                    self.extract_xsrf_token()
                    continue

                if resp.status_code == 200:
                    data = resp.json()
                    msgs = data.get("messageData", [])
                    # Log detalhado de cada mensagem na inbox
                    if msgs:
                        for m in msgs:
                            mid = m.get('messageID', '?')
                            mfrom = m.get('from', '?')
                            msubj = m.get('subject', '?')
                            debug_write(f"  [INBOX] ID={mid} | From={mfrom} | Subject={msubj}")
                    return msgs
                else:
                    log("WARN", f"message-list HTTP {resp.status_code} (retry {retry+1}/{MAX_INBOX_RETRIES})")
                    debug_write(f"  [INBOX ERROR] HTTP {resp.status_code}: {resp.text[:300]}")
                    STATS["inbox_errors"] += 1
                    time.sleep(1)

            except Exception as e:
                log("DEBUG", f"get_messages erro (retry {retry+1}): {str(e)}")
                debug_error(f"get_messages retry {retry+1}: {str(e)}")
                time.sleep(1)

        return []

    def get_message_content(self, msg_id):
        """
        Lê o conteúdo completo de um email pelo messageID.
        Método idêntico ao A0AUTO: POST message-list com messageID.
        V5.0: Retry em caso de erro.
        """
        for retry in range(2):
            try:
                if not self.xsrf_token:
                    self.extract_xsrf_token()

                url = f"{self.base_url}/message-list"
                payload = {"email": self.email, "messageID": msg_id}
                headers = self._get_headers()

                resp = self.session.post(url, json=payload, headers=headers, timeout=30)
                self._refresh_xsrf_from_cookies()

                # Tratar 419 com re-extração
                if resp.status_code == 419:
                    log("WARN", f"get_message_content HTTP 419, re-extraindo XSRF...")
                    self.extract_xsrf_token()
                    headers = self._get_headers()
                    resp = self.session.post(url, json=payload, headers=headers, timeout=30)
                    self._refresh_xsrf_from_cookies()

                debug_response(url, resp.status_code, None, resp.text[:3000], f"message_{msg_id}")

                if resp.status_code == 200:
                    return resp.text
                else:
                    log("WARN", f"get_message_content HTTP {resp.status_code}")
                    if retry == 0:
                        time.sleep(1)
                        self.extract_xsrf_token()
                        continue
                return ""
            except Exception as e:
                log("DEBUG", f"get_message_content erro: {str(e)}")
                if retry == 0:
                    time.sleep(1)
                    continue
                return ""
        return ""

    def extract_links(self, html_content):
        """
        Extrai links do conteúdo do email.
        V5.0: Decodifica quoted-printable ANTES de buscar URLs (método A0AUTO).
        """
        if not html_content:
            return []

        # NOVO V5.0: Decodificar quoted-printable (igual ao A0AUTO)
        try:
            decoded_content = quopri.decodestring(html_content.encode()).decode('utf-8', errors='ignore')
        except Exception:
            decoded_content = html_content

        # Buscar URLs no conteúdo decodificado
        links = re.findall(r'href=["\']?(https?://[^\s"\'<>]+)', decoded_content)

        # Também buscar URLs soltas (não em href)
        url_pattern = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+'
        loose_urls = re.findall(url_pattern, decoded_content)

        # Combinar e deduplicar mantendo ordem
        all_links = []
        for link in links + loose_urls:
            # Limpar caracteres finais indesejados
            link = link.rstrip(')').rstrip('\\').rstrip('"').rstrip("'").rstrip(';').rstrip('&')
            if link not in all_links:
                all_links.append(link)

        log("DEBUG", f"Links encontrados no email: {len(all_links)}")
        debug_event(f"Email links extracted: {len(all_links)}")
        for i, link in enumerate(all_links[:25]):
            short = link[:120] + "..." if len(link) > 120 else link
            log("DEBUG", f"  Link [{i}]: {short}")
            debug_write(f"    Link [{i}]: {link}")
        return all_links

    def extract_all_urls_a0auto(self, text):
        """
        Método de extração de URLs IDÊNTICO ao A0AUTO.
        Usado como fallback quando extract_links não encontra o padrão.
        """
        if not text:
            return []
        try:
            decoded_text = quopri.decodestring(text.encode()).decode('utf-8', errors='ignore')
        except Exception:
            decoded_text = text

        url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
        urls = re.findall(url_pattern, decoded_text)

        unique_urls = []
        for u in urls:
            u = u.rstrip(')').rstrip('\\').rstrip('"').rstrip("'")
            if u not in unique_urls:
                unique_urls.append(u)
        return unique_urls

    def find_best_link(self, links, pattern):
        """Encontra o melhor link com o padrão especificado."""
        # Prioridade 1: Link sendgrid que contém o padrão na URL
        for link in links:
            if "sendgrid" in link.lower() and pattern.lower() in link.lower():
                log("OK", f"Link encontrado com padrao '{pattern}' (match direto)")
                return link

        # Prioridade 2: Primeiro link sendgrid que não seja imagem/unsubscribe
        sendgrid_links = [l for l in links if "sendgrid" in l.lower()]
        if sendgrid_links and pattern == "sendgrid":
            for link in sendgrid_links:
                if "unsubscribe" not in link.lower() and "open" not in link.lower():
                    log("OK", f"Link encontrado com padrao '{pattern}'")
                    return link
            log("OK", f"Link encontrado com padrao '{pattern}' (primeiro sendgrid)")
            return sendgrid_links[0]

        # Prioridade 3: Qualquer link que contenha o padrão
        for link in links:
            if pattern.lower() in link.lower():
                log("OK", f"Link encontrado com padrao '{pattern}' (match parcial)")
                return link

        return None

    def find_link_by_index(self, content, target_index=5):
        """
        Método A0AUTO: Extrai o link pelo índice (padrão: #6, índice 5).
        Usado como fallback quando find_best_link não encontra.
        """
        urls = self.extract_all_urls_a0auto(content)
        if len(urls) > target_index:
            target_url = urls[target_index]
            log("OK", f"Link #{target_index+1} encontrado via metodo A0AUTO: {target_url[:80]}...")
            debug_event(f"Link #{target_index+1} via A0AUTO method", target_url)
            return target_url
        log("DEBUG", f"Metodo A0AUTO: apenas {len(urls)} links, precisava de {target_index+1}")
        return None

    def wait_for_email(self, sender_filter="", timeout=60, link_pattern="sendgrid", accept_any=False):
        """
        Aguarda email na inbox com polling adaptativo.
        V5.0: Polling rápido nos primeiros 30s, depois lento.
        V5.0: Fallback via método A0AUTO (link por índice).
        """
        filter_desc = 'QUALQUER' if accept_any else sender_filter
        log("EMAIL", f"Aguardando email de '{filter_desc}' (timeout: {timeout}s)...")
        debug_event(f"Waiting for email from '{filter_desc}'", f"timeout={timeout}s, pattern={link_pattern}, accept_any={accept_any}")

        start = time.time()
        seen_ids = set()
        poll_count = 0

        while time.time() - start < timeout:
            poll_count += 1
            elapsed = time.time() - start

            messages = self.get_messages()

            # Se get_messages retornou None (erro grave), tentar re-extrair token
            if messages is None:
                log("WARN", f"Inbox retornou None no poll #{poll_count}, re-extraindo XSRF...")
                self.extract_xsrf_token()
                time.sleep(2)
                continue

            # Log periódico do estado da inbox
            if poll_count % 3 == 1:
                log("DEBUG", f"Inbox poll #{poll_count}: {len(messages)} mensagens ({int(elapsed)}s/{timeout}s)")

            for msg in messages:
                msg_id = msg.get("messageID", "")
                if msg_id in seen_ids or msg_id == "ADSVPN":
                    continue
                seen_ids.add(msg_id)

                from_addr = msg.get("from", "")
                subject = msg.get("subject", "")
                log("EMAIL", f"Novo email na inbox: De={from_addr} | Assunto={subject}")
                debug_event("New email in inbox", f"From: {from_addr} | Subject: {subject} | ID: {msg_id}")

                # Verificar match
                is_match = False
                if accept_any:
                    spam_keywords = ["samsung", "apple", "newsletter", "promo", "offer", "deal", "unsubscribe", "adsvpn", "cephalon", "welcome to", "verification code"]
                    is_spam = any(kw in from_addr.lower() + subject.lower() for kw in spam_keywords)
                    is_match = not is_spam
                    if is_spam:
                        log("DEBUG", f"Email ignorado (spam): {from_addr}")
                else:
                    # Filtro por remetente/subject - V5.1 CORRIGIDO
                    # IMPORTANTE: NÃO usar termos genéricos como "noreply", "cadastro",
                    # "confirma" etc. pois fazem match com emails de OUTROS serviços!
                    # Usar APENAS termos específicos da Movida.
                    search_terms = [sender_filter.lower()]
                    if "movida" in sender_filter.lower():
                        search_terms.extend([
                            "movida", "vetormovida", "vetormovida@movida.com.br",
                            "fidelidade movida", "movida.com.br"
                        ])
                    combined = (from_addr + " " + subject).lower()
                    is_match = any(term in combined for term in search_terms)

                if is_match:
                    log("EMAIL", f"Email MATCH! De: {from_addr}", f"Subject: {subject}")
                    STATS["emails_recebidos"] += 1

                    content = self.get_message_content(msg_id)
                    if content:
                        # Método 1: extract_links + find_best_link (original)
                        links = self.extract_links(content)
                        link = self.find_best_link(links, link_pattern)
                        if link:
                            return link

                        # Método 2: Fallback sendgrid genérico
                        if link_pattern != "sendgrid":
                            link = self.find_best_link(links, "sendgrid")
                            if link:
                                log("OK", f"Link encontrado via fallback sendgrid")
                                return link

                        # Método 3: Fallback A0AUTO - Link #6
                        link = self.find_link_by_index(content, target_index=5)
                        if link:
                            log("OK", f"Link encontrado via metodo A0AUTO (Link #6)")
                            return link

                        # Método 4: Tentar outros índices (4, 7, 3)
                        for idx in [4, 6, 3, 7, 2]:
                            link = self.find_link_by_index(content, target_index=idx)
                            if link and "sendgrid" in link.lower():
                                log("OK", f"Link SendGrid encontrado no indice #{idx+1}")
                                return link

                        # Método 5: Primeiro link que contenha keywords de confirmação
                        for l in links:
                            if any(x in l.lower() for x in ["confirma", "ativa", "cadastro", "verify", "confirm"]):
                                log("OK", f"Link encontrado via keyword match")
                                return l

                        log("WARN", f"Padrao '{link_pattern}' nao encontrado nos {len(links)} links")
                    else:
                        log("WARN", f"Conteudo do email vazio para ID={msg_id}")

            # Polling adaptativo V5.0: rápido nos primeiros 30s, depois lento
            if elapsed < EMAIL_FAST_PHASE:
                time.sleep(EMAIL_POLL_FAST)
            else:
                time.sleep(EMAIL_POLL_SLOW)

        log("FAIL", f"Timeout {timeout}s esperando email de '{filter_desc}'")
        return None

# ==============================================================================
# 4DEVS - GERADOR DE PESSOA
# ==============================================================================

def gerar_pessoa_4devs():
    log("API", "Gerando pessoa via 4devs...")
    try:
        url = "https://www.4devs.com.br/ferramentas_online.php"
        idade_min = random.randint(21, 45)
        payload = f"acao=gerar_pessoa&sexo=I&pontuacao=S&idade={idade_min}&cep_estado=SP&txt_qtde=1&cep_cidade="
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Referer": "https://www.4devs.com.br/gerador_de_pessoas",
        }
        debug_request("POST", url, headers, payload)
        resp = requests.post(url, data=payload, headers=headers, timeout=15)
        debug_response(url, resp.status_code, dict(resp.headers), resp.text[:600], "4devs_pessoa")

        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                pessoa = data[0]
                log("OK", f"Pessoa gerada: {pessoa.get('nome', '?')}")
                log("DEBUG", f"  CPF: {pessoa.get('cpf')} | Nasc: {pessoa.get('data_nasc')}")
                log("DEBUG", f"  Tel: {pessoa.get('telefone_fixo')} | Cel: {pessoa.get('celular')}")
                log("DEBUG", f"  CEP: {pessoa.get('cep')} | Cidade: {pessoa.get('cidade')}/{pessoa.get('estado')}")
                log("DEBUG", f"  Endereco: {pessoa.get('endereco')}, {pessoa.get('numero')} - {pessoa.get('bairro')}")
                return pessoa
        log("FAIL", f"4devs HTTP {resp.status_code}")
        return None
    except Exception as e:
        log("FAIL", f"4devs erro: {str(e)}")
        debug_error(f"4devs: {str(e)}", traceback.format_exc())
        return None


# ==============================================================================
# CÓDIGO IBGE DA CIDADE
# ==============================================================================

CIDADES_SP_IBGE = {
    "são paulo": "3550308", "sao paulo": "3550308",
    "campinas": "3509502", "guarulhos": "3518800",
    "osasco": "3534401", "santo andré": "3547809", "santo andre": "3547809",
    "são bernardo do campo": "3548708", "sao bernardo do campo": "3548708",
    "ribeirão preto": "3543402", "ribeirao preto": "3543402",
    "sorocaba": "3552205", "santos": "3548500",
    "são josé dos campos": "3549904", "sao jose dos campos": "3549904",
    "jundiaí": "3525904", "jundiai": "3525904",
    "piracicaba": "3538709", "bauru": "3506003",
    "franca": "3516200", "taubaté": "3554102", "taubate": "3554102",
    "limeira": "3526902", "marília": "3529005", "marilia": "3529005",
    "araraquara": "3503208", "presidente prudente": "3541406",
    "são carlos": "3548906", "sao carlos": "3548906",
    "mogi das cruzes": "3530508", "diadema": "3513801",
    "carapicuíba": "3510609", "carapicuiba": "3510609",
    "itaquaquecetuba": "3523107", "mauá": "3529401", "maua": "3529401",
    "são josé do rio preto": "3549805", "sao jose do rio preto": "3549805",
    "barueri": "3505708", "cotia": "3513009",
    "taboão da serra": "3553708", "tabao da serra": "3553708",
    "sumaré": "3552403", "sumare": "3552403",
    "indaiatuba": "3520509", "embu das artes": "3515004",
    "americana": "3501608", "praia grande": "3541000",
    "jacareí": "3524402", "jacarei": "3524402",
    "são vicente": "3551009", "sao vicente": "3551009",
    "hortolândia": "3519071", "hortolandia": "3519071",
    "rio claro": "3543907", "araçatuba": "3502804", "aracatuba": "3502804",
    "ferraz de vasconcelos": "3515707", "santa bárbara d'oeste": "3545803",
    "itapevi": "3522505", "valinhos": "3556206",
    "francisco morato": "3516309", "franco da rocha": "3516408",
    "guarujá": "3518701", "guaruja": "3518701",
    "itatiba": "3523602", "bragança paulista": "3507605",
    "braganca paulista": "3507605", "atibaia": "3504107",
    "cubatão": "3513504", "cubatao": "3513504",
    "votorantim": "3557006", "itu": "3523909",
    "catanduva": "3511102", "assis": "3504008",
    "ourinhos": "3534708", "lins": "3527108",
    "jaú": "3525300", "jau": "3525300",
    "botucatu": "3507506", "tatui": "3554003", "tatuí": "3554003",
    "mogi guaçu": "3530706", "mogi guacu": "3530706",
    "itapetininga": "3522307", "birigui": "3506508",
    "sertãozinho": "3551702", "sertaozinho": "3551702",
    "bebedouro": "3506102", "leme": "3526704",
    "são joão da boa vista": "3549102", "sao joao da boa vista": "3549102",
    "matão": "3529302", "matao": "3529302",
    "votuporanga": "3557105", "tupã": "3555406", "tupa": "3555406",
    "penápolis": "3537305", "penapolis": "3537305",
}

def get_cidade_ibge(cidade_nome):
    nome_lower = cidade_nome.lower().strip()
    nome_norm = unicodedata.normalize('NFKD', nome_lower).encode('ascii', 'ignore').decode('ascii')

    if nome_lower in CIDADES_SP_IBGE:
        return CIDADES_SP_IBGE[nome_lower]
    if nome_norm in CIDADES_SP_IBGE:
        return CIDADES_SP_IBGE[nome_norm]

    for key, code in CIDADES_SP_IBGE.items():
        if nome_norm in key or key in nome_norm:
            return code

    log("WARN", f"Cidade '{cidade_nome}' nao encontrada no mapa IBGE, usando Araraquara")
    return "3503208"

# ==============================================================================
# reCAPTCHA BYPASS V3.0 - FORM-URLENCODED
# ==============================================================================

def solve_recaptcha(action="submit"):
    # Movida usa action='signup' no enterprise.execute()
    if action == 'submit':
        action = 'signup'
    log("CAPTCHA", f"Resolvendo reCAPTCHA V3.0 (action='{action}')...")
    debug_event(f"reCAPTCHA V3.0 solve start", f"action={action}")

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

                c_token_match = re.search(r'id="recaptcha-token"\s*value="(.*?)"', res_anchor.text)
                if not c_token_match:
                    c_token_match = re.search(r'recaptcha-token.*?value="(.*?)"', res_anchor.text)

                if not c_token_match:
                    log("FAIL", f"  [{endpoint}] c-token nao encontrado no anchor")
                    debug_event("c-token not found", f"Response snippet: {res_anchor.text[:500]}")
                    continue

                c_token = c_token_match.group(1)
                log("CAPTCHA", f"  [{endpoint}] c-token obtido ({len(c_token)} chars)")

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
                    log("OK", f"  [{endpoint}] reCAPTCHA RESOLVIDO! ({len(token)} chars)")
                    debug_event("reCAPTCHA solved", f"endpoint={endpoint}, token_length={len(token)}")
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
                                log("OK", f"  [{endpoint}] reCAPTCHA RESOLVIDO via JSON! ({len(token)} chars)")
                                debug_event("reCAPTCHA solved (JSON)", f"endpoint={endpoint}, token_length={len(token)}")
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
                log("FAIL", f"  [{endpoint}] Erro: {str(e)}")
                debug_error(f"reCAPTCHA {endpoint}: {str(e)}", traceback.format_exc())

        # Delay progressivo entre tentativas
        if attempt < 2:
            delay = (attempt + 1) * 2
            log("WARN", f"  Aguardando {delay}s antes da proxima tentativa...")
            time.sleep(delay)

    log("FAIL", "reCAPTCHA FALHOU apos todas as tentativas!")
    return None

# ==============================================================================
# MOVIDA - CADASTRO
# ==============================================================================

def fazer_cadastro(session, pessoa, email, senha, captcha_token):
    """Cadastro na Movida - IDENTICO ao V3.0 que funciona!"""
    log("STEP", "PASSO 5: Enviando cadastro na Movida...")

    # CPF COM pontuacao (identico ao V3.0)
    cpf_formatado = pessoa["cpf"]
    cpf_numeros = re.sub(r'\D', '', cpf_formatado)
    telefone = pessoa.get("telefone_fixo", "(11) 3333-3333")
    celular = pessoa.get("celular", "(11) 99999-9999")
    cidade_ibge = get_cidade_ibge(pessoa.get("cidade", ""))

    log("DEBUG", f"Payload cadastro: CPF={cpf_formatado}, Nome={pessoa['nome']}")
    log("DEBUG", f"  Email={email}, Cidade={pessoa.get('cidade', '?')}/{pessoa.get('estado', '?')}")
    log("DEBUG", f"  CEP={pessoa.get('cep', '?')}, Endereco={pessoa.get('endereco', '?')}, {pessoa.get('numero', '?')}")

    # FORM DATA IDENTICO AO V3.0 (todos os campos na ordem exata)
    form_data = {
        "g-recaptcha-response": captcha_token,
        "isLoginSocial": "",
        "requester": "",
        "tokenRequester": "",
        "partnership": "",
        "nationality": "Brasileiro",
        "nacionalidade": "2",
        "cpf": cpf_formatado,
        "nome": pessoa["nome"],
        "IDNacionalidade": "1007",
        "data_nasc": pessoa["data_nasc"],
        "telefone": telefone,
        "celular": celular,
        "email": email,
        "email_conf": email,
        "cep": pessoa.get("cep", "01001-000"),
        "logradouro": pessoa.get("endereco", "Rua Exemplo"),
        "numero": str(pessoa.get("numero", "100")),
        "complemento": "",
        "bairro": pessoa.get("bairro", "Centro"),
        "Pais": "1",
        "uf": pessoa.get("estado", "SP"),
        "cidade": cidade_ibge,
        "senha_cadastro": senha,
        "senha_conf": senha,
        "participarFidelidade": "1",
        "regulamentoFidelidade": "1",
        "ofertasFidelidade": "1",
        "politicaPrivacidade": "on",
    }

    # HEADERS IDENTICOS AO V3.0 (Android WebView)
    post_headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": MOVIDA_BASE,
        "Referer": f"{MOVIDA_BASE}/usuario/enviar-cadastro",
        "User-Agent": USER_AGENT,
        "X-Requested-With": "com.netsky.vfat.pro",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-language": "en-BR,en;q=0.9,pt-BR;q=0.8,pt;q=0.7,en-US;q=0.6",
        "cache-control": "max-age=0",
        "upgrade-insecure-requests": "1",
        "sec-ch-ua": '"Not:A-Brand";v="99", "Android WebView";v="145", "Chromium";v="145"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-site": "same-origin",
        "sec-fetch-mode": "navigate",
        "sec-fetch-user": "?1",
        "sec-fetch-dest": "document",
    }

    try:
        url = f"{MOVIDA_BASE}/usuario/enviar-cadastro"
        debug_request("POST", url, post_headers, form_data)

        resp = session.post(
            url,
            data=form_data,
            headers=post_headers,
            timeout=30,
            allow_redirects=False
        )

        log("API", f"enviar-cadastro -> HTTP {resp.status_code}")
        debug_response(
            url,
            resp.status_code,
            dict(resp.headers),
            resp.text,
            "enviar_cadastro_POST"
        )
        debug_event("Final URL after redirects", resp.url)
        debug_event("Response history (redirects)", str([r.status_code for r in resp.history]))

        body = resp.text
        body_lower = body.lower()

        # Procurar mensagens JS (toastr, alert, swal)
        js_msgs = re.findall(r'(?:toastr\[.*?\]|toastr\.(?:error|warning|success|info))\s*\(\s*["\']([^"\']+)', body)
        if not js_msgs:
            js_msgs = re.findall(r'(?:alert|showMessage|swal|Swal\.fire)\s*\(\s*["\']([^"\']+)', body)
        if js_msgs:
            for msg in js_msgs:
                log("API", f"  JS Message: {msg[:200]}")
                debug_event("JS alert message", msg)
                if "captcha" in msg.lower() and "inv" in msg.lower():
                    log("FAIL", f"  CAPTCHA INVALIDO detectado: {msg}")
                    return False

        # Detectar sucesso
        has_success_msg = (
            'Cadastro efetuado com sucesso' in body or
            'cadastro efetuado com sucesso' in body_lower or
            'receber um e-mail para confirmar' in body_lower or
            'Bem vindo a Movida' in body
        )

        if has_success_msg:
            log("OK", "Cadastro efetuado com sucesso! (mensagem de sucesso detectada no HTML)")
            debug_event("CADASTRO OK", "Mensagem de sucesso encontrada no HTML")
            return True

        if resp.status_code == 303:
            redirect_url = resp.headers.get('Location', '')
            log("OK", f"Cadastro enviado com sucesso! (HTTP 303 -> {redirect_url})")
            debug_event("CADASTRO OK", f"HTTP 303 redirect to {redirect_url}")
            return True

        if resp.status_code == 200:
            has_form_cadastro = 'name="senha_cadastro"' in body or 'id="formCadastro"' in body
            has_recaptcha_field = 'g-recaptcha-response' in body and 'name="cpf"' in body

            if has_form_cadastro or has_recaptcha_field:
                log("FAIL", "Cadastro FALHOU: formulario de cadastro retornado (erro de validacao)")
                debug_event("CADASTRO FALHOU", "Formulario de cadastro retornado na resposta")

                error_patterns = [
                    r'<div[^>]*class="[^"]*(?:error|alert-danger|invalid-feedback|text-danger)[^"]*"[^>]*>(.*?)</div>',
                    r'<span[^>]*class="[^"]*(?:error|invalid|text-danger)[^"]*"[^>]*>(.*?)</span>',
                    r'<p[^>]*class="[^"]*(?:error|alert|danger)[^"]*"[^>]*>(.*?)</p>',
                    r'toastr\[.*?\]\(["\'](.+?)["\']',
                    r'class="help-block"[^>]*>(.*?)<',
                ]

                found_errors = []
                for pattern in error_patterns:
                    matches = re.findall(pattern, body, re.IGNORECASE | re.DOTALL)
                    for m in matches:
                        clean = re.sub(r'<[^>]+>', '', m).strip()
                        if clean and len(clean) > 3 and len(clean) < 500:
                            found_errors.append(clean)

                if found_errors:
                    for err in found_errors:
                        log("FAIL", f"  Erro encontrado: {err[:200]}")
                else:
                    log("FAIL", "  Nenhuma mensagem de erro especifica encontrada no HTML")

                return False

            if not has_form_cadastro:
                if "confirma" in body_lower or "sucesso" in body_lower or "cadastro realizado" in body_lower:
                    log("OK", "Cadastro enviado com sucesso! (indicacao de sucesso no HTML)")
                    debug_event("CADASTRO OK", "Indicacao de sucesso encontrada no HTML")
                    return True
                log("OK", "Cadastro enviado (pagina diferente do formulario = provavel sucesso)")
                debug_event("CADASTRO PROVAVEL OK", "Pagina retornada nao e o formulario de cadastro")
                return True

        log("FAIL", f"Cadastro falhou HTTP {resp.status_code}")
        debug_event("CADASTRO FALHOU", f"HTTP {resp.status_code}")
        return False

    except Exception as e:
        log("FAIL", f"Erro no cadastro: {str(e)}")
        debug_error(f"Cadastro exception: {str(e)}", traceback.format_exc())
        return False


# ==============================================================================
# MOVIDA - ATIVAÇÃO DE CONTA (V4.0 - CORRIGIDO!)
# ==============================================================================

def ativar_conta(session, confirmation_link, senha):
    """Ativa a conta seguindo o link de confirmação e definindo a senha."""
    log("STEP", "PASSO 7: Ativando conta via link de confirmacao...")
    debug_event("Ativacao iniciada", f"Link: {confirmation_link}")

    try:
        final_url = confirmation_link
        pessoa_id = None

        if "sendgrid" in confirmation_link.lower():
            log("DEBUG", "Link SendGrid detectado, seguindo redirect...")
            debug_request("GET", confirmation_link)

            resp_redirect = session.get(
                confirmation_link,
                allow_redirects=True,
                timeout=20,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
            )

            final_url = str(resp_redirect.url)
            debug_response(confirmation_link, resp_redirect.status_code, dict(resp_redirect.headers), resp_redirect.text[:3000], "sendgrid_redirect")
            debug_event("SendGrid final URL", final_url)
            debug_event("Redirect chain", str([str(r.url) for r in resp_redirect.history]))

            log("OK", f"URL final apos redirect: {final_url[:100]}...")

            id_match = re.search(r'[?&]id=(\d+)', final_url)
            if id_match:
                pessoa_id = id_match.group(1)
                log("OK", f"PessoaID extraido da URL: {pessoa_id}")
                debug_event("PessoaID from URL", pessoa_id)

            if not pessoa_id:
                hash_match = re.search(r'[?&]hash=([a-zA-Z0-9]+)', final_url)
                if hash_match:
                    log("DEBUG", f"Hash encontrado na URL: {hash_match.group(1)}")

            page_html = resp_redirect.text
            if resp_redirect.encoding and 'iso' in resp_redirect.encoding.lower():
                page_html = resp_redirect.content.decode('iso-8859-1', errors='replace')

        else:
            log("DEBUG", "Link direto (nao SendGrid), fazendo GET...")
            debug_request("GET", confirmation_link)
            resp_redirect = session.get(confirmation_link, allow_redirects=True, timeout=20)
            final_url = str(resp_redirect.url)
            page_html = resp_redirect.text
            if resp_redirect.encoding and 'iso' in resp_redirect.encoding.lower():
                page_html = resp_redirect.content.decode('iso-8859-1', errors='replace')
            debug_response(final_url, resp_redirect.status_code, dict(resp_redirect.headers), page_html[:3000], "direct_link_GET")

            id_match = re.search(r'[?&]id=(\d+)', final_url)
            if id_match:
                pessoa_id = id_match.group(1)
                log("OK", f"PessoaID extraido da URL: {pessoa_id}")

        # Extrair PessoaID do HTML se necessário
        if not pessoa_id and page_html:
            id_patterns = [
                r'name=["\']pessoaId["\'].*?value=["\'](\d+)["\']',
                r'name=["\']pessoa_id["\'].*?value=["\'](\d+)["\']',
                r'name=["\']id["\'].*?value=["\'](\d+)["\']',
                r'value=["\'](\d+)["\'].*?name=["\']pessoaId["\']',
                r'value=["\'](\d+)["\'].*?name=["\']id["\']',
                r'pessoaId["\s:=]+["\']?(\d+)',
                r'pessoa_id["\s:=]+["\']?(\d+)',
                r'/confirma_cadastro/?\?id=(\d+)',
                r'confirma_cadastro.*?id=(\d+)',
            ]
            for pattern in id_patterns:
                match = re.search(pattern, page_html, re.IGNORECASE)
                if match:
                    pessoa_id = match.group(1)
                    log("OK", f"PessoaID extraido do HTML: {pessoa_id} (pattern: {pattern[:40]})")
                    debug_event("PessoaID from HTML", f"{pessoa_id} via {pattern[:40]}")
                    break

        if not pessoa_id:
            all_ids = re.findall(r'(?:id|pessoa|user)["\s:=]+["\']?(\d{4,10})', page_html, re.IGNORECASE)
            if all_ids:
                pessoa_id = all_ids[0]
                log("WARN", f"PessoaID extraido por heuristica: {pessoa_id}")
                debug_event("PessoaID heuristic", str(all_ids))

        # POST atualizar-senha
        if not pessoa_id:
            log("WARN", "PessoaID NAO encontrado! Tentando ativacao sem ID...")
            debug_event("PessoaID NOT FOUND", f"URL: {final_url}")
            STATS["ativacoes_fail"] += 1
            return True  # Retorna True para tentar login

        log("STEP", "PASSO 8: Definindo senha via atualizar-senha...")

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
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "pt-BR,pt;q=0.9,en;q=0.8",
            "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Linux"',
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
        }

        debug_request("POST", atualizar_url, atualizar_headers, atualizar_data)
        resp_senha = session.post(atualizar_url, data=atualizar_data, headers=atualizar_headers, timeout=15)

        if resp_senha.encoding and 'iso' in resp_senha.encoding.lower():
            resp_text = resp_senha.content.decode('iso-8859-1', errors='replace')
        else:
            resp_text = resp_senha.text

        debug_response(atualizar_url, resp_senha.status_code, dict(resp_senha.headers), resp_text, "atualizar_senha_POST")
        log("API", f"atualizar-senha -> HTTP {resp_senha.status_code}", resp_text[:300])

        if resp_senha.status_code == 200:
            try:
                data = json.loads(resp_text)
                if data.get("success"):
                    log("OK", "Senha definida com sucesso! Conta ATIVADA!")
                    debug_event("ATIVACAO OK", f"pessoaId={pessoa_id}")
                    STATS["ativacoes_ok"] += 1
                    return True
                else:
                    msg = data.get("msg", "?")
                    log("WARN", f"atualizar-senha retornou success=false: {msg}")
                    debug_event("atualizar-senha FAIL", json.dumps(data, ensure_ascii=False))
                    if "já" in msg.lower() or "already" in msg.lower():
                        log("OK", "Conta ja estava ativada!")
                        STATS["ativacoes_ok"] += 1
                        return True
                    STATS["ativacoes_fail"] += 1
                    return False
            except json.JSONDecodeError:
                if resp_senha.status_code == 200 and ("login" in resp_text.lower() or "sucesso" in resp_text.lower()):
                    log("OK", "Ativacao aparentemente OK (resposta HTML)")
                    STATS["ativacoes_ok"] += 1
                    return True

        if resp_senha.status_code in (302, 303):
            log("OK", f"Ativacao OK! (HTTP {resp_senha.status_code} redirect)")
            STATS["ativacoes_ok"] += 1
            return True

        log("FAIL", f"atualizar-senha HTTP {resp_senha.status_code}")
        STATS["ativacoes_fail"] += 1
        return False

    except Exception as e:
        log("FAIL", f"Erro na ativacao: {str(e)}")
        debug_error(f"Ativacao: {str(e)}", traceback.format_exc())
        STATS["ativacoes_fail"] += 1
        return False

# ==============================================================================
# MOVIDA - LOGIN
# ==============================================================================

def fazer_login(session, cpf_numeros, senha, referer_url=None):
    log("STEP", "PASSO 9: Fazendo login na Movida...")

    captcha = solve_recaptcha(action="login")
    if not captcha:
        log("FAIL", "Falha ao resolver reCAPTCHA para login")
        return None, "captcha_fail"

    if not referer_url:
        referer_url = f"{MOVIDA_BASE}/usuario/login"

    try:
        url_login = f"{MOVIDA_BASE}/login_site"
        login_data = {
            "cpf": cpf_numeros,
            "senha": senha,
            "requester": "",
            "tokenRequester": "",
            "V2": "",
            "g-recaptcha-response": captcha,
        }
        login_headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "Origin": MOVIDA_BASE,
            "Referer": referer_url,
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "accept-language": "en-BR,en;q=0.9,pt-BR;q=0.8,pt;q=0.7,en-US;q=0.6",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Android WebView";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
        }

        debug_request("POST", url_login, login_headers, login_data)
        resp = session.post(url_login, data=login_data, headers=login_headers, timeout=15)
        debug_response(url_login, resp.status_code, dict(resp.headers), resp.text, "login_site_POST")

        log("API", f"login_site -> HTTP {resp.status_code}", resp.text[:300])

        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                user_token = data.get("token", "")
                user_id = data.get("user_id", "")
                nome = data.get("nome", "")
                cpf_resp = data.get("cpf", "")
                email_resp = data.get("email", "")
                log("OK", f"Login OK! Nome: {nome}, UserID: {user_id}")
                log("TOKEN", f"USER-TOKEN DIRETO DO LOGIN: {user_token}")
                log("DEBUG", f"CPF: {cpf_resp}, Email: {email_resp}")
                debug_event("LOGIN OK + TOKEN", f"nome={nome}, user_id={user_id}, token={user_token}, cpf={cpf_resp}")

                if user_token and len(user_token) > 10:
                    return user_token, "ok"

                log("WARN", "Token nao veio no login, tentando webcheckin/token...")
                wc_token = extrair_user_token_webcheckin(data.get("token", ""))
                if wc_token:
                    return wc_token, "ok"

                return user_token or "LOGIN_OK_NO_TOKEN", "ok"
            else:
                msg = data.get("msg", "").lower()
                log("WARN", f"Login falhou: {data.get('msg', '?')}")
                debug_event("LOGIN FAILED", json.dumps(data, ensure_ascii=False))

                if "confirmado" in msg or "confirmar" in msg or "confirma" in msg:
                    return None, "nao_confirmado"
                if "senha" in msg or "inválido" in msg or "invalido" in msg:
                    return None, "senha_invalida"
                if "complete" in msg or "has_to_complete" in str(data):
                    return None, "incomplete_data"
                return None, "unknown_error"

        log("FAIL", f"Login HTTP {resp.status_code}")
        return None, "http_error"

    except Exception as e:
        log("FAIL", f"Erro no login: {str(e)}")
        debug_error(f"Login: {str(e)}", traceback.format_exc())
        return None, "exception"

# ==============================================================================
# MOVIDA - EXTRAIR USER-TOKEN VIA WEBCHECKIN (FALLBACK)
# ==============================================================================

def extrair_user_token_webcheckin(grant_token):
    log("STEP", "Extraindo user-token via webcheckin/token...")
    try:
        url_token = f"{BFF_BASE}/api/v1/webcheckin/token"
        token_data = {"_token": grant_token}
        token_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": MOVIDA_BASE,
            "Referer": f"{MOVIDA_BASE}/webcheckin/meus-cartoes",
            "User-Agent": USER_AGENT,
            "X-Requested-With": "com.netsky.vfat.pro",
            "accept-language": "en-BR,en;q=0.9,pt-BR;q=0.8,pt;q=0.7,en-US;q=0.6",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Android WebView";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
        }

        debug_request("POST", url_token, token_headers, token_data)
        resp = requests.post(url_token, json=token_data, headers=token_headers, timeout=15)
        debug_response(url_token, resp.status_code, dict(resp.headers), resp.text, "webcheckin_token_POST")

        log("API", f"webcheckin/token -> HTTP {resp.status_code}", resp.text[:300])

        if resp.status_code == 200:
            data = resp.json()
            if not data.get("error") and data.get("data", {}).get("token"):
                user_token = data["data"]["token"]
                log("TOKEN", f"USER-TOKEN EXTRAIDO! {user_token[:20]}...{user_token[-10:]}")
                debug_event("USER-TOKEN EXTRACTED", user_token)
                return user_token
            else:
                log("FAIL", f"webcheckin/token erro: {data}")
        return None
    except Exception as e:
        log("FAIL", f"Erro webcheckin/token: {str(e)}")
        debug_error(f"webcheckin/token: {str(e)}", traceback.format_exc())
        return None

# ==============================================================================
# MOVIDA - RECUPERAÇÃO DE SENHA (FALLBACK)
# ==============================================================================

def recuperar_senha(session, emailnator, cpf_numeros, email, nova_senha):
    log("STEP", "RECUPERACAO DE SENHA: Iniciando fluxo...")
    debug_event("Password recovery started", f"cpf={cpf_numeros}, email={email}")
    STATS["senhas_recuperadas"] += 1

    try:
        url_recuperar = f"{BFF_BASE}/api/v1/usuario/recuperar-senha"
        recuperar_data = {"cpf": cpf_numeros, "tipo": "email"}
        recuperar_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": MOVIDA_BASE,
            "Referer": f"{MOVIDA_BASE}/webcheckin/meus-cartoes",
            "User-Agent": USER_AGENT,
        }

        debug_request("POST", url_recuperar, recuperar_headers, recuperar_data)
        resp = requests.post(url_recuperar, json=recuperar_data, headers=recuperar_headers, timeout=15)
        debug_response(url_recuperar, resp.status_code, dict(resp.headers), resp.text, "recuperar_senha_POST")

        log("API", f"recuperar-senha -> HTTP {resp.status_code}", resp.text[:300])

        if resp.status_code == 200:
            data = resp.json()
            if data.get("success"):
                log("OK", "Email de recuperacao solicitado!")
            else:
                log("WARN", f"Recuperacao falhou: {data.get('msg', '?')}")
                return False
        else:
            log("FAIL", f"recuperar-senha HTTP {resp.status_code}")
            return False

        log("EMAIL", "Aguardando email de recuperacao de senha...")

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
        return ativar_conta(session, link, nova_senha)

    except Exception as e:
        log("FAIL", f"Erro na recuperacao: {str(e)}")
        debug_error(f"Recuperacao: {str(e)}", traceback.format_exc())
        return False

# ==============================================================================
# SALVAR TOKEN
# ==============================================================================

def salvar_token(user_token, cpf_numeros):
    try:
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(f"{user_token}\n{cpf_numeros}\n")
        log("TOKEN", f"Token salvo em {OUTPUT_FILE}")
        log("TOKEN", f"  user-token: {user_token[:20]}...{user_token[-10:] if len(user_token) > 20 else user_token}")
        log("TOKEN", f"  cpf: {cpf_numeros}")
        debug_event("TOKEN SAVED", f"file={OUTPUT_FILE}, token={user_token}, cpf={cpf_numeros}")
        return True
    except Exception as e:
        log("FAIL", f"Erro ao salvar token: {str(e)}")
        debug_error(f"Salvar token: {str(e)}", traceback.format_exc())
        return False


# ==============================================================================
# CICLO PRINCIPAL - GERAÇÃO DE 1 TOKEN COMPLETO (V5.0)
# ==============================================================================

def gerar_um_token():
    CURRENT_CYCLE["num"] += 1
    cycle = CURRENT_CYCLE["num"]
    log_separator(f"NOVO CICLO DE GERACAO (Token #{STATS['tokens_gerados']+1})")

    # ==========================================
    # PASSO 1: Gerar Gmail temporário (com rotação de tipo)
    # ==========================================
    log("STEP", "PASSO 1: Gerando Gmail temporario (Emailnator)...")
    emailnator = Emailnator()
    email = None

    email_type_idx = (CURRENT_CYCLE["num"] - 1) % len(EMAIL_TYPES_PRIORITY)
    email_type = EMAIL_TYPES_PRIORITY[email_type_idx]

    for attempt in range(3):
        current_type = EMAIL_TYPES_PRIORITY[(email_type_idx + attempt) % len(EMAIL_TYPES_PRIORITY)]
        email = emailnator.generate_email(email_type=current_type)
        if email:
            break
        log("WARN", f"Tentativa {attempt+1}/3 com tipo '{current_type}' falhou, retentando...")
        time.sleep(1)
        emailnator.reset_session()

    if not email:
        log("FAIL", "Impossivel gerar email temporario!")
        STATS["cadastros_fail"] += 1
        debug_event("CYCLE FAILED", "Cannot generate email")
        return False

    # ==========================================
    # PASSO 1B (NOVO V5.0): Verificar inbox inicial
    # ==========================================
    log("DEBUG", "Verificando inbox inicial (pre-cadastro)...")
    initial_msgs = emailnator.get_messages()
    if initial_msgs is not None:
        log("DEBUG", f"Inbox inicial: {len(initial_msgs)} mensagens")
    else:
        log("WARN", "Inbox inicial retornou None, re-extraindo XSRF...")
        emailnator.extract_xsrf_token()
        initial_msgs = emailnator.get_messages()
        if initial_msgs is not None:
            log("DEBUG", f"Inbox inicial (retry): {len(initial_msgs)} mensagens")
        else:
            log("WARN", "Inbox ainda None! Continuando mesmo assim...")

    # ==========================================
    # PASSO 2: Gerar pessoa fake (4devs)
    # ==========================================
    log("STEP", "PASSO 2: Gerando dados de pessoa (4devs)...")
    pessoa = None
    for attempt in range(3):
        pessoa = gerar_pessoa_4devs()
        if pessoa:
            break
        log("WARN", f"4devs tentativa {attempt+1}/3 falhou")
        time.sleep(2)

    if not pessoa:
        log("FAIL", "Impossivel gerar pessoa no 4devs!")
        STATS["cadastros_fail"] += 1
        debug_event("CYCLE FAILED", "Cannot generate person")
        return False

    cpf_numeros = re.sub(r'\D', '', pessoa["cpf"])

    # Iniciar sessão de debug
    CURRENT_CYCLE["email"] = email
    CURRENT_CYCLE["cpf"] = cpf_numeros
    CURRENT_CYCLE["nome"] = pessoa["nome"]
    debug_session_start(cycle, email, pessoa["cpf"], pessoa["nome"])
    debug_event("Pessoa completa", json.dumps(pessoa, ensure_ascii=False, indent=2))

    # ==========================================
    # PASSO 3: Gerar senha segura
    # ==========================================
    log("STEP", "PASSO 3: Gerando senha segura...")
    senha = gerar_senha()
    log("OK", f"Senha gerada: {senha}")
    debug_event("Senha gerada", senha)

    # ==========================================
    # PASSO 4: Criar sessão Movida
    # ==========================================
    log("STEP", "PASSO 4: Carregando pagina de cadastro (sessao + cookies)...")
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    try:
        url_cadastro = f"{MOVIDA_BASE}/usuario/cadastro"
        get_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
            "accept-language": "en-BR,en;q=0.9,pt-BR;q=0.8,pt;q=0.7,en-US;q=0.6",
            "upgrade-insecure-requests": "1",
            "sec-ch-ua": '"Not:A-Brand";v="99", "Android WebView";v="145", "Chromium";v="145"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
            "sec-fetch-site": "none",
            "sec-fetch-mode": "navigate",
            "sec-fetch-user": "?1",
            "sec-fetch-dest": "document",
            "X-Requested-With": "com.netsky.vfat.pro",
        }
        debug_request("GET", url_cadastro, get_headers)
        resp_page = session.get(url_cadastro, headers=get_headers, timeout=30)
        debug_response(url_cadastro, resp_page.status_code, dict(resp_page.headers), resp_page.text[:3000], "cadastro_page_GET")
        debug_event("Session cookies after GET cadastro", str(dict(session.cookies)))
        log("OK", f"Pagina carregada! PHPSESSID obtido. Cookies: {len(session.cookies)}")
    except Exception as e:
        log("FAIL", f"Erro ao carregar pagina de cadastro: {e}")
        STATS["cadastros_fail"] += 1
        return False

    # ==========================================
    # PASSO 5-6: Resolver reCAPTCHA + Enviar cadastro
    # ==========================================
    cadastro_ok = False
    for cadastro_attempt in range(3):
        log("STEP", f"PASSO 5: Resolvendo reCAPTCHA V3.0 (tentativa {cadastro_attempt+1}/3)...")
        captcha_token = solve_recaptcha(action="signup")
        if not captcha_token:
            log("FAIL", "Falha no reCAPTCHA para cadastro!")
            continue

        log("STEP", f"PASSO 6: Enviando cadastro na Movida (tentativa {cadastro_attempt+1}/3)...")
        cadastro_ok = fazer_cadastro(session, pessoa, email, senha, captcha_token)
        if cadastro_ok:
            break

        if cadastro_attempt < 2:
            log("WARN", f"Cadastro falhou (tentativa {cadastro_attempt+1}/3). Gerando novo token reCAPTCHA...")
            time.sleep(2)

    if not cadastro_ok:
        log("FAIL", "Cadastro falhou apos 3 tentativas!")
        STATS["cadastros_fail"] += 1
        return False

    STATS["cadastros_ok"] += 1

    # ==========================================
    # PASSO 6B: Aguardar email de confirmação (V5.1 - CORRIGIDO!)
    # ==========================================
    log("STEP", "PASSO 6B: Aguardando email de confirmacao da Movida...")
    log("INFO", f"Email: {email} | Timeout: {EMAIL_CONFIRM_TIMEOUT}s | Poll rapido: {EMAIL_POLL_FAST}s (primeiros {EMAIL_FAST_PHASE}s)")
    log("INFO", f"Remetente esperado: vetormovida@movida.com.br")

    # V5.1: Re-extrair XSRF-TOKEN ANTES de começar o polling
    # (o token pode ter expirado durante o cadastro)
    log("DEBUG", "Re-extraindo XSRF-TOKEN antes do polling de inbox...")
    emailnator.extract_xsrf_token()

    # Tentativa 1: Buscar email da Movida (identico ao V3.0)
    confirmation_link = emailnator.wait_for_email(
        sender_filter="Movida",
        timeout=EMAIL_CONFIRM_TIMEOUT,
        link_pattern="sendgrid"
    )

    # Tentativa 2: Retry com padrao confirma_cadastro (identico ao V3.0)
    if not confirmation_link:
        log("WARN", "Tentando buscar link via padrao confirma_cadastro...")
        confirmation_link = emailnator.wait_for_email(
            sender_filter="Movida",
            timeout=15,
            link_pattern="confirma_cadastro"
        )

    # Tentativa 3: Qualquer email com sendgrid (identico ao V3.0)
    if not confirmation_link:
        log("WARN", "Tentando buscar qualquer link sendgrid...")
        confirmation_link = emailnator.wait_for_email(
            sender_filter="movida",
            timeout=10,
            link_pattern="sendgrid"
        )

    if not confirmation_link:
        log("FAIL", f"Email de confirmacao nao chegou em {EMAIL_CONFIRM_TIMEOUT}s!")
        log("WARN", "Limpando tudo e recomecando com novo email...")
        STATS["emails_timeout"] += 1
        debug_event("EMAIL TIMEOUT", f"No confirmation email in {EMAIL_CONFIRM_TIMEOUT}s")
        return False

    log("OK", f"Link de confirmacao recebido!")

    # ==========================================
    # PASSO 7-8: Ativar conta + definir senha
    # ==========================================
    ativacao_ok = ativar_conta(session, confirmation_link, senha)
    if not ativacao_ok:
        log("WARN", "Ativacao falhou, mas tentando login mesmo assim...")

    # DELAY CRÍTICO
    log("INFO", f"Aguardando {ACTIVATION_DELAY}s para propagacao no backend...")
    time.sleep(ACTIVATION_DELAY)

    confirma_referer = None
    id_match = re.search(r'id=(\d+)', confirmation_link)
    if id_match:
        confirma_referer = f"{MOVIDA_BASE}/usuario/confirma_cadastro/?id={id_match.group(1)}"
        log("DEBUG", f"Referer para login: {confirma_referer}")

    # ==========================================
    # PASSO 9: Login (com reativação e recuperação de senha)
    # ==========================================
    user_token = None
    login_attempts = 0
    reactivation_attempts = 0

    while login_attempts < MAX_LOGIN_RETRIES and user_token is None:
        login_attempts += 1
        log("INFO", f"Tentativa de login {login_attempts}/{MAX_LOGIN_RETRIES}...")

        user_token, status = fazer_login(session, cpf_numeros, senha, referer_url=confirma_referer)

        if user_token:
            break

        if status == "nao_confirmado":
            if reactivation_attempts < MAX_REACTIVATION_ATTEMPTS:
                reactivation_attempts += 1
                STATS["reativacoes"] += 1
                log("WARN", f"CONTA NAO CONFIRMADA! Tentando reativacao #{reactivation_attempts}...")
                debug_event("REACTIVATION ATTEMPT", f"attempt={reactivation_attempts}")

                reativ_ok = ativar_conta(session, confirmation_link, senha)
                if reativ_ok:
                    log("OK", "Reativacao feita! Aguardando propagacao...")
                    time.sleep(ACTIVATION_DELAY + 2)
                    continue
                else:
                    log("WARN", "Reativacao falhou, tentando recuperacao de senha...")
                    nova_senha = gerar_senha()
                    recover_ok = recuperar_senha(session, emailnator, cpf_numeros, email, nova_senha)
                    if recover_ok:
                        senha = nova_senha
                        log("OK", "Senha recuperada! Tentando login novamente...")
                        time.sleep(ACTIVATION_DELAY)
                        continue
            else:
                log("FAIL", f"Reativacao esgotada ({MAX_REACTIVATION_ATTEMPTS} tentativas)")
                nova_senha = gerar_senha()
                recover_ok = recuperar_senha(session, emailnator, cpf_numeros, email, nova_senha)
                if recover_ok:
                    senha = nova_senha
                    time.sleep(ACTIVATION_DELAY)
                    continue
                break

        elif status == "senha_invalida":
            log("WARN", "BUG DE SENHA INVALIDA DETECTADO! Iniciando recuperacao...")
            debug_event("PASSWORD BUG DETECTED", f"Attempt {login_attempts}")

            nova_senha = gerar_senha()
            log("INFO", f"Nova senha para recuperacao: {nova_senha}")
            debug_event("New password for recovery", nova_senha)

            recover_ok = recuperar_senha(session, emailnator, cpf_numeros, email, nova_senha)
            if recover_ok:
                senha = nova_senha
                log("OK", "Senha recuperada! Tentando login novamente...")
                time.sleep(ACTIVATION_DELAY)
            else:
                log("FAIL", "Recuperacao de senha falhou!")
                break

        elif status == "incomplete_data":
            log("WARN", "Conta precisa completar dados, tentando login direto...")
            time.sleep(2)

        elif status == "captcha_fail":
            log("WARN", "reCAPTCHA falhou, retentando...")
            time.sleep(2)

        else:
            log("WARN", f"Login falhou com status: {status}")
            time.sleep(2)

    if not user_token:
        log("FAIL", "Impossivel fazer login apos todas as tentativas!")
        debug_event("LOGIN FAILED ALL ATTEMPTS", f"attempts={login_attempts}, reactivations={reactivation_attempts}")
        return False

    # ==========================================
    # PASSO 10: Salvar token
    # ==========================================
    salvo = salvar_token(user_token, cpf_numeros)
    if salvo:
        STATS["tokens_gerados"] += 1
        log_separator("TOKEN GERADO COM SUCESSO!")
        log("TOKEN", f"#{STATS['tokens_gerados']} | CPF: {cpf_numeros} | Email: {email}")
        log("TOKEN", f"user-token: {user_token}")
        debug_separator(f"TOKEN #{STATS['tokens_gerados']} GERADO COM SUCESSO!")
        debug_write(f"CPF: {cpf_numeros}")
        debug_write(f"Email: {email}")
        debug_write(f"user-token: {user_token}")
        return True

    return False

# ==============================================================================
# MAIN - LOOP INFINITO COM DASHBOARD
# ==============================================================================

def main():
    os.system("clear")
    print(f"""
{C.MG}{C.B}+============================================================+
|  AJATO TOKEN GENERATOR V6.1 - NETHUNTER EDITION           |
|  Emailnator + 4devs + reCAPTCHA Bypass + Movida Auto      |
|  --------------------------------------------------------  |
|  [FIX] reCAPTCHA ENTERPRISE (endpoint enterprise first!)  |
|  [FIX] Campos fidelidade: participar + regulamento         |
|  [FIX] CADASTRO REESCRITO (identico ao V3.0 funcional!)   |
|  [FIX] Headers: Android WebView/145 (nao mais Linux)      |
|  [FIX] CPF COM pontuacao + email_conf + senha_cadastro     |
|  [FIX] X-Requested-With: com.netsky.vfat.pro              |
|  [FIX] XSRF-TOKEN via cookies + HTTP 419/500 retry        |
|  [FIX] Decodificacao quopri para links SendGrid           |
|  Arquivos: /sdcard/nh_files/                               |
|  Pressione CTRL+C para parar                               |
+============================================================+{C.R}
""")

    # Inicializar arquivo de debug
    debug_separator(f"SESSAO INICIADA | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    debug_write(f"Platform: Kali Linux NetHunter")
    debug_write(f"Script version: V6.1 (Enterprise reCAPTCHA + Fidelidade Fix)")
    debug_write(f"Output tokens: {OUTPUT_FILE}")
    debug_write(f"Debug logs: {DEBUG_LOG_FILE}")
    debug_write(f"reCAPTCHA v={RECAPTCHA_V}")
    debug_write(f"reCAPTCHA bypass: enterprise/reload FIRST, then api2 fallback")
    debug_write(f"Email confirm timeout: {EMAIL_CONFIRM_TIMEOUT}s")
    debug_write(f"Email poll fast: {EMAIL_POLL_FAST}s (primeiros {EMAIL_FAST_PHASE}s)")
    debug_write(f"Email poll slow: {EMAIL_POLL_SLOW}s")
    debug_write(f"Recover timeout: {EMAIL_RECOVER_TIMEOUT}s")
    debug_write(f"Activation delay: {ACTIVATION_DELAY}s")
    debug_write(f"Max login retries: {MAX_LOGIN_RETRIES}")
    debug_write(f"Max reactivation attempts: {MAX_REACTIVATION_ATTEMPTS}")
    debug_write(f"Max inbox retries: {MAX_INBOX_RETRIES}")
    debug_write(f"Emailnator UA: {EMAILNATOR_UA}")
    debug_write(f"Movida UA: {USER_AGENT}")
    debug_write("")

    log("INFO", f"Output tokens: {OUTPUT_FILE}")
    log("INFO", f"Debug logs: {C.Y}{DEBUG_LOG_FILE}{C.R}")
    log("INFO", f"reCAPTCHA bypass: enterprise/reload FIRST, api2 fallback")
    log("INFO", f"reCAPTCHA v={RECAPTCHA_V[:15]}... | key={RECAPTCHA_SITE_KEY[:15]}...")
    log("INFO", f"Email timeout: {EMAIL_CONFIRM_TIMEOUT}s | Poll: {EMAIL_POLL_FAST}s/{EMAIL_POLL_SLOW}s | Recover: {EMAIL_RECOVER_TIMEOUT}s")
    log("INFO", f"Remetente Movida: vetormovida@movida.com.br (filtro exato)")
    log("INFO", f"Activation delay: {ACTIVATION_DELAY}s | Max retries: {MAX_LOGIN_RETRIES}")
    log("INFO", f"Emailnator UA: Chrome/135 Windows (igual A0AUTO)")
    log("INFO", f"Movida UA: Android WebView/145 (identico V3.0)")
    log("INFO", f"Cadastro: form data + headers IDENTICOS ao V3.0 funcional")
    log("INFO", "Iniciando geracao automatica de tokens...\n")

    # Teste inicial do bypass
    log("STEP", "Teste inicial do bypass reCAPTCHA V3.0...")
    test_token = solve_recaptcha(action="signup")
    if not test_token:
        log("FAIL", "BYPASS reCAPTCHA NAO FUNCIONA! Verifique sua conexao.")
        log("FAIL", "O bypass precisa acessar www.google.com/recaptcha/ diretamente.")
        input(f"\n{C.Y}Pressione ENTER para tentar mesmo assim...{C.R}")
    else:
        log("OK", f"Bypass V3.0 OK! Token de teste: {len(test_token)} chars")

    # V5.0: Teste inicial do Emailnator
    log("STEP", "Teste inicial do Emailnator...")
    test_emailnator = Emailnator()
    test_email = test_emailnator.generate_email(email_type="dotGmail")
    if test_email:
        log("OK", f"Emailnator OK! Email de teste: {test_email}")
        # Testar inbox
        test_msgs = test_emailnator.get_messages()
        if test_msgs is not None:
            log("OK", f"Inbox OK! {len(test_msgs)} mensagens iniciais")
        else:
            log("WARN", "Inbox retornou None no teste, mas continuando...")
    else:
        log("FAIL", "Emailnator FALHOU no teste! Verifique sua conexao.")
        input(f"\n{C.Y}Pressione ENTER para tentar mesmo assim...{C.R}")

    print()

    ciclo = 0
    while True:
        ciclo += 1
        try:
            sucesso = gerar_um_token()

            if not sucesso:
                log("WARN", f"Ciclo #{ciclo} falhou. Aguardando 5s antes de recomecar...")
                time.sleep(5)
            else:
                log("INFO", f"Ciclo #{ciclo} concluido com sucesso! Proximo em 3s...")
                time.sleep(3)

            log_stats()

        except KeyboardInterrupt:
            print(f"\n\n{C.Y}{C.B}[CTRL+C] Parando...{C.R}")
            log_stats()
            log_separator("SESSAO ENCERRADA")
            debug_separator("SESSAO ENCERRADA")
            debug_write(f"Total tokens: {STATS['tokens_gerados']}")
            debug_write(f"Total cadastros OK: {STATS['cadastros_ok']}")
            debug_write(f"Total ativacoes OK: {STATS['ativacoes_ok']}")
            debug_write(f"Total emails recebidos: {STATS['emails_recebidos']}")
            debug_write(f"Total fails: {STATS['cadastros_fail']}")
            debug_write(f"Total inbox errors: {STATS['inbox_errors']}")
            debug_write(f"Total reativacoes: {STATS['reativacoes']}")
            log("INFO", f"Total de tokens gerados: {STATS['tokens_gerados']}")
            log("INFO", f"Salvos em: {OUTPUT_FILE}")
            log("INFO", f"Debug logs em: {DEBUG_LOG_FILE}")
            break
        except Exception as e:
            log("FAIL", f"ERRO INESPERADO no ciclo #{ciclo}: {str(e)}")
            debug_error(f"Unexpected error cycle #{ciclo}: {str(e)}", traceback.format_exc())
            traceback.print_exc()
            log("WARN", "Aguardando 10s antes de recomecar...")
            time.sleep(10)

    input(f"\n{C.Y}Pressione ENTER para fechar...{C.R}")

if __name__ == "__main__":
    main()
