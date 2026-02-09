# imap-tools

Ferramenta simples e prática para gerenciar migrações e backups de caixas IMAP.

Por que este projeto existe

Mudar provedores de e-mail ou extrair backups massivos de contas IMAP é uma tarefa repetitiva e sensível. Este repositório reúne scripts práticos que automatizam duas tarefas comuns:

- Migrar caixas entre dois servidores usando `imapsync` (`sync/`).
- Fazer backup de caixas em formato MBOX ou EML (`backup/`).

Principais características

- Uso por linha de comando, sem necessidade de instalação complexa.
- Configuração via `*.env` para manter credenciais fora do código.
- Logs opcionais com `tee` para auditoria e troubleshooting.
- Scripts preparados para rodar em lote a partir de CSVs.

Conteúdo

- [sync/](sync/README.md) — migração IMAP com `imapsync`.
- [backup/](backup/README.md) — backups MBOX/EML por IMAP.

Requisitos

- Python 3.8+
- `imapsync` disponível no `PATH` (para tarefas de migração/backup com imapsync)
- Recomenda-se criar um `virtualenv` e instalar `python-dotenv` se quiser carregar `.env` automaticamente.

Quickstart

1. Clone o repositório:

```bash
git clone <repo-url>
cd imap-tools
```

2. Edite os arquivos `sync/.env` e `backup/.env` com os valores do seu ambiente (veja os READMEs em `sync/` e `backup/`).

3. Execute um script (ex.: migração):

```bash
mkdir -p logs
python sync/script.py | tee logs/execucao_$(date +%Y%m%d_%H%M%S).log
```

Segurança e boas práticas

- ESTE REPOSITÓRIO É PÚBLICO: nunca coloque credenciais reais em commits.
- Adicione `sync/.env`, `backup/.env` e qualquer arquivo CSV com senhas ao seu `.gitignore` antes de commitar.
- Proteja o acesso às máquinas e aos arquivos de log que contenham dados sensíveis.

Contribuições

Contribuições são bem-vindas: abra issues para bugs ou features e faça pull-requests com mudanças claras e testadas.

Licença

Verifique o arquivo `LICENSE` no repositório para os termos de uso.

Mais informações

Consulte os READMEs dentro de `sync/` e `backup/` para instruções detalhadas e exemplos de `.env`.