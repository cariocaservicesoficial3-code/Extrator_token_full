#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║     AJATO TOKEN GENERATOR V7.0 - PLAYWRIGHT EDITION         ║
║     Refatorado com Playwright para Kali Linux NetHunter      ║
║     Baseado no HAR real de cadastro bem-sucedido             ║
╚══════════════════════════════════════════════════════════════╝

Fluxo principal:
  1. Gerar email temporário (Emailnator)
  2. Gerar dados de pessoa (4devs)
  3. Gerar senha segura
  4. Cadastrar na Movida (Playwright + reCAPTCHA Enterprise)
  5. Aguardar email de confirmação
  6. Ativar conta via link
  7. Fazer login e extrair token
  8. Salvar token no arquivo
"""

import os
import re
import sys
import time
import signal
import asyncio
import traceback
from datetime import datetime

# Adicionar diretório src ao path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import (
    C, OUTPUT_FILE, BASE_DIR, IS_NETHUNTER,
    EMAIL_CONFIRM_TIMEOUT, MAX_CADASTRO_RETRIES,
    MAX_LOGIN_RETRIES, MAX_RECOVER_RETRIES,
    MAX_REACTIVATION_ATTEMPTS, ACTIVATION_DELAY,
    EMAIL_TYPES_PRIORITY,
)
from logger import (
    log, log_separator, log_stats, debug_write,
    debug_separator, debug_session_start, debug_event,
    debug_error, STATS, CURRENT_CYCLE,
)
from emailnator_module import Emailnator
from pessoa_generator import gerar_pessoa_4devs, gerar_senha
from movida_playwright import (
    criar_browser, fazer_cadastro_playwright,
    ativar_conta_playwright, fazer_login_playwright,
    recuperar_senha,
)


# ==============================================================================
# BANNER
# ==============================================================================

def print_banner():
    print(f"""
{C.MG}{C.B}╔══════════════════════════════════════════════════════════════╗
║{C.CY}     ___       _  ___  _____  ___                              {C.MG}║
║{C.CY}    / _ \\     | |/ _ \\|_   _|/ _ \\                             {C.MG}║
║{C.CY}   / /_\\ \\    | / /_\\ \\ | | / / \\ \\                            {C.MG}║
║{C.CY}   |  _  | _  | |  _  | | | | | | |                            {C.MG}║
║{C.CY}   | | | || |_| | | | | | | \\ \\_/ /                            {C.MG}║
║{C.CY}   \\_| |_/ \\___/\\_| |_/ \\_/  \\___/                             {C.MG}║
║                                                              ║
║{C.G}   TOKEN GENERATOR V7.0 - PLAYWRIGHT EDITION                 {C.MG}║
║{C.Y}   Otimizado para Kali Linux NetHunter                       {C.MG}║
║{C.CY}   reCAPTCHA Enterprise via Browser Real                     {C.MG}║
╚══════════════════════════════════════════════════════════════╝{C.R}
""")
    env = "NetHunter" if IS_NETHUNTER else "Linux Desktop"
    log("INFO", f"Ambiente detectado: {C.G}{env}{C.R}")
    log("INFO", f"Output: {C.CY}{OUTPUT_FILE}{C.R}")
    log("INFO", f"Base dir: {C.CY}{BASE_DIR}{C.R}")


# ==============================================================================
# SALVAR TOKEN
# ==============================================================================

def salvar_token(token, email, cpf, nome, senha):
    """Salva token no arquivo de saída."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] TOKEN={token} | EMAIL={email} | CPF={cpf} | NOME={nome} | SENHA={senha}\n"
    try:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(line)
        STATS["tokens_gerados"] += 1
        log("TOKEN", f"{C.BG_G}{C.W} TOKEN SALVO #{STATS['tokens_gerados']} {C.R}")
        log("TOKEN", f"  Token: {token[:30]}...{token[-10:] if len(token) > 40 else ''}")
        log("TOKEN", f"  Email: {email}")
        log("TOKEN", f"  CPF: {cpf}")
        log("TOKEN", f"  Senha: {senha}")
        return True
    except Exception as e:
        log("FAIL", f"Erro ao salvar token: {str(e)}")
        return False


# ==============================================================================
# CICLO PRINCIPAL (ASYNC)
# ==============================================================================

