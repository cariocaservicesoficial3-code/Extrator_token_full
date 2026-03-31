#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AJATO TOKEN GENERATOR V7.1 - Sistema de Logging Completo
Terminal colorido + debug detalhado + compressão ZIP.

LOGS SALVOS EM: /sdcard/nh_files/logs/
  - DEBUG_LOGS_GEN_TOKENS.txt  -> Log principal (tudo)
  - PLAYWRIGHT_DEBUG.txt       -> Ações do Playwright (navegação, cliques, HTML)
  - HTTP_REQUESTS.txt          -> Requests/Responses HTTP detalhados
  - CYCLE_HISTORY.txt          -> Histórico resumido de cada ciclo
  - screenshots/               -> Screenshots de debug
  - *.zip                      -> Pacotes comprimidos por ciclo/sessão
"""

import os
import re
import time
import json
import shutil
import zipfile
import traceback
from datetime import datetime

from config import (
    C, LOGS_DIR, SCREENSHOTS_DIR,
    DEBUG_LOG_FILE, PW_LOG_FILE, HTTP_LOG_FILE, CYCLE_LOG_FILE,
    BASE_DIR,
)


# ==============================================================================
# CONTADORES GLOBAIS
# ==============================================================================
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
    "logins_ok": 0,
    "logins_fail": 0,
    "start_time": time.time(),
}

CURRENT_CYCLE = {"num": 0, "email": "", "cpf": "", "nome": "", "start_time": 0}

# Session ID para organizar ZIPs
SESSION_ID = datetime.now().strftime("%Y%m%d_%H%M%S")


# ==============================================================================
# FUNÇÕES DE ESCRITA EM ARQUIVO
# ==============================================================================

def _clean_ansi(text):
    """Remove códigos ANSI de cores."""
    return re.sub(r'\033\[[0-9;]*m', '', str(text))


def _write_file(filepath, text):
    """Escreve no arquivo de forma segura."""
    try:
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(_clean_ansi(text) + "\n")
    except Exception:
        pass


def debug_write(text):
    """Escreve no arquivo de debug principal."""
    _write_file(DEBUG_LOG_FILE, text)


def pw_write(text):
    """Escreve no arquivo de debug do Playwright."""
    _write_file(PW_LOG_FILE, text)


def http_write(text):
    """Escreve no arquivo de debug HTTP."""
    _write_file(HTTP_LOG_FILE, text)


def cycle_write(text):
    """Escreve no arquivo de histórico de ciclos."""
    _write_file(CYCLE_LOG_FILE, text)


# ==============================================================================
# DEBUG DETALHADO - SESSÃO
# ==============================================================================

def debug_separator(title=""):
    """Separador visual nos logs."""
    lines = "=" * 80
    debug_write(f"\n{lines}")
    if title:
        debug_write(f"  {title}")
        debug_write(lines)
    debug_write("")


def debug_session_start(cycle_num, email, cpf, nome):
    """Registra início de um ciclo com todos os dados."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    CURRENT_CYCLE.update({
        "num": cycle_num, "email": email,
        "cpf": cpf, "nome": nome,
        "start_time": time.time(),
    })

    debug_separator(f"CICLO #{cycle_num} | {ts}")
    debug_write(f"Email: {email}")
    debug_write(f"CPF: {cpf}")
    debug_write(f"Nome: {nome}")
    debug_write(f"Session ID: {SESSION_ID}")
    debug_write("")

    # Log no histórico de ciclos
    cycle_write(f"\n{'='*60}")
    cycle_write(f"CICLO #{cycle_num} | {ts}")
    cycle_write(f"  Email: {email}")
    cycle_write(f"  CPF: {cpf}")
    cycle_write(f"  Nome: {nome}")

    # Log no Playwright
    pw_write(f"\n{'='*60}")
    pw_write(f"CICLO #{cycle_num} | {ts}")
    pw_write(f"{'='*60}")

    # Log no HTTP
    http_write(f"\n{'='*60}")
    http_write(f"CICLO #{cycle_num} | {ts}")
    http_write(f"{'='*60}")


def debug_session_end(cycle_num, success, token="", error=""):
    """Registra fim de um ciclo."""
    elapsed = time.time() - CURRENT_CYCLE.get("start_time", time.time())
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCESSO" if success else "FALHA"

    debug_write(f"\n--- CICLO #{cycle_num} FINALIZADO: {status} ({elapsed:.1f}s) ---")
    if token:
        debug_write(f"  Token: {token[:40]}...")
    if error:
        debug_write(f"  Erro: {error}")
    debug_write("")

    # Histórico de ciclos
    cycle_write(f"  Status: {status}")
    cycle_write(f"  Duracao: {elapsed:.1f}s")
    if token:
        cycle_write(f"  Token: {token[:40]}...")
    if error:
        cycle_write(f"  Erro: {error}")
    cycle_write(f"  Fim: {ts}")
    cycle_write(f"{'='*60}")


