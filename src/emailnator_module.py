#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AJATO TOKEN GENERATOR V7.0 - Módulo Emailnator
Gerenciamento de emails temporários via Emailnator.
Suporte dual: requests (rápido) + Playwright fallback (bypass Cloudflare).
"""

import re
import time
import quopri
import json
import requests
import traceback
from urllib.parse import unquote

from config import (
    EMAILNATOR_UA, EMAIL_POLL_FAST, EMAIL_POLL_SLOW,
    EMAIL_FAST_PHASE, MAX_INBOX_RETRIES
)
from logger import log, debug_write, debug_event, debug_error, STATS


class Emailnator:
    """Gerencia emails temporários via Emailnator."""

    def __init__(self, playwright_context=None):
        self.base_url = "https://www.emailnator.com"
        self.user_agent = EMAILNATOR_UA
        self.xsrf_token = None
        self.email = None
        self.use_playwright = False
        self.pw_context = playwright_context
        self.pw_page = None
        self.reset_session()

    def reset_session(self):
        """Reseta a sessão HTTP."""
        self.session = requests.Session()
        self.xsrf_token = None
        self.email = None
        log("DEBUG", "Emailnator: sessao resetada")

    async def init_playwright_mode(self, context):
        """Inicializa modo Playwright para bypass Cloudflare."""
        self.pw_context = context
        self.use_playwright = True
        log("PW", "Emailnator: modo Playwright ativado (bypass Cloudflare)")

        try:
            self.pw_page = await context.new_page()
            await self.pw_page.goto(self.base_url, wait_until="networkidle", timeout=30000)
            await self.pw_page.wait_for_timeout(3000)

            # Extrair cookies do Playwright
            cookies = await context.cookies()
            for c in cookies:
                if c["name"] == "XSRF-TOKEN":
                    self.xsrf_token = unquote(c["value"])
                    log("OK", f"XSRF-TOKEN extraido via Playwright ({len(self.xsrf_token)} chars)")

                # Copiar cookies para session requests
                self.session.cookies.set(
                    c["name"], c["value"],
                    domain=c.get("domain", ".emailnator.com")
                )

            if not self.xsrf_token:
                # Tentar extrair do meta tag ou JS
                token = await self.pw_page.evaluate("""
                    () => {
                        const meta = document.querySelector('meta[name="csrf-token"]');
                        if (meta) return meta.getAttribute('content');
                        const cookies = document.cookie.split(';');
                        for (const c of cookies) {
                            const [name, ...val] = c.trim().split('=');
                            if (name === 'XSRF-TOKEN') return decodeURIComponent(val.join('='));
                        }
                        return null;
                    }
                """)
                if token:
                    self.xsrf_token = token
                    log("OK", f"XSRF-TOKEN extraido via JS ({len(self.xsrf_token)} chars)")

            return bool(self.xsrf_token)
        except Exception as e:
            log("FAIL", f"Emailnator Playwright init falhou: {str(e)}")
            debug_error(f"Emailnator PW init: {str(e)}", traceback.format_exc())
            return False

    def extract_xsrf_token(self):
        """Extrai XSRF-TOKEN dos cookies do Session."""
        try:
            headers = {
                'User-Agent': self.user_agent,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
            }
            response = self.session.get(self.base_url, headers=headers, timeout=30)

            if response.status_code == 403:
                log("WARN", "Emailnator retornou 403 (Cloudflare). Precisa modo Playwright.")
                return False

            for cookie in self.session.cookies:
                if cookie.name == 'XSRF-TOKEN':
                    self.xsrf_token = unquote(cookie.value)
                    log("DEBUG", f"XSRF-TOKEN extraido dos cookies ({len(self.xsrf_token)} chars)")
                    return True

            for cookie in response.cookies:
                if cookie.name == 'XSRF-TOKEN':
                    self.xsrf_token = unquote(cookie.value)
                    log("DEBUG", f"XSRF-TOKEN extraido do response ({len(self.xsrf_token)} chars)")
                    return True

            log("WARN", "XSRF-TOKEN nao encontrado nos cookies!")
            return False
        except Exception as e:
            log("FAIL", f"extract_xsrf_token erro: {str(e)}")
            debug_error(f"extract_xsrf_token: {str(e)}", traceback.format_exc())
            return False

    async def _pw_extract_xsrf(self):
        """Extrai XSRF-TOKEN via Playwright."""
        if not self.pw_page:
            return False
        try:
            cookies = await self.pw_context.cookies()
            for c in cookies:
                if c["name"] == "XSRF-TOKEN":
                    self.xsrf_token = unquote(c["value"])
                    return True
            return False
        except Exception:
            return False

    def _get_headers(self):
        """Headers para requests ao Emailnator."""
        h = {
            'Content-Type': 'application/json',
            'Origin': 'https://www.emailnator.com',
            'Referer': 'https://www.emailnator.com/',
            'User-Agent': self.user_agent,
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'application/json, text/plain, */*',
        }
        if self.xsrf_token:
            h['X-XSRF-TOKEN'] = self.xsrf_token
        return h

    def _refresh_xsrf_from_cookies(self):
        """Atualiza XSRF-TOKEN dos cookies do Session."""
        for cookie in self.session.cookies:
            if cookie.name == 'XSRF-TOKEN':
                new_token = unquote(cookie.value)
                if new_token != self.xsrf_token:
                    self.xsrf_token = new_token
                    log("DEBUG", f"XSRF-TOKEN atualizado ({len(self.xsrf_token)} chars)")
                return

    async def _pw_api_call(self, endpoint, payload):
        """Faz chamada API via Playwright (bypass Cloudflare)."""
        if not self.pw_page:
            return None
        try:
            result = await self.pw_page.evaluate(f"""
                async () => {{
                    const resp = await fetch('{self.base_url}/{endpoint}', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/json',
                            'X-Requested-With': 'XMLHttpRequest',
                            'Accept': 'application/json, text/plain, */*',
                        }},
                        body: JSON.stringify({json.dumps(payload)}),
                        credentials: 'same-origin',
                    }});
                    const text = await resp.text();
                    return {{ status: resp.status, body: text }};
                }}
            """)
            return result
        except Exception as e:
            log("DEBUG", f"PW API call falhou: {str(e)}")
            return None

    def generate_email(self, email_type="dotGmail"):
        """Gera email temporário (sync wrapper)."""
        if self.use_playwright:
            log("DEBUG", "Emailnator: usando modo Playwright para gerar email")
            # Será chamado via async wrapper
            return None  # Precisa ser chamado via generate_email_async

        if not self.extract_xsrf_token():
            log("FAIL", "Nao foi possivel obter XSRF-TOKEN!")
            return None

        return self._generate_email_requests(email_type)

    async def generate_email_async(self, email_type="dotGmail"):
        """Gera email temporário (async, suporta Playwright)."""
        if self.use_playwright:
            return await self._generate_email_pw(email_type)
        else:
            # Tentar requests primeiro
            if not self.extract_xsrf_token():
                log("WARN", "Requests falhou, tentando Playwright...")
                if self.pw_context:
                    await self.init_playwright_mode(self.pw_context)
                    return await self._generate_email_pw(email_type)
                return None
            return self._generate_email_requests(email_type)

    def _generate_email_requests(self, email_type):
        """Gera email via requests."""
        try:
            url = f"{self.base_url}/generate-email"
            payload = {"email": [email_type]}
            headers = self._get_headers()

            log("DEBUG", f"Emailnator: gerando com tipo '{email_type}'")
            resp = self.session.post(url, json=payload, headers=headers, timeout=30)
            self._refresh_xsrf_from_cookies()

            if resp.status_code == 200:
                result = resp.json()
                if isinstance(result, dict) and 'email' in result:
                    emails = result['email']
                    self.email = emails[0] if isinstance(emails, list) else emails
                elif isinstance(result, list):
                    self.email = result[0]
                else:
                    log("FAIL", f"generate-email resposta inesperada: {result}")
                    return None

                log("OK", f"Email gerado ({email_type}): {self.email}")
                return self.email

            log("FAIL", f"generate-email HTTP {resp.status_code}")
            return None
        except Exception as e:
            log("FAIL", f"Emailnator generate: {str(e)}")
            return None

    async def _generate_email_pw(self, email_type):
        """Gera email via Playwright."""
        try:
            result = await self._pw_api_call("generate-email", {"email": [email_type]})
            if not result:
                return None

            if result["status"] == 200:
                data = json.loads(result["body"])
                if isinstance(data, dict) and 'email' in data:
                    emails = data['email']
                    self.email = emails[0] if isinstance(emails, list) else emails
                elif isinstance(data, list):
                    self.email = data[0]
                else:
                    log("FAIL", f"PW generate-email resposta: {data}")
                    return None

                log("OK", f"Email gerado via PW ({email_type}): {self.email}")
                return self.email

            log("FAIL", f"PW generate-email HTTP {result['status']}")
            return None
        except Exception as e:
            log("FAIL", f"PW generate: {str(e)}")
            return None

    async def get_messages_async(self):
        """Lista mensagens da inbox (async)."""
        if not self.email:
            return None

        for retry in range(MAX_INBOX_RETRIES):
            try:
                if self.use_playwright:
                    result = await self._pw_api_call("message-list", {"email": self.email})
                    if not result:
                        continue

                    if result["status"] == 200:
                        data = json.loads(result["body"])
                        msgs = data.get("messageData", [])
                        return msgs
                    elif result["status"] == 419:
                        log("WARN", f"PW message-list 419, re-extraindo token...")
                        await self._pw_extract_xsrf()
                        continue
                    else:
                        log("WARN", f"PW message-list HTTP {result['status']}")
                        continue
                else:
                    return self._get_messages_requests(retry)

            except Exception as e:
                log("DEBUG", f"get_messages erro (retry {retry+1}): {str(e)}")
                time.sleep(1)

        return []

    def get_messages(self):
        """Lista mensagens (sync, para compatibilidade)."""
        if self.use_playwright:
            return None  # Precisa ser chamado via get_messages_async
        return self._get_messages_requests(0)

    def _get_messages_requests(self, retry=0):
        """Lista mensagens via requests."""
        if not self.email:
            return None

        try:
            if not self.xsrf_token:
                self.extract_xsrf_token()

            url = f"{self.base_url}/message-list"
            payload = {"email": self.email}
            headers = self._get_headers()

            resp = self.session.post(url, json=payload, headers=headers, timeout=30)
            self._refresh_xsrf_from_cookies()

            if resp.status_code == 419:
                log("WARN", f"message-list 419, re-extraindo token...")
                STATS["inbox_errors"] += 1
                self.extract_xsrf_token()
                headers = self._get_headers()
                resp = self.session.post(url, json=payload, headers=headers, timeout=30)
                self._refresh_xsrf_from_cookies()

            if resp.status_code == 500:
                log("WARN", f"message-list 500, aguardando 2s...")
                STATS["inbox_errors"] += 1
                time.sleep(2)
                self.extract_xsrf_token()
                return []

            if resp.status_code == 200:
                data = resp.json()
                msgs = data.get("messageData", [])
                return msgs
            else:
                log("WARN", f"message-list HTTP {resp.status_code}")
                STATS["inbox_errors"] += 1
                return []

        except Exception as e:
            log("DEBUG", f"get_messages erro: {str(e)}")
            return []

    async def get_message_content_async(self, msg_id):
        """Lê conteúdo de email (async)."""
        if self.use_playwright:
            try:
                result = await self._pw_api_call("message-list", {
                    "email": self.email,
                    "messageID": msg_id
                })
                if result and result["status"] == 200:
                    return result["body"]
                return ""
            except Exception:
                return ""
        else:
            return self.get_message_content(msg_id)

    def get_message_content(self, msg_id):
        """Lê conteúdo de email (sync)."""
        for retry in range(2):
            try:
                if not self.xsrf_token:
                    self.extract_xsrf_token()

                url = f"{self.base_url}/message-list"
                payload = {"email": self.email, "messageID": msg_id}
                headers = self._get_headers()

                resp = self.session.post(url, json=payload, headers=headers, timeout=30)
                self._refresh_xsrf_from_cookies()

                if resp.status_code == 419:
                    self.extract_xsrf_token()
                    headers = self._get_headers()
                    resp = self.session.post(url, json=payload, headers=headers, timeout=30)
                    self._refresh_xsrf_from_cookies()

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
        """Extrai links do conteúdo do email com decodificação quopri."""
        if not html_content:
            return []

        try:
            decoded_content = quopri.decodestring(html_content.encode()).decode('utf-8', errors='ignore')
        except Exception:
            decoded_content = html_content

        links = re.findall(r'href=["\']?(https?://[^\s"\'<>]+)', decoded_content)
        url_pattern = r'https?://[^\s<>"\']+|www\.[^\s<>"\']+'
        loose_urls = re.findall(url_pattern, decoded_content)

        all_links = []
        for link in links + loose_urls:
            link = link.rstrip(')').rstrip('\\').rstrip('"').rstrip("'").rstrip(';').rstrip('&')
            if link not in all_links:
                all_links.append(link)

        log("DEBUG", f"Links encontrados no email: {len(all_links)}")
        for i, link in enumerate(all_links[:15]):
            short = link[:120] + "..." if len(link) > 120 else link
            log("DEBUG", f"  Link [{i}]: {short}")
        return all_links

    def find_best_link(self, links, pattern):
        """Encontra o melhor link com o padrão especificado."""
        for link in links:
            if "sendgrid" in link.lower() and pattern.lower() in link.lower():
                return link

        sendgrid_links = [l for l in links if "sendgrid" in l.lower()]
        if sendgrid_links and pattern == "sendgrid":
            for link in sendgrid_links:
                if "unsubscribe" not in link.lower() and "open" not in link.lower():
                    return link
            return sendgrid_links[0]

        for link in links:
            if pattern.lower() in link.lower():
                return link

        return None

    def find_link_by_index(self, content, target_index=5):
        """Extrai link pelo índice (fallback)."""
        if not content:
            return None
        try:
            decoded = quopri.decodestring(content.encode()).decode('utf-8', errors='ignore')
        except Exception:
            decoded = content

        urls = re.findall(r'https?://[^\s<>"]+', decoded)
        unique = []
        for u in urls:
            u = u.rstrip(')').rstrip('\\').rstrip('"').rstrip("'")
            if u not in unique:
                unique.append(u)

        if len(unique) > target_index:
            return unique[target_index]
        return None

    async def wait_for_email_async(self, sender_filter="", timeout=60, link_pattern="sendgrid", accept_any=False):
        """Aguarda email na inbox com polling adaptativo (async)."""
        import asyncio
        filter_desc = 'QUALQUER' if accept_any else sender_filter
        log("EMAIL", f"Aguardando email de '{filter_desc}' (timeout: {timeout}s)...")

        start = time.time()
        seen_ids = set()
        poll_count = 0

        while time.time() - start < timeout:
            poll_count += 1
            elapsed = time.time() - start

            messages = await self.get_messages_async()

            if messages is None:
                log("WARN", f"Inbox retornou None no poll #{poll_count}, re-extraindo XSRF...")
                if self.use_playwright:
                    await self._pw_extract_xsrf()
                else:
                    self.extract_xsrf_token()
                await asyncio.sleep(2)
                continue

            if poll_count % 3 == 1:
                log("DEBUG", f"Inbox poll #{poll_count}: {len(messages)} msgs ({int(elapsed)}s/{timeout}s)")

            for msg in messages:
                msg_id = msg.get("messageID", "")
                if msg_id in seen_ids or msg_id == "ADSVPN":
                    continue
                seen_ids.add(msg_id)

                from_addr = msg.get("from", "")
                subject = msg.get("subject", "")
                log("EMAIL", f"Novo email: De={from_addr} | Assunto={subject}")

                is_match = False
                if accept_any:
                    spam_kw = ["samsung", "apple", "newsletter", "promo", "adsvpn"]
                    is_spam = any(kw in (from_addr + subject).lower() for kw in spam_kw)
                    is_match = not is_spam
                else:
                    search_terms = [sender_filter.lower()]
                    if "movida" in sender_filter.lower():
                        search_terms.extend([
                            "movida", "vetormovida", "vetormovida@movida.com.br",
                            "fidelidade movida", "movida.com.br"
                        ])
                    combined = (from_addr + " " + subject).lower()
                    is_match = any(term in combined for term in search_terms)

                if is_match:
                    log("EMAIL", f"Email MATCH! De: {from_addr}")
                    STATS["emails_recebidos"] += 1

                    content = await self.get_message_content_async(msg_id)
                    if content:
                        links = self.extract_links(content)
                        link = self.find_best_link(links, link_pattern)
                        if link:
                            return link

                        if link_pattern != "sendgrid":
                            link = self.find_best_link(links, "sendgrid")
                            if link:
                                return link

                        link = self.find_link_by_index(content, target_index=5)
                        if link:
                            return link

                        for idx in [4, 6, 3, 7, 2]:
                            link = self.find_link_by_index(content, target_index=idx)
                            if link and "sendgrid" in link.lower():
                                return link

                        for l in links:
                            if any(x in l.lower() for x in ["confirma", "ativa", "cadastro", "verify"]):
                                return l

                        log("WARN", f"Padrao '{link_pattern}' nao encontrado nos {len(links)} links")

            if elapsed < EMAIL_FAST_PHASE:
                await asyncio.sleep(EMAIL_POLL_FAST)
            else:
                await asyncio.sleep(EMAIL_POLL_SLOW)

        log("FAIL", f"Timeout {timeout}s esperando email de '{filter_desc}'")
        return None

    def wait_for_email(self, sender_filter="", timeout=60, link_pattern="sendgrid", accept_any=False):
        """Versão sync do wait_for_email (para compatibilidade)."""
        if self.use_playwright:
            return None  # Precisa ser chamado via wait_for_email_async

        filter_desc = 'QUALQUER' if accept_any else sender_filter
        log("EMAIL", f"Aguardando email de '{filter_desc}' (timeout: {timeout}s)...")

        start = time.time()
        seen_ids = set()
        poll_count = 0

        while time.time() - start < timeout:
            poll_count += 1
            elapsed = time.time() - start

            messages = self.get_messages()

            if messages is None:
                log("WARN", f"Inbox retornou None, re-extraindo XSRF...")
                self.extract_xsrf_token()
                time.sleep(2)
                continue

            if poll_count % 3 == 1:
                log("DEBUG", f"Inbox poll #{poll_count}: {len(messages)} msgs ({int(elapsed)}s/{timeout}s)")

            for msg in messages:
                msg_id = msg.get("messageID", "")
                if msg_id in seen_ids or msg_id == "ADSVPN":
                    continue
                seen_ids.add(msg_id)

                from_addr = msg.get("from", "")
                subject = msg.get("subject", "")
                log("EMAIL", f"Novo email: De={from_addr} | Assunto={subject}")

                is_match = False
                if accept_any:
                    spam_kw = ["samsung", "apple", "newsletter", "promo", "adsvpn"]
                    is_spam = any(kw in (from_addr + subject).lower() for kw in spam_kw)
                    is_match = not is_spam
                else:
                    search_terms = [sender_filter.lower()]
                    if "movida" in sender_filter.lower():
                        search_terms.extend([
                            "movida", "vetormovida", "vetormovida@movida.com.br",
                            "fidelidade movida", "movida.com.br"
                        ])
                    combined = (from_addr + " " + subject).lower()
                    is_match = any(term in combined for term in search_terms)

                if is_match:
                    log("EMAIL", f"Email MATCH! De: {from_addr}")
                    STATS["emails_recebidos"] += 1

                    content = self.get_message_content(msg_id)
                    if content:
                        links = self.extract_links(content)
                        link = self.find_best_link(links, link_pattern)
                        if link:
                            return link

                        if link_pattern != "sendgrid":
                            link = self.find_best_link(links, "sendgrid")
                            if link:
                                return link

                        link = self.find_link_by_index(content, target_index=5)
                        if link:
                            return link

                        for idx in [4, 6, 3, 7, 2]:
                            link = self.find_link_by_index(content, target_index=idx)
                            if link and "sendgrid" in link.lower():
                                return link

                        for l in links:
                            if any(x in l.lower() for x in ["confirma", "ativa", "cadastro", "verify"]):
                                return l

                        log("WARN", f"Padrao '{link_pattern}' nao encontrado nos {len(links)} links")

            if elapsed < EMAIL_FAST_PHASE:
                time.sleep(EMAIL_POLL_FAST)
            else:
                time.sleep(EMAIL_POLL_SLOW)

        log("FAIL", f"Timeout {timeout}s esperando email de '{filter_desc}'")
        return None

    async def close(self):
        """Fecha a página Playwright do Emailnator."""
        if self.pw_page:
            try:
                await self.pw_page.close()
            except Exception:
                pass
            self.pw_page = None
