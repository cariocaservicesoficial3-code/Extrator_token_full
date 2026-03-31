#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════════╗
║     AJATO TOKEN GENERATOR V7.8 - MODO TESTE EMAIL          ║
║     Playwright + HTTP POST Direto + Smart CPF Retry            ║
║     Otimizado para Kali Linux NetHunter                      ║
╚══════════════════════════════════════════════════════════════╝

Fluxo V7.8 (MODO TESTE):
  1. PEDIR EMAIL DO USUARIO (input manual)
  2. Gerar dados de pessoa (4devs)
  3. Gerar senha segura
  4. Cadastrar na Movida (Playwright + reCAPTCHA Enterprise)
  5. PARAR e mostrar dados - usuario verifica email manualmente
  6. Se usuario confirmar email recebido -> continuar com ativacao/login
  7. Se nao -> diagnostico de falso positivo confirmado

NOVIDADES V7.8:
  - MODO TESTE: Emailnator DESATIVADO temporariamente
  - Pede email real do usuario no inicio de cada ciclo
  - Apos cadastro, PARA e espera confirmacao manual do usuario
  - Corrigido falso positivo na deteccao de sucesso HTTP 200
  - Body completo logado (10000 chars) para analise
  - Objetivo: confirmar se cadastro realmente funciona
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
# Emailnator DESATIVADO no modo teste
# from emailnator_module import Emailnator
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
║{C.G}   TOKEN GENERATOR V7.8 - MODO TESTE EMAIL             {C.MG}║
║{C.Y}   Otimizado para Kali Linux NetHunter                       {C.MG}║
║{C.BG_Y}{C.W}   >>> EMAILNATOR DESATIVADO - TESTE COM EMAIL REAL <<<      {C.R}{C.MG}║
║{C.W}   Debug Logs + ZIP em /sdcard/nh_files/logs/               {C.MG}║
╚══════════════════════════════════════════════════════════════╝{C.R}
""")
    env = "NetHunter" if IS_NETHUNTER else "Linux Desktop"
    log("INFO", f"Ambiente detectado: {C.G}{env}{C.R}")
    log("INFO", f"Output: {C.CY}{OUTPUT_FILE}{C.R}")
    log("INFO", f"Base dir: {C.CY}{BASE_DIR}{C.R}")
    log("INFO", f"Logs dir: {C.CY}{LOGS_DIR}{C.R}")
    log("INFO", f"Session ID: {C.CY}{SESSION_ID}{C.R}")
    print()
    log("WARN", f"{C.BG_Y}{C.W} MODO TESTE ATIVO - Emailnator desativado {C.R}")
    log("INFO", "Voce vai colar seu email real para testar se o cadastro funciona")
    log("INFO", "Apos o cadastro, verifique sua caixa de entrada manualmente")
    print()


# ==============================================================================
# PEDIR EMAIL DO USUARIO
# ==============================================================================

def pedir_email_usuario():
    """Pede para o usuario colar um email real para teste."""
    print(f"{C.MG}{'='*60}{C.R}")
    print(f"{C.B}{C.CY}  COLE SEU EMAIL PARA TESTE{C.R}")
    print(f"{C.MG}{'='*60}{C.R}")
    print()
    print(f"  {C.Y}O script vai usar esse email para fazer o cadastro na Movida.{C.R}")
    print(f"  {C.Y}Apos o cadastro, verifique se o email de confirmacao chegou.{C.R}")
    print()

    while True:
        try:
            email = input(f"  {C.G}>>> Cole seu email aqui: {C.W}").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            log("INFO", "Cancelado pelo usuario.")
            return None

        if not email:
            print(f"  {C.RD}Email vazio! Tente novamente.{C.R}")
            continue

        # Validação básica de email
        if "@" not in email or "." not in email:
            print(f"  {C.RD}Email invalido! Deve conter @ e dominio.{C.R}")
            continue

        # Confirmar
        print()
        print(f"  {C.CY}Email informado: {C.B}{C.W}{email}{C.R}")
        try:
            confirma = input(f"  {C.Y}Confirma? (S/n): {C.W}").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        if confirma in ("", "s", "sim", "y", "yes"):
            print()
            log("OK", f"Email de teste: {C.G}{email}{C.R}")
            return email
        else:
            print(f"  {C.Y}Ok, digite novamente...{C.R}")
            print()


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
# CICLO PRINCIPAL - MODO TESTE (ASYNC)
# ==============================================================================

async def executar_ciclo_teste(cycle_num, playwright, email_usuario):
    """Executa um ciclo de teste com email real do usuario."""
    log_separator(f"CICLO TESTE #{cycle_num}")
    cycle_start = time.time()

    browser = None
    context = None
    token = None
    status = None

    try:
        # =============================================
        # INICIALIZAR BROWSER
        # =============================================
        log("PW", "Iniciando browser Playwright...")
        browser, context = await criar_browser(playwright)

        email = email_usuario

        # =============================================
        # PASSO 1: Email ja fornecido pelo usuario
        # =============================================
        log("STEP", f"PASSO 1: Usando email do usuario: {C.G}{email}{C.R}")
        debug_event("email_manual", email)

        # =============================================
        # PASSO 2: Gerar Dados de Pessoa
        # =============================================
        log("STEP", "PASSO 2: Gerando dados de pessoa (4devs)...")

        pessoa = gerar_pessoa_4devs()
        if not pessoa:
            log("FAIL", "Nao foi possivel gerar pessoa!")
            STATS["cadastros_fail"] += 1
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
        max_cpf_retries = 5
        cpf_attempt = 0

        for tentativa in range(1, MAX_CADASTRO_RETRIES + 1):
            log("STEP", f"PASSO 4-6: Cadastrando na Movida (tentativa {tentativa}/{MAX_CADASTRO_RETRIES})...")
            log("DEBUG", f"  Usando CPF: {cpf} | Nome: {nome} | Email: {email}")

            cadastro_status = await fazer_cadastro_playwright(context, pessoa, email, senha)
            log("DEBUG", f"  Resultado cadastro: {cadastro_status}")

            if cadastro_status == "sucesso":
                log("OK", f"Cadastro SUCESSO na tentativa {tentativa}!")
                break

            elif cadastro_status == "cpf_duplicado":
                cpf_attempt += 1
                log("WARN", f"CPF {cpf} ja existe na Movida! (tentativa CPF #{cpf_attempt})")

                if cpf_attempt >= max_cpf_retries:
                    log("FAIL", f"Esgotou {max_cpf_retries} tentativas de CPF diferente!")
                    break

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

            else:
                log("WARN", f"Cadastro falhou com status '{cadastro_status}' (tentativa {tentativa})")
                if tentativa < MAX_CADASTRO_RETRIES:
                    await asyncio.sleep(2)

        # =============================================
        # RESULTADO DO CADASTRO - MODO TESTE
        # =============================================
        print()
        print(f"{C.MG}{'='*60}{C.R}")
        print(f"{C.B}{C.CY}  RESULTADO DO CADASTRO - MODO TESTE{C.R}")
        print(f"{C.MG}{'='*60}{C.R}")
        print()
        print(f"  {C.W}Status do cadastro: ", end="")

        if cadastro_status == "sucesso":
            print(f"{C.BG_G}{C.W} SUCESSO (segundo o script) {C.R}")
        else:
            print(f"{C.BG_R}{C.W} FALHOU: {cadastro_status} {C.R}")

        print()
        print(f"  {C.CY}Dados usados:{C.R}")
        print(f"  {C.W}  Email: {C.G}{email}{C.R}")
        print(f"  {C.W}  Nome:  {C.G}{nome}{C.R}")
        print(f"  {C.W}  CPF:   {C.G}{cpf}{C.R}")
        print(f"  {C.W}  Senha: {C.G}{senha}{C.R}")
        print()
        print(f"{C.MG}{'='*60}{C.R}")
        print()

        if cadastro_status in ("sucesso", "incerto"):
            if cadastro_status == "incerto":
                print(f"  {C.BG_Y}{C.W} RESULTADO INCERTO - HTTP 200 sem formulario, sem indicadores claros {C.R}")
                print(f"  {C.Y}O servidor retornou algo diferente do esperado.{C.R}")
                print(f"  {C.Y}Verifique seu email para confirmar se o cadastro funcionou.{C.R}")
                print()
            print(f"  {C.BG_Y}{C.W} AGORA VERIFIQUE SUA CAIXA DE EMAIL! {C.R}")
            print()
            print(f"  {C.Y}Verifique:{C.R}")
            print(f"  {C.W}  1. Caixa de entrada{C.R}")
            print(f"  {C.W}  2. Spam / Lixo eletronico{C.R}")
            print(f"  {C.W}  3. Aba 'Promocoes' (Gmail){C.R}")
            print(f"  {C.W}  4. Aba 'Atualizacoes' (Gmail){C.R}")
            print()
            print(f"  {C.Y}O email deve ser de: {C.W}Movida / noreply / sendgrid{C.R}")
            print()

            try:
                resposta = input(f"  {C.G}>>> O email de confirmacao chegou? (s/N): {C.W}").strip().lower()
            except (EOFError, KeyboardInterrupt):
                resposta = "n"

            if resposta in ("s", "sim", "y", "yes"):
                print()
                log("OK", f"{C.BG_G}{C.W} EMAIL CONFIRMADO! O cadastro FUNCIONA! {C.R}")
                log("OK", "O problema era no Emailnator, nao no cadastro.")
                debug_event("teste_email_ok", f"Email chegou em {email}")

                # Perguntar se quer continuar com ativacao
                print()
                try:
                    continuar = input(f"  {C.Y}>>> Cole o link de confirmacao do email (ou Enter para pular): {C.W}").strip()
                except (EOFError, KeyboardInterrupt):
                    continuar = ""

                if continuar and continuar.startswith("http"):
                    log("STEP", "Ativando conta com link fornecido...")
                    ativacao_ok = await ativar_conta_playwright(context, continuar, senha)
                    if ativacao_ok:
                        log("OK", "Conta ativada com sucesso!")
                        await asyncio.sleep(ACTIVATION_DELAY)

                        # Tentar login
                        log("STEP", "Tentando login...")
                        token, status = await fazer_login_playwright(context, cpf_numeros, senha)
                        if token and status == "ok":
                            salvar_token(token, email, cpf, nome, senha)
                            log("OK", f"{C.BG_G}{C.W} FLUXO COMPLETO COM SUCESSO! {C.R}")
                            debug_session_end(cycle_num, True, token=token[:30])
                            await browser.close()
                            return True
                        else:
                            log("WARN", f"Login falhou: {status}")
                    else:
                        log("WARN", "Ativacao falhou")
                else:
                    log("INFO", "Pulando ativacao - teste concluido com sucesso parcial")

                debug_session_end(cycle_num, True, token="teste_email_ok")
                await browser.close()
                return True

            else:
                print()
                log("WARN", f"{C.BG_R}{C.W} EMAIL NAO CHEGOU! {C.R}")
                log("WARN", "Isso confirma que o cadastro retorna FALSO POSITIVO.")
                log("WARN", "O POST HTTP retorna HTTP 200 mas NAO efetua o cadastro.")
                debug_event("teste_email_fail", f"Email NAO chegou em {email}")
                debug_event("diagnostico", "FALSO POSITIVO confirmado - HTTP 200 sem cadastro real")

                print()
                print(f"  {C.CY}Diagnostico:{C.R}")
                print(f"  {C.W}  O servidor retorna HTTP 200 com a mesma pagina de cadastro{C.R}")
                print(f"  {C.W}  Isso indica que o POST falhou silenciosamente{C.R}")
                print(f"  {C.W}  Possiveis causas:{C.R}")
                print(f"  {C.Y}    1. Token reCAPTCHA invalido/expirado{C.R}")
                print(f"  {C.Y}    2. Falta de campo obrigatorio no POST{C.R}")
                print(f"  {C.Y}    3. Cookie de sessao nao vinculado ao form{C.R}")
                print(f"  {C.Y}    4. Validacao server-side rejeitando silenciosamente{C.R}")
                print()

                STATS["cadastros_fail"] += 1
                debug_session_end(cycle_num, False, error="falso_positivo_confirmado")
                await browser.close()
                return False

        else:
            log("FAIL", f"Cadastro falhou com status: {cadastro_status}")
            log("INFO", "O script detectou a falha corretamente desta vez.")
            STATS["cadastros_fail"] += 1
            debug_session_end(cycle_num, False, error=f"cadastro_{cadastro_status}")
            await browser.close()
            return False

    except Exception as e:
        log("FAIL", f"Erro no ciclo teste #{cycle_num}: {str(e)}")
        debug_error(f"Ciclo teste #{cycle_num}: {str(e)}", traceback.format_exc())
        debug_session_end(cycle_num, False, error=f"exception: {str(e)[:100]}")
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        return False


# ==============================================================================
# LOOP PRINCIPAL - MODO TESTE
# ==============================================================================

async def main_loop():
    """Loop principal - MODO TESTE com email manual."""
    from playwright.async_api import async_playwright

    print_banner()

    cycle_num = 0

    async with async_playwright() as playwright:
        while True:
            # Pedir email do usuario a cada ciclo
            email_usuario = pedir_email_usuario()
            if not email_usuario:
                log("INFO", "Nenhum email fornecido. Encerrando.")
                break

            cycle_num += 1

            try:
                limpar_screenshots()

                success = await executar_ciclo_teste(cycle_num, playwright, email_usuario)

                # ZIP do ciclo
                zip_path = criar_zip_ciclo(cycle_num, include_screenshots=True)
                if zip_path:
                    log("ZIP", f"Logs do ciclo #{cycle_num} compactados!")
                    log("ZIP", f"Arquivo: {zip_path}")

                limpar_logs_ciclo()
                log_stats()

                # Perguntar se quer testar novamente
                print()
                try:
                    novamente = input(f"  {C.Y}>>> Testar novamente com outro email? (s/N): {C.W}").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    novamente = "n"

                if novamente not in ("s", "sim", "y", "yes"):
                    log("INFO", "Encerrando modo teste.")
                    break

            except KeyboardInterrupt:
                log("INFO", "Interrompido pelo usuario (Ctrl+C)")
                log_stats()
                break
            except Exception as e:
                log("FAIL", f"Erro fatal no ciclo #{cycle_num}: {str(e)}")
                debug_error(f"Fatal ciclo #{cycle_num}: {str(e)}", traceback.format_exc())
                criar_zip_ciclo(cycle_num, include_screenshots=True)
                await asyncio.sleep(2)


# ==============================================================================
# ENTRY POINT
# ==============================================================================

def main():
    """Entry point do script."""
    def signal_handler(sig, frame):
        print(f"\n{C.Y}[INFO]{C.R} Encerrando gracefully...")
        log_stats()
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
        zip_path = criar_zip_sessao()
        if zip_path:
            print(f"{C.G}[ZIP]{C.R} Sessao completa: {zip_path}")
    except Exception as e:
        print(f"\n{C.RD}[FATAL]{C.R} {str(e)}")
        traceback.print_exc()
        criar_zip_sessao()
        sys.exit(1)


if __name__ == "__main__":
    main()