async def executar_ciclo(cycle_num, playwright):
    """Executa um ciclo completo de geração de token."""
    log_separator(f"CICLO #{cycle_num}")

    browser = None
    context = None
    emailnator = None

    try:
        # =============================================
        # INICIALIZAR BROWSER (compartilhado para tudo)
        # =============================================
        log("PW", "Iniciando browser Playwright...")
        browser, context = await criar_browser(playwright)

        # =============================================
        # PASSO 1: Gerar Email Temporário
        # =============================================
        log("STEP", "PASSO 1: Gerando Gmail temporario (Emailnator)...")

        emailnator = Emailnator(playwright_context=context)

        # Tentar requests primeiro, fallback Playwright
        email = None
        for email_type in EMAIL_TYPES_PRIORITY:
            email = await emailnator.generate_email_async(email_type)
            if email:
                break

        if not email:
            log("FAIL", "Nao foi possivel gerar email temporario!")
            STATS["cadastros_fail"] += 1
            await browser.close()
            return False

        log("OK", f"Email gerado: {C.G}{email}{C.R}")

        # Verificar inbox inicial
        log("DEBUG", "Verificando inbox inicial (pre-cadastro)...")
        initial_msgs = await emailnator.get_messages_async()
        if initial_msgs is not None:
            log("DEBUG", f"Inbox inicial: {len(initial_msgs)} mensagens")

        # =============================================
        # PASSO 2: Gerar Dados de Pessoa
        # =============================================
        log("STEP", "PASSO 2: Gerando dados de pessoa (4devs)...")

        pessoa = gerar_pessoa_4devs()
        if not pessoa:
            log("FAIL", "Nao foi possivel gerar pessoa!")
            STATS["cadastros_fail"] += 1
            await emailnator.close()
            await browser.close()
            return False

        nome = pessoa.get("nome", "?")
        cpf = pessoa.get("cpf", "?")
        cpf_numeros = re.sub(r'\D', '', cpf)

        log("OK", f"Pessoa gerada: {C.G}{nome}{C.R}")
        log("DEBUG", f"  CPF: {cpf} | Nasc: {pessoa.get('data_nasc')}")
        log("DEBUG", f"  Tel: {pessoa.get('telefone_fixo')} | Cel: {pessoa.get('celular')}")
        log("DEBUG", f"  CEP: {pessoa.get('cep')} | Cidade: {pessoa.get('cidade')}/{pessoa.get('estado')}")

        # Atualizar ciclo atual
        CURRENT_CYCLE.update({"num": cycle_num, "email": email, "cpf": cpf, "nome": nome})
        debug_session_start(cycle_num, email, cpf, nome)

        # =============================================
        # PASSO 3: Gerar Senha
        # =============================================
        log("STEP", "PASSO 3: Gerando senha segura...")
        senha = gerar_senha()
        log("OK", f"Senha gerada: {C.Y}{senha}{C.R}")

        # =============================================
        # PASSO 4-6: Cadastro via Playwright
        # =============================================
        cadastro_ok = False
        for tentativa in range(1, MAX_CADASTRO_RETRIES + 1):
            log("STEP", f"PASSO 4-6: Cadastrando na Movida (tentativa {tentativa}/{MAX_CADASTRO_RETRIES})...")

            cadastro_ok = await fazer_cadastro_playwright(context, pessoa, email, senha)
            if cadastro_ok:
                break

            if tentativa < MAX_CADASTRO_RETRIES:
                log("WARN", f"Cadastro falhou (tentativa {tentativa}). Tentando novamente...")
                await asyncio.sleep(2)

        if not cadastro_ok:
            log("FAIL", f"Cadastro falhou apos {MAX_CADASTRO_RETRIES} tentativas!")
            STATS["cadastros_fail"] += 1
            await emailnator.close()
            await browser.close()
            return False

        # =============================================
        # PASSO 7: Aguardar Email de Confirmação
        # =============================================
        log("STEP", "PASSO 7: Aguardando email de confirmacao...")

        confirmation_link = await emailnator.wait_for_email_async(
            sender_filter="movida",
            timeout=EMAIL_CONFIRM_TIMEOUT,
            link_pattern="sendgrid",
        )

        if not confirmation_link:
            # Tentar aceitar qualquer email
            log("WARN", "Email da Movida nao chegou, tentando qualquer email...")
            confirmation_link = await emailnator.wait_for_email_async(
                sender_filter="",
                timeout=30,
                link_pattern="sendgrid",
                accept_any=True,
            )

        if not confirmation_link:
            log("FAIL", "Email de confirmacao nao chegou!")
            STATS["emails_timeout"] += 1

            # Tentar login direto (alguns cadastros não precisam confirmação)
            log("WARN", "Tentando login direto sem confirmacao...")
            token, status = await fazer_login_playwright(context, cpf_numeros, senha)
            if token and status == "ok":
                salvar_token(token, email, cpf, nome, senha)
                await emailnator.close()
                await browser.close()
                return True

            await emailnator.close()
            await browser.close()
            return False

        log("OK", f"Link de confirmacao: {confirmation_link[:80]}...")

        # =============================================
        # PASSO 8: Ativar Conta
        # =============================================
        log("STEP", "PASSO 8: Ativando conta...")

        ativacao_ok = await ativar_conta_playwright(context, confirmation_link, senha)

        if not ativacao_ok:
            log("WARN", "Ativacao falhou, tentando login mesmo assim...")

        await asyncio.sleep(ACTIVATION_DELAY)

        # =============================================
        # PASSO 9: Login e Extração de Token
        # =============================================
        log("STEP", "PASSO 9: Fazendo login e extraindo token...")

        token = None
        status = None

        for login_try in range(1, MAX_LOGIN_RETRIES + 1):
            log("DEBUG", f"Tentativa de login {login_try}/{MAX_LOGIN_RETRIES}...")

            token, status = await fazer_login_playwright(context, cpf_numeros, senha)

            if token and status == "ok":
                log("OK", f"Login OK na tentativa {login_try}!")
                break

            if status == "nao_confirmado":
                log("WARN", "Conta nao confirmada! Tentando reativacao...")
                STATS["reativacoes"] += 1

                for reactivation in range(MAX_REACTIVATION_ATTEMPTS):
                    log("DEBUG", f"Reativacao tentativa {reactivation + 1}...")
                    new_link = await emailnator.wait_for_email_async(
                        sender_filter="movida",
                        timeout=30,
                        link_pattern="sendgrid",
                    )
                    if new_link:
                        await ativar_conta_playwright(context, new_link, senha)
                        await asyncio.sleep(ACTIVATION_DELAY)
                        token, status = await fazer_login_playwright(context, cpf_numeros, senha)
                        if token and status == "ok":
                            break
                if token and status == "ok":
                    break

            elif status == "senha_invalida":
                log("WARN", "Senha invalida! Tentando recuperacao...")
                nova_senha = gerar_senha()
                recuperou = await recuperar_senha(context, emailnator, cpf_numeros, email, nova_senha)
                if recuperou:
                    senha = nova_senha
                    await asyncio.sleep(2)
                    token, status = await fazer_login_playwright(context, cpf_numeros, senha)
                    if token and status == "ok":
                        break

            elif status == "incomplete_data":
                log("WARN", "Dados incompletos! Tentando login direto...")
                await asyncio.sleep(2)
                continue

            else:
                log("WARN", f"Login falhou com status: {status}")
                if login_try < MAX_LOGIN_RETRIES:
                    await asyncio.sleep(2)

        # =============================================
        # PASSO 10: Salvar Token
        # =============================================
        if token and status == "ok":
            salvar_token(token, email, cpf, nome, senha)
            log("OK", f"{C.BG_G}{C.W} CICLO #{cycle_num} CONCLUIDO COM SUCESSO! {C.R}")
            await emailnator.close()
            await browser.close()
            return True
        else:
            log("FAIL", f"Ciclo #{cycle_num} falhou! Status final: {status}")
            STATS["logins_fail"] += 1
            await emailnator.close()
            await browser.close()
            return False

    except Exception as e:
        log("FAIL", f"Erro no ciclo #{cycle_num}: {str(e)}")
        debug_error(f"Ciclo #{cycle_num}: {str(e)}", traceback.format_exc())
        if emailnator:
            try:
                await emailnator.close()
            except Exception:
                pass
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        return False


