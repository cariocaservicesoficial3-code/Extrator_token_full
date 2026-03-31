#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AJATO TOKEN GENERATOR V7.0 - Sistema de Logging
Terminal colorido + arquivo de debug detalhado.
"""

import re
import time
from datetime import datetime
from config import C, DEBUG_LOG_FILE

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
    "start_time": time.time()
}

CURRENT_CYCLE = {"num": 0, "email": "", "cpf": "", "nome": ""}


# ==============================================================================
# DEBUG FILE
# ==============================================================================

def debug_write(text):
    """Escreve no arquivo de debug."""
    try:
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            clean = re.sub(r'\033\[[0-9;]*m', '', str(text))
            f.write(clean + "\n")
    except Exception:
        pass


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
# LOGGER PRINCIPAL
# ==============================================================================

def log(level, msg, detail=""):
    """Log colorido no terminal + arquivo de debug."""
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    colors = {
        "INFO": C.CY, "OK": C.G, "FAIL": C.RD, "WARN": C.Y,
        "API": C.MG, "EMAIL": C.CY, "CAPTCHA": C.MG,
        "TOKEN": C.G, "DEBUG": C.DIM, "STEP": C.W,
        "PW": C.CY,  # Playwright
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
    total_tentativas = STATS["cadastros_ok"] + STATS["cadastros_fail"]
    if total_tentativas > 0:
        taxa = int(STATS["tokens_gerados"] / total_tentativas * 100)

    print(f"\n{C.CY}{C.B}[STATS]{C.R} "
          f"Tokens: {C.G}{STATS['tokens_gerados']}{C.R} | "
          f"Cadastros: {C.G}{STATS['cadastros_ok']}{C.R} | "
          f"Logins: {C.G}{STATS['logins_ok']}{C.R} | "
          f"Ativacoes: {C.G}{STATS['ativacoes_ok']}{C.R} | "
          f"Emails: {C.G}{STATS['emails_recebidos']}{C.R} | "
          f"Fails: {C.RD}{STATS['cadastros_fail']}{C.R} | "
          f"Timeout: {C.Y}{STATS['emails_timeout']}{C.R} | "
          f"Taxa: {C.G}{taxa}%{C.R} | "
          f"Tempo: {mins}m{secs}s\n")

    debug_write(f"\n[STATS] Tokens={STATS['tokens_gerados']} | "
                f"Cadastros={STATS['cadastros_ok']} | "
                f"Logins={STATS['logins_ok']} | "
                f"Fails={STATS['cadastros_fail']} | "
                f"Taxa={taxa}% | Tempo={mins}m{secs}s\n")
