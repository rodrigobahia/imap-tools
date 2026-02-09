# backup — Backup de caixas IMAP

Resumo

- Script: `backup/script.py`
- Objetivo: criar backups de caixas IMAP em formato MBOX (via `imapsync`) ou EML (download direto).

Variáveis obrigatórias (.env)

Crie/edite `backup/.env` com as seguintes variáveis (obrigatórias):

- `IMAP_HOST` — host do servidor IMAP
- `IMAP_PORT` — porta (ex: `993`)
- `USE_SSL` — `true`/`false`
- `BACKUP_DIR` — diretório onde os backups serão gravados (ex: `backups`)
- `LOG_DIR` — diretório para logs (ex: `logs`)
- `BACKUP_CSV` — arquivo CSV com contas (ex: `backup.csv`)

Instalação

Recomendado criar um virtualenv e instalar dependências:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backup/requirements.txt
```

Uso

1. Preencha `backup/.env` com os valores reais.
2. Prepare o CSV (`BACKUP_CSV`) com colunas: `email, senha`.
3. Execute:

```bash
python backup/script.py
```

Notas de segurança

- Este repositório é público — NÃO coloque credenciais reais em commits. Adicione `backup/.env` e `backup.csv` ao `.gitignore`.

Logging

Para gravar a saída em um arquivo de log com timestamp, crie a pasta `logs` (se ainda não existir) e use `tee`:

```bash
mkdir -p logs
python backup/script.py | tee logs/execucao_$(date +%Y%m%d_%H%M%S).log
```
