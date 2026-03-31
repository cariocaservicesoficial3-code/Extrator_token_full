#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AJATO TOKEN GENERATOR V7.0 - Gerador de Pessoa
Gera dados pessoais fake via 4devs + utilitários.
"""

import re
import random
import string
import requests
import traceback
import unicodedata

from logger import log, debug_event, debug_error


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
    tamanho = random.randint(10, 14)
    pool = string.ascii_letters + string.digits + especiais
    while len(senha) < tamanho:
        senha.append(random.choice(pool))
    random.shuffle(senha)
    return "".join(senha)


# ==============================================================================
# 4DEVS - GERADOR DE PESSOA
# ==============================================================================

def gerar_pessoa_4devs():
    """Gera pessoa fake via 4devs."""
    log("API", "Gerando pessoa via 4devs...")
    try:
        url = "https://www.4devs.com.br/ferramentas_online.php"
        idade_min = random.randint(21, 50)
        payload = f"acao=gerar_pessoa&sexo=I&pontuacao=S&idade={idade_min}&cep_estado=SP&txt_qtde=1&cep_cidade="
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "Referer": "https://www.4devs.com.br/gerador_de_pessoas",
        }
        resp = requests.post(url, data=payload, headers=headers, timeout=15)

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
    "ferraz de vasconcelos": "3515707",
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
    """Retorna código IBGE da cidade."""
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
