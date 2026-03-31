# Análise do Screenshot 06_post_submit.png

## DESCOBERTA CRÍTICA
O screenshot mostra que **NÃO HÁ MENSAGEM DE ERRO VISÍVEL** na página!

O formulário simplesmente voltou ao estado preenchido, sem nenhum toastr, sem nenhuma mensagem de erro.
A página está exatamente como antes do submit - todos os campos preenchidos, checkboxes marcados.

## Implicação
A detecção de "documento ja cadastrado" é um **FALSO POSITIVO**!
O texto "cadastrado" provavelmente está no HTML do formulário em algum lugar (template JS, label, etc.)
e o código está detectando erroneamente como "Documento já cadastrado".

## O problema REAL
O formulário simplesmente NÃO FOI SUBMETIDO. O token reCAPTCHA HTTP bypass pode estar sendo
rejeitado silenciosamente pelo JavaScript do formulário antes mesmo de fazer o POST.

O formulário da Movida provavelmente:
1. Executa `grecaptcha.enterprise.execute()` via JS ao clicar ENVIAR
2. Se o token no textarea não for válido OU se o grecaptcha não estiver carregado, simplesmente não faz nada
3. O formulário fica parado sem mensagem de erro

## Solução
Preciso verificar se o botão ENVIAR realmente dispara o POST ou se o JS do formulário
bloqueia antes. Pode ser necessário:
1. Submeter via JavaScript diretamente (bypass do handler do botão)
2. Ou interceptar e fazer o POST HTTP manualmente com os dados do formulário
