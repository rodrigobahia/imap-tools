# sync — Migração IMAP com imapsync

Resumo

- Script: `sync/script.py`
- Objetivo: migrar caixas entre dois servidores IMAP usando `imapsync`.

Variáveis obrigatórias (.env)

Crie/edite `sync/.env` com as seguintes variáveis (obrigatórias):

- `HOST_ORIGEM` — host do servidor de origem
- `PORTA_ORIGEM` — porta (ex: 993)
- `SSL_ORIGEM` — `true`/`false`
- `HOST_DESTINO` — host do servidor destino
- `PORTA_DESTINO` — porta (ex: 993)
- `SSL_DESTINO` — `true`/`false`
- `CSV_FILE` — arquivo CSV com contas (ex: `contas.csv`)
- `TIMEOUT` — timeout (segundos) para conexões de socket
- `PROMPT_ON_ERROR` — `true`/`false` (se deve perguntar ao usuário ao ocorrer erro)

Instalação

Recomendado criar um virtualenv e instalar dependências:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r sync/requirements.txt
```

Uso

1. Preencha `sync/.env` com os valores corretos.
2. Prepare o CSV (`CSV_FILE`) com colunas: `email_origem, senha_origem, email_destino, senha_destino`.
3. Execute:

```bash
python sync/script.py
```

Notas de segurança

- Este projeto é público — NÃO coloque credenciais reais em commits. Use o `.env` local e adicione-o ao `.gitignore`.
- As senhas das contas são lidas do CSV; proteja esse arquivo também.

Logging

Se desejar gravar a saída do script em arquivo de log com timestamp, crie a pasta `logs` e use `tee`:

```bash
mkdir -p logs
python sync/script.py | tee logs/execucao_$(date +%Y%m%d_%H%M%S).log
```