# ==============================================================================
# DEBUG DETALHADO - HTTP REQUESTS/RESPONSES
# ==============================================================================

def debug_request(method, url, headers=None, body=None):
    """Log detalhado de request HTTP (como V6.1 original)."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] >>> REQUEST: {method} {url}"
    debug_write(line)
    http_write(line)

    if headers:
        debug_write("  HEADERS:")
        http_write("  HEADERS:")
        for k, v in headers.items():
            v_str = str(v)
            if k.lower() == "g-recaptcha-response" or len(v_str) > 500:
                entry = f"    {k}: {v_str[:80]}...({len(v_str)} chars)"
            else:
                entry = f"    {k}: {v_str}"
            debug_write(entry)
            http_write(entry)

    if body:
        if isinstance(body, dict):
            debug_write("  BODY (dict):")
            http_write("  BODY (dict):")
            for k, v in body.items():
                v_str = str(v)
                if len(v_str) > 200:
                    entry = f"    {k}: {v_str[:200]}...({len(v_str)} chars)"
                else:
                    entry = f"    {k}: {v_str}"
                debug_write(entry)
                http_write(entry)
        elif isinstance(body, str):
            if len(body) > 2000:
                debug_write(f"  BODY (raw, {len(body)} chars):")
                debug_write(f"    {body[:2000]}...")
                http_write(f"  BODY (raw, {len(body)} chars):")
                http_write(f"    {body[:2000]}...")
            else:
                debug_write(f"  BODY (raw): {body}")
                http_write(f"  BODY (raw): {body}")
        elif isinstance(body, bytes):
            debug_write(f"  BODY (bytes, {len(body)} bytes): {body[:200]}")
            http_write(f"  BODY (bytes, {len(body)} bytes): {body[:200]}")

    debug_write("")
    http_write("")


def debug_response(url, status_code, headers=None, body="", label=""):
    """Log detalhado de response HTTP (como V6.1 original)."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    tag = f" [{label}]" if label else ""
    line = f"[{ts}] <<< RESPONSE{tag}: HTTP {status_code} | {url}"
    debug_write(line)
    http_write(line)

    if headers:
        debug_write("  RESPONSE HEADERS:")
        http_write("  RESPONSE HEADERS:")
        for k, v in (headers.items() if hasattr(headers, 'items') else []):
            entry = f"    {k}: {v}"
            debug_write(entry)
            http_write(entry)

    if body:
        body_str = str(body)
        debug_write(f"  RESPONSE BODY ({len(body_str)} chars):")
        http_write(f"  RESPONSE BODY ({len(body_str)} chars):")
        if len(body_str) > 10000:
            debug_write(f"    {body_str[:10000]}")
            debug_write(f"    ... [TRUNCATED, total {len(body_str)} chars]")
            http_write(f"    {body_str[:10000]}")
            http_write(f"    ... [TRUNCATED, total {len(body_str)} chars]")
        else:
            debug_write(f"    {body_str}")
            http_write(f"    {body_str}")

    debug_write("")
    http_write("")


# ==============================================================================
# DEBUG DETALHADO - PLAYWRIGHT
# ==============================================================================

def debug_pw_action(action, detail=""):
    """Log de ação do Playwright (navegação, clique, preenchimento)."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] [PW-ACTION] {action}"
    debug_write(line)
    pw_write(line)
    if detail:
        debug_write(f"    {detail}")
        pw_write(f"    {detail}")


def debug_pw_navigation(url, status="", wait_until=""):
    """Log de navegação do Playwright."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] [PW-NAV] {url}"
    if status:
        line += f" | Status: {status}"
    if wait_until:
        line += f" | WaitUntil: {wait_until}"
    debug_write(line)
    pw_write(line)


def debug_pw_element(selector, action, value="", success=True):
    """Log de interação com elemento do Playwright."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    status = "OK" if success else "FAIL"
    line = f"[{ts}] [PW-ELEM] [{status}] {action} -> {selector}"
    if value:
        v_str = str(value)
        if len(v_str) > 100:
            line += f" = {v_str[:100]}..."
        else:
            line += f" = {v_str}"
    debug_write(line)
    pw_write(line)


def debug_pw_screenshot(name, path):
    """Log de screenshot do Playwright."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] [PW-SCREENSHOT] {name} -> {path}"
    debug_write(line)
    pw_write(line)


