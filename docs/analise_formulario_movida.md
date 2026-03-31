# Análise do Formulário de Cadastro da Movida

## URL: https://www.movida.com.br/usuario/cadastro

## Campos do Formulário (id="formCadastro")

### Informações Pessoais
- `#brasileiro` (radio) - Brasileiro
- `#estrangeiro` (radio) - Estrangeiro
- `#cpf` (text) - CPF
- `#nome` (text) - Nome
- `#data_nasc` (text) - Data de Nascimento
- `#telefone` (text) - Telefone
- `#celular` (text) - Celular
- `#email` (email) - E-mail
- `#email_conf` (email) - Confirmação E-mail

### Endereço
- `#cep` (text) - CEP
- `#logradouro` (text) - Endereço
- `#numero` (text) - Número
- `#complemento` (text) - Complemento
- `#bairro` (text) - Bairro
- `#Pais` (select) - País
- `#uf_sel` (select) - Estado
- `#cidade_sel` (select) - Cidade

### Senha
- `#senha_cadastro` (password) - Senha
- `#senha_conf` (password) - Confirme sua senha

### Checkboxes (Fidelidade)
- Quero participar do Fidelidade Movida
- Estou ciente e de acordo com o Regulamento do Programa
- Aceito receber ofertas
- Estou ciente e de acordo com o Aviso de privacidade

### Botão Submit
- `#btnEnviaDados` - ENVIAR

## Observações
- O formulário usa reCAPTCHA Enterprise (invisível)
- País default: Brasil
- Estado e Cidade são selects dinâmicos (carregam via AJAX)
- CEP provavelmente auto-preenche endereço via API
- Campos com * são obrigatórios