# ==============================================================================
# LOOP PRINCIPAL
# ==============================================================================

async def main_loop():
    """Loop principal de geração de tokens."""
    from playwright.async_api import async_playwright

    print_banner()

    cycle_num = 0
    consecutive_fails = 0
    max_consecutive_fails = 5

    async with async_playwright() as playwright:
        while True:
            cycle_num += 1

            try:
                success = await executar_ciclo(cycle_num, playwright)

                if success:
                    consecutive_fails = 0
                    log_stats()
                else:
                    consecutive_fails += 1
                    log_stats()

                    if consecutive_fails >= max_consecutive_fails:
                        log("WARN", f"{consecutive_fails} falhas consecutivas. Aguardando 10s...")
                        consecutive_fails = 0
                        await asyncio.sleep(10)
                    else:
                        log("WARN", f"Ciclo #{cycle_num} falhou. Aguardando 5s...")
                        await asyncio.sleep(5)

            except KeyboardInterrupt:
                log("INFO", "Interrompido pelo usuario (Ctrl+C)")
                log_stats()
                break
            except Exception as e:
                log("FAIL", f"Erro fatal no ciclo #{cycle_num}: {str(e)}")
                debug_error(f"Fatal ciclo #{cycle_num}: {str(e)}", traceback.format_exc())
                consecutive_fails += 1
                await asyncio.sleep(5)


# ==============================================================================
# ENTRY POINT
# ==============================================================================

def main():
    """Entry point do script."""
    # Tratar Ctrl+C gracefully
    def signal_handler(sig, frame):
        print(f"\n{C.Y}[INFO]{C.R} Encerrando gracefully...")
        log_stats()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print(f"\n{C.Y}[INFO]{C.R} Encerrado pelo usuario.")
        log_stats()
    except Exception as e:
        print(f"\n{C.RD}[FATAL]{C.R} {str(e)}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