def debug_pw_html(page_title, url, html_snippet=""):
    """Log do HTML da página (primeiros 2000 chars)."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    pw_write(f"[{ts}] [PW-HTML] Title: {page_title}")
    pw_write(f"  URL: {url}")
    if html_snippet:
        pw_write(f"  HTML ({len(html_snippet)} chars):")
        pw_write(f"    {html_snippet[:3000]}")
        if len(html_snippet) > 3000:
            pw_write(f"    ... [TRUNCATED, total {len(html_snippet)} chars]")
    pw_write("")


def debug_pw_js_eval(expression, result="", success=True):
    """Log de execução JavaScript no Playwright."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    status = "OK" if success else "FAIL"
    expr_short = expression[:150] + "..." if len(expression) > 150 else expression
    line = f"[{ts}] [PW-JS] [{status}] {expr_short}"
    debug_write(line)
    pw_write(line)
    if result:
        r_str = str(result)
        if len(r_str) > 200:
            pw_write(f"    Result: {r_str[:200]}...")
        else:
            pw_write(f"    Result: {r_str}")


def debug_pw_error(action, error, tb=""):
    """Log de erro do Playwright."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] [PW-ERROR] {action}: {error}"
    debug_write(line)
    pw_write(line)
    if tb:
        pw_write(f"  TRACEBACK:\n{tb}")


# ==============================================================================
# DEBUG GENÉRICO - EVENTS/ERRORS
# ==============================================================================

def debug_event(event, detail=""):
    """Log de evento genérico."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    debug_write(f"[{ts}] [EVENT] {event}")
    if detail:
        debug_write(f"    {detail}")


def debug_error(error, tb=""):
    """Log de erro genérico."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    debug_write(f"[{ts}] [ERROR] {error}")
    if tb:
        debug_write(f"  TRACEBACK:\n{tb}")


# ==============================================================================
# LOGGER PRINCIPAL - TERMINAL + ARQUIVO
# ==============================================================================

def log(level, msg, detail=""):
    """Log colorido no terminal + arquivo de debug."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    colors = {
        "INFO": C.CY, "OK": C.G, "FAIL": C.RD, "WARN": C.Y,
        "API": C.MG, "EMAIL": C.CY, "CAPTCHA": C.MG,
        "TOKEN": C.G, "DEBUG": C.DIM, "STEP": C.W,
        "PW": C.CY, "ZIP": C.MG,
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
    """Separador visual no terminal."""
    print(f"\n{C.MG}{C.B}{'='*60}{C.R}")
    if title:
        print(f"{C.MG}{C.B}  {title}{C.R}")
        print(f"{C.MG}{C.B}{'='*60}{C.R}")


def log_stats():
    """Exibe estatísticas no terminal e salva no debug."""
    elapsed = time.time() - STATS["start_time"]
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)
    taxa = 0
    total_tentativas = STATS["cadastros_ok"] + STATS["cadastros_fail"]
    if total_tentativas > 0:
        taxa = int(STATS["tokens_gerados"] / total_tentativas * 100)

    stats_line = (
        f"Tokens: {STATS['tokens_gerados']} | "
        f"Cadastros OK: {STATS['cadastros_ok']} | "
        f"Cadastros Fail: {STATS['cadastros_fail']} | "
        f"Logins OK: {STATS['logins_ok']} | "
        f"Logins Fail: {STATS['logins_fail']} | "
        f"Ativacoes OK: {STATS['ativacoes_ok']} | "
        f"Ativacoes Fail: {STATS['ativacoes_fail']} | "
        f"Emails: {STATS['emails_recebidos']} | "
        f"Timeout: {STATS['emails_timeout']} | "
        f"Inbox Errs: {STATS['inbox_errors']} | "
        f"Reativacoes: {STATS['reativacoes']} | "
        f"Senhas Recup: {STATS['senhas_recuperadas']} | "
        f"Taxa: {taxa}% | Tempo: {mins}m{secs}s"
    )

    print(f"\n{C.CY}{C.B}[STATS]{C.R} "
          f"Tokens: {C.G}{STATS['tokens_gerados']}{C.R} | "
          f"Cadastros: {C.G}{STATS['cadastros_ok']}{C.R}/{C.RD}{STATS['cadastros_fail']}{C.R} | "
          f"Logins: {C.G}{STATS['logins_ok']}{C.R}/{C.RD}{STATS['logins_fail']}{C.R} | "
          f"Ativacoes: {C.G}{STATS['ativacoes_ok']}{C.R}/{C.RD}{STATS['ativacoes_fail']}{C.R} | "
          f"Emails: {C.G}{STATS['emails_recebidos']}{C.R} | "
          f"Timeout: {C.Y}{STATS['emails_timeout']}{C.R} | "
          f"Taxa: {C.G}{taxa}%{C.R} | "
          f"Tempo: {mins}m{secs}s\n")

    debug_write(f"\n[STATS] {stats_line}\n")
    cycle_write(f"[STATS] {stats_line}")


