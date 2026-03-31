#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║     AJATO TOKEN GENERATOR V7.6 - HTTP DIRECT SUBMIT        ║
║     Playwright + HTTP POST Direto + Smart CPF Retry            ║
║     Otimizado para Kali Linux NetHunter                      ║
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
  9. Criar ZIP com logs + screenshots do ciclo

NOVIDADES V7.6:
  - HTTP DIRECT SUBMIT: POST HTTP direto ao invés de clicar no botão ENVIAR
  - Resolve o problema do grecaptcha.enterprise não carregar no headless
  - Extrai cookies do Playwright + campos do formulário via JS
  - Faz POST para /usuario/enviar-cadastro com token reCAPTCHA HTTP
  - Detecção precisa: HTTP 303=sucesso, verifica corpo para erros
  - Debug logs completo em /sdcard/nh_files/logs/ com ZIP automático
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
    C, OUTPUT_FILE, BASE_DIR, IS_NETHUNTER, LOGS_DIR,
    EMAIL_CONFIRM_TIMEOUT, MAX_CADASTRO_RETRIES,
    MAX_LOGIN_RETRIES, MAX_RECOVER_RETRIES,
    MAX_REACTIVATION_ATTEMPTS, ACTIVATION_DELAY,
    EMAIL_TYPES_PRIORITY,
)
from logger import (
    log, log_separator, log_stats, debug_write,
    debug_separator, debug_session_start, debug_session_end,
    debug_event, debug_error,
    criar_zip_ciclo, criar_zip_sessao,
    limpar_screenshots, limpar_logs_ciclo,
    STATS, CURRENT_CYCLE, SESSION_ID,
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
║{C.G}   TOKEN GENERATOR V7.6 - HTTP DIRECT SUBMIT          {C.MG}║
║{C.Y}   Otimizado para Kali Linux NetHunter                       {C.MG}║
║{C.CY}   Smart CPF Retry + AJAX Submit + HTTP reCAPTCHA Bypass                     {C.MG}║
║{C.W}   Debug Logs + ZIP em /sdcard/nh_files/logs/               {C.MG}║
╚══════════════════════════════════════════════════════════════╝{C.R}
""")
    env = "NetHunter" if IS_NETHUNTER else "Linux Desktop"
    log("INFO", f"Ambiente detectado: {C.G}{env}{C.R}")
    log("INFO", f"Output: {C.CY}{OUTPUT_FILE}{C.R}")
    log("INFO", f"Base dir: {C.CY}{BASE_DIR}{C.R}")
    log("INFO", f"Logs dir: {C.CY}{LOGS_DIR}{C.R}")
    log("INFO", f"Session ID: {C.CY}{SESSION_ID}{C.R}")


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
        debug_event("TOKEN_SAVED", f"#{STATS['tokens_gerados']} | {email} | {cpf}")
        return True
    except Exception as e:
        log("FAIL", f"Erro ao salvar token: {str(e)}")
        debug_error(f"salvar_token: {str(e)}", traceback.format_exc())
        return False


# ==============================================================================
# CICLO PRINCIPAL (ASYNC)
# ==============================================================================

async def executar_ciclo(cycle_num, playwright):
    """Executa um ciclo completo de geração de token."""
    log_separator(f"CICLO #{cycle_num}")
    cycle_start = time.time()

    browser = None
    context = None
    emailnator = None
    token = None
    status = None

    try:
        # =============================================
        # INICIALIZAR BROWSER
        # =============================================
        log("PW", "Iniciando browser Playwright...")
        browser, context = await criar_browser(playwright)

        # =============================================
        # PASSO 1: Gerar Email Temporário
        # =============================================
        log("STEP", "PASSO 1: Gerando Gmail temporario (Emailnator)...")

        emailnator = Emailnator(playwright_context=context)

        email = None
        for email_type in EMAIL_TYPES_PRIORITY:
            email = await emailnator.generate_email_async(email_type)
            if email:
                break

        if not email:
            log("FAIL", "Nao foi possivel gerar email temporario!")
            STATS["cadastros_fail"] += 1
            await browser.close()
            debug_session_end(cycle_num, False, error="email_generation_failed")
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
            debug_session_end(cycle_num, False, error="pessoa_generation_failed")
            return False

        nome = pessoa.get("nome", "?")
        cpf = pessoa.get("cpf", "?")
        cpf_numeros = re.sub(r'\D', '', cpf)

        log("OK", f"Pessoa gerada: {C.G}{nome}{C.R}")
        log("DEBUG", f"  CPF: {cpf} | Nasc: {pessoa.get('data_nasc')}")
        log("DEBUG", f"  Tel: {pessoa.get('telefone_fixo')} | Cel: {pessoa.get('celular')}")
        log("DEBUG", f"  CEP: {pessoa.get('cep')} | Cidade: {pessoa.get('cidade')}/{pessoa.get('estado')}")

        # Atualizar ciclo atual
        CURRENT_CYCLE.update({"num": cycle_num, "email": email, "cpf": cpf, "nome": nome, "start_time": cycle_start})
        debug_session_start(cycle_num, email, cpf, nome)

        # =============================================
        # PASSO 3: Gerar Senha
        # =============================================
        log("STEP", "PASSO 3: Gerando senha segura...")
        senha = gerar_senha()
        log("OK", f"Senha gerada: {C.Y}{senha}{C.R}")

        # =============================================
        # PASSO 4-6: Cadastro via Playwright (V7.6 HTTP Direct Submit)
        # =============================================
        cadastro_status = None
        max_cpf_retries = 5  # Máximo de CPFs diferentes para tentar
        cpf_attempt = 0

        for tentativa in range(1, MAX_CADASTRO_RETRIES + 1):
            log("STEP", f"PASSO 4-6: Cadastrando na Movida (tentativa {tentativa}/{MAX_CADASTRO_RETRIES})...")
            log("DEBUG", f"  Usando CPF: {cpf} | Nome: {nome} | Email: {email}")

            cadastro_status = await fazer_cadastro_playwright(context, pessoa, email, senha)
            log("DEBUG", f"  Resultado cadastro: {cadastro_status}")

            # V7.6: Retorno inteligente com status string
            if cadastro_status == "sucesso":
                log("OK", f"Cadastro SUCESSO na tentativa {tentativa}!")
                break

            elif cadastro_status == "cpf_duplicado":
                cpf_attempt += 1
                log("WARN", f"CPF {cpf} ja existe na Movida! (tentativa CPF #{cpf_attempt})")

                if cpf_attempt >= max_cpf_retries:
                    log("FAIL", f"Esgotou {max_cpf_retries} tentativas de CPF diferente!")
                    break

                # Gerar NOVA pessoa com CPF diferente
                log("STEP", f"Gerando NOVO CPF/pessoa (tentativa CPF #{cpf_attempt + 1})...")
                nova_pessoa = gerar_pessoa_4devs()
                if nova_pessoa:
                    pessoa = nova_pessoa
                    nome = pessoa.get("nome", "?")
                    cpf = pessoa.get("cpf", "?")
                    cpf_numeros = re.sub(r'\D', '', cpf)
                    log("OK", f"Nova pessoa: {C.G}{nome}{C.R} | CPF: {cpf}")
                    debug_event("novo_cpf", f"Tentativa #{cpf_attempt + 1}: {cpf} - {nome}")
                    CURRENT_CYCLE.update({"cpf": cpf, "nome": nome})
                else:
                    log("FAIL", "Nao conseguiu gerar nova pessoa!")
                    break

                await asyncio.sleep(1)
                continue

            elif cadastro_status == "captcha_fail":
                log("WARN", f"reCAPTCHA falhou na tentativa {tentativa}. Retentando...")
                await asyncio.sleep(2)
                continue

            else:  # erro_generico ou qualquer outro
                log("WARN", f"Cadastro falhou com status '{cadastro_status}' (tentativa {tentativa})")
                if tentativa < MAX_CADASTRO_RETRIES:
                    await asyncio.sleep(2)

        if cadastro_status != "sucesso":
            log("FAIL", f"Cadastro falhou! Status final: {cadastro_status}")
            STATS["cadastros_fail"] += 1
            debug_session_end(cycle_num, False, error=f"cadastro_{cadastro_status}")
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

            # Tentar login direto
            log("WARN", "Tentando login direto sem confirmacao...")
            token, status = await fazer_login_playwright(context, cpf_numeros, senha)
            if token and status == "ok":
                salvar_token(token, email, cpf, nome, senha)
                debug_session_end(cycle_num, True, token=token[:30])
                await emailnator.close()
                await browser.close()
                return True

            debug_session_end(cycle_num, False, error="email_timeout")
            await emailnator.close()
            await browser.close()
            return False

        log("OK", f"Link de confirmacao: {confirmation_link[:80]}...")
        STATS["emails_recebidos"] += 1

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
            elapsed = time.time() - cycle_start
            log("OK", f"{C.BG_G}{C.W} CICLO #{cycle_num} CONCLUIDO COM SUCESSO! ({elapsed:.1f}s) {C.R}")
            debug_session_end(cycle_num, True, token=token[:30])
            await emailnator.close()
            await browser.close()
            return True
        else:
            elapsed = time.time() - cycle_start
            log("FAIL", f"Ciclo #{cycle_num} falhou! Status final: {status} ({elapsed:.1f}s)")
            STATS["logins_fail"] += 1
            debug_session_end(cycle_num, False, error=f"login_{status}")
            await emailnator.close()
            await browser.close()
            return False

    except Exception as e:
        log("FAIL", f"Erro no ciclo #{cycle_num}: {str(e)}")
        debug_error(f"Ciclo #{cycle_num}: {str(e)}", traceback.format_exc())
        debug_session_end(cycle_num, False, error=f"exception: {str(e)[:100]}")
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
                # Limpar screenshots do ciclo anterior
                limpar_screenshots()

                success = await executar_ciclo(cycle_num, playwright)

                # =============================================
                # ZIP DO CICLO (logs + screenshots)
                # =============================================
                zip_path = criar_zip_ciclo(cycle_num, include_screenshots=True)
                if zip_path:
                    log("ZIP", f"Logs do ciclo #{cycle_num} compactados!")
                    log("ZIP", f"Arquivo: {zip_path}")

                # Rotacionar logs se muito grandes
                limpar_logs_ciclo()

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
                # ZIP mesmo em caso de erro fatal
                criar_zip_ciclo(cycle_num, include_screenshots=True)
                consecutive_fails += 1
                await asyncio.sleep(5)


# ==============================================================================
# ENTRY POINT
# ==============================================================================

def main():
    """Entry point do script."""
    def signal_handler(sig, frame):
        print(f"\n{C.Y}[INFO]{C.R} Encerrando gracefully...")
        log_stats()
        # Criar ZIP final da sessão
        zip_path = criar_zip_sessao()
        if zip_path:
            print(f"{C.G}[ZIP]{C.R} Sessao completa salva em: {zip_path}")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print(f"\n{C.Y}[INFO]{C.R} Encerrado pelo usuario.")
        log_stats()
        # ZIP final
        zip_path = criar_zip_sessao()
        if zip_path:
            print(f"{C.G}[ZIP]{C.R} Sessao completa: {zip_path}")
    except Exception as e:
        print(f"\n{C.RD}[FATAL]{C.R} {str(e)}")
        traceback.print_exc()
        # ZIP mesmo em caso de crash
        criar_zip_sessao()
        sys.exit(1)


if __name__ == "__main__":
    main()