# ==============================================================================
# COMPRESSÃO ZIP
# ==============================================================================

def criar_zip_ciclo(cycle_num, include_screenshots=True):
    """
    Cria um ZIP com todos os logs e screenshots do ciclo atual.
    Salva em /sdcard/nh_files/logs/ciclo_NNN_TIMESTAMP.zip
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"ciclo_{cycle_num:03d}_{ts}.zip"
    zip_path = os.path.join(LOGS_DIR, zip_name)

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Adicionar logs
            for log_file in [DEBUG_LOG_FILE, PW_LOG_FILE, HTTP_LOG_FILE, CYCLE_LOG_FILE]:
                if os.path.exists(log_file):
                    arcname = os.path.basename(log_file)
                    zf.write(log_file, arcname)

            # Adicionar screenshots
            if include_screenshots and os.path.exists(SCREENSHOTS_DIR):
                for fname in os.listdir(SCREENSHOTS_DIR):
                    fpath = os.path.join(SCREENSHOTS_DIR, fname)
                    if os.path.isfile(fpath):
                        zf.write(fpath, f"screenshots/{fname}")

        file_size = os.path.getsize(zip_path)
        size_kb = file_size / 1024
        log("ZIP", f"ZIP criado: {zip_name} ({size_kb:.1f} KB)")
        debug_write(f"[ZIP] Arquivo: {zip_path} ({size_kb:.1f} KB)")
        return zip_path

    except Exception as e:
        log("FAIL", f"Erro ao criar ZIP: {str(e)}")
        debug_error(f"ZIP creation: {str(e)}", traceback.format_exc())
        return None


def criar_zip_sessao():
    """
    Cria um ZIP completo da sessão inteira (todos os logs + screenshots).
    Ideal para enviar ao desenvolvedor para análise.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_name = f"sessao_completa_{SESSION_ID}_{ts}.zip"
    zip_path = os.path.join(LOGS_DIR, zip_name)

    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Adicionar TODOS os logs
            for log_file in [DEBUG_LOG_FILE, PW_LOG_FILE, HTTP_LOG_FILE, CYCLE_LOG_FILE]:
                if os.path.exists(log_file):
                    arcname = os.path.basename(log_file)
                    zf.write(log_file, arcname)

            # Adicionar TODOS os screenshots
            if os.path.exists(SCREENSHOTS_DIR):
                for fname in sorted(os.listdir(SCREENSHOTS_DIR)):
                    fpath = os.path.join(SCREENSHOTS_DIR, fname)
                    if os.path.isfile(fpath):
                        zf.write(fpath, f"screenshots/{fname}")

            # Adicionar token file se existir
            token_file = os.path.join(BASE_DIR, "tokenschkfull.txt")
            if os.path.exists(token_file):
                zf.write(token_file, "tokenschkfull.txt")

            # Adicionar stats resumo
            stats_content = json.dumps(STATS, indent=2, ensure_ascii=False)
            zf.writestr("stats_final.json", stats_content)

        file_size = os.path.getsize(zip_path)
        size_mb = file_size / (1024 * 1024)
        log("ZIP", f"ZIP sessao completa: {zip_name} ({size_mb:.2f} MB)")
        log("ZIP", f"Caminho: {zip_path}")
        return zip_path

    except Exception as e:
        log("FAIL", f"Erro ao criar ZIP sessao: {str(e)}")
        debug_error(f"ZIP session: {str(e)}", traceback.format_exc())
        return None


def limpar_screenshots():
    """Limpa screenshots antigos para economizar espaço."""
    try:
        if os.path.exists(SCREENSHOTS_DIR):
            for fname in os.listdir(SCREENSHOTS_DIR):
                fpath = os.path.join(SCREENSHOTS_DIR, fname)
                if os.path.isfile(fpath):
                    os.remove(fpath)
            debug_write("[CLEANUP] Screenshots limpos")
    except Exception:
        pass


def limpar_logs_ciclo():
    """Limpa logs do ciclo anterior (mantém histórico no ZIP)."""
    for log_file in [DEBUG_LOG_FILE, PW_LOG_FILE, HTTP_LOG_FILE]:
        try:
            if os.path.exists(log_file):
                # Manter apenas as últimas 500 linhas
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                if len(lines) > 5000:
                    with open(log_file, 'w', encoding='utf-8') as f:
                        f.write(f"--- LOG ROTACIONADO ({len(lines)} linhas -> 500) ---\n")
                        f.writelines(lines[-500:])
                    debug_write(f"[ROTATION] {os.path.basename(log_file)} rotacionado")
        except Exception:
            pass
