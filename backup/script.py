import csv
import os
import subprocess
import sys
from datetime import datetime
import shutil
import mailbox
from email import policy
import imaplib
import email
import time
import re
from pathlib import Path


def _fatal(msg):
    print(msg)
    sys.exit(1)


def _load_env_required():
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        _fatal(f"Arquivo .env obrigatório não encontrado em: {env_path}")

    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except Exception:
        # fallback: parse .env manualmente into os.environ
        text = env_path.read_text(encoding="utf-8")
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip('"').strip("'")
            if k and k not in os.environ:
                os.environ[k] = v


def _get_required_env(name):
    v = os.getenv(name)
    if v is None or v == "":
        _fatal(f"Variável obrigatória '{name}' não encontrada no .env. Atualize backup/.env e tente novamente.")
    return v


# Carrega .env obrigatoriamente
_load_env_required()


# Lê configurações obrigatórias do .env (sem fallback)
IMAP_HOST = _get_required_env("IMAP_HOST")
try:
    IMAP_PORT = int(_get_required_env("IMAP_PORT"))
except ValueError:
    _fatal("IMAP_PORT deve ser um número inteiro válido em backup/.env")

USE_SSL = _get_required_env("USE_SSL").strip().lower() in ("1", "true", "yes", "y", "on")

BACKUP_DIR = _get_required_env("BACKUP_DIR")
LOG_DIR = _get_required_env("LOG_DIR")
BACKUP_CSV = _get_required_env("BACKUP_CSV")

os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)


def imap_download_eml(host, port, user, password, destino, log):
    """Conecta via IMAP e baixa cada mensagem como .eml em subpastas por pasta IMAP."""
    total = 0
    total_bytes = 0
    imap = imaplib.IMAP4_SSL(host, int(port))
    try:
        imap.login(user, password)
    except imaplib.IMAP4.error as e:
        raise RuntimeError(f"IMAP login failed: {e}")

    typ, mailboxes = imap.list()
    if typ != 'OK':
        log.write(f"LIST failed: {typ} {mailboxes}\n")
        return 0, 0

    # First pass: count total messages across all folders for progress reporting
    folder_infos = []  # list of (name, folder_safe, count)
    grand_total = 0
    for m in mailboxes:
        try:
            m_bytes = m if isinstance(m, bytes) else m.encode()
        except Exception:
            m_bytes = str(m).encode('utf-8', errors='replace')
        match = re.search(br'"([^"]+)"\s*$', m_bytes)
        if match:
            raw_name = match.group(1)
            try:
                name = raw_name.decode('utf-8')
            except Exception:
                try:
                    name = raw_name.decode('latin-1')
                except Exception:
                    name = raw_name.decode('utf-8', errors='replace')
        else:
            try:
                s = m_bytes.decode('utf-8', errors='replace')
            except Exception:
                s = str(m)
            parts = s.split()
            name = parts[-1].strip('"')

        # attempt select to count messages (try multiple quoting variants)
        def _try_select(name_to_try):
            try:
                return imap.select(name_to_try, readonly=True), name_to_try
            except Exception as e:
                return (None, e), name_to_try

        sel_result, used_name = _try_select(name)
        if sel_result[0] != 'OK':
            nm = name.strip('"')
            sel_result, used_name = _try_select(nm)
            if sel_result[0] != 'OK':
                qname = f'"{name}"'
                sel_result, used_name = _try_select(qname)
                if sel_result[0] != 'OK':
                    # give up on this folder
                    continue
                else:
                    name = used_name
            else:
                name = used_name

        typ, data = imap.search(None, 'ALL')
        if typ != 'OK':
            count = 0
        else:
            uids = data[0].split()
            count = len(uids)

        folder_safe = name.replace('/', '_').replace('"', '').replace(' ', '_')
        folder_infos.append((name, folder_safe, count))
        grand_total += count

    log.write(f"Total messages across all folders: {grand_total}\n")
    log.flush()

    # Second pass: download and report progress
    downloaded = 0
    skipped = 0
    for name, folder_safe, count in folder_infos:
        folder_dir = os.path.join(destino, folder_safe)
        os.makedirs(folder_dir, exist_ok=True)

        # robust select for second pass as well
        sel_result, used_name = _try_select(name)
        if sel_result[0] != 'OK':
            log.write(f"Skipping folder {name}: cannot select ({sel_result})\n")
            continue
        name = used_name

        typ, data = imap.search(None, 'ALL')
        if typ != 'OK' or not data or not data[0]:
            log.write(f"No messages in folder {name} or search failed: {data}\n")
            continue

        uids = data[0].split()
        log.write(f"Folder {name}: {len(uids)} messages\n")
        log.flush()

        for uid in uids:
            uid_str = uid.decode() if isinstance(uid, bytes) else str(uid)
            out_name = f"{uid_str}.eml"
            out_path = os.path.join(folder_dir, out_name)

            # skip if already downloaded (resume)
            if os.path.exists(out_path):
                skipped += 1
                log.write(f"Já existe, pulando: {out_path}\n")
                log.flush()
                continue

            try:
                typ, msgdata = imap.fetch(uid, '(RFC822)')
            except Exception as e:
                log.write(f"Fetch failed for UID {uid}: {e}\n")
                continue
            if typ != 'OK' or not msgdata:
                continue
            raw = None
            for part in msgdata:
                if isinstance(part, tuple) and part[1]:
                    raw = part[1]
                    break
            if raw is None:
                continue

            try:
                with open(out_path, 'wb') as outf:
                    outf.write(raw)
            except Exception as e:
                log.write(f"Failed to write {out_path}: {e}\n")
                continue

            downloaded += 1
            total += 1
            total_bytes += len(raw)

            # progress output
            percent = (downloaded / grand_total * 100) if grand_total else 0
            msg = f"Baixando: {downloaded}/{grand_total} ({percent:.1f}%) — pasta: {name}\n"
            print(msg, end='')
            log.write(msg)
            log.flush()

    try:
        imap.logout()
    except Exception:
        pass
    return total, total_bytes, skipped, grand_total



def get_imapsync_path():
    """Return full path to imapsync executable or None if not found."""
    for c in ("imapsync", "imapsync.exe"):
        p = shutil.which(c)
        if p:
            return p
    return None


def carregar_contas():
    # Espera um CSV com colunas: email, senha
    with open(BACKUP_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def listar_contas(contas):
    print("\n📧 Caixas disponíveis para backup:\n")
    print("0 - Todas as caixas")
    for i, c in enumerate(contas, start=1):
        print(f"{i} - {c.get('email')}")


def escolher_conta(contas):
    listar_contas(contas)
    escolha = input("\nEscolha o número da caixa (0 para todas): ")
    try:
        escolha_int = int(escolha)
    except ValueError:
        print("❌ Entrada inválida")
        sys.exit(1)

    if escolha_int == 0:
        return None

    if 1 <= escolha_int <= len(contas):
        return contas[escolha_int - 1]
    else:
        print("❌ Opção fora do intervalo")
        sys.exit(1)


def escolher_tipo_backup():
    print("\nTipo de backup:")
    print("1 - MBOX (recomendado)")
    print("2 - EML (um arquivo por mensagem)")
    opcao = input("Escolha (1 ou 2): ")

    if opcao == "1":
        return "mbox"
    elif opcao == "2":
        return "eml"
    else:
        print("❌ Opção inválida")
        sys.exit(1)


def escolher_fluxo_multiplas_contas():
    """Ao processar todas as contas, determina se o script deve avançar automático ou perguntar antes de cada conta."""
    print("\nQuando processar todas as contas:")
    print("1 - Continuar automaticamente para a próxima conta")
    print("2 - Perguntar antes de iniciar a próxima conta")
    opcao = input("Escolha (1 ou 2) [1]: ")
    if opcao.strip() == "" or opcao.strip() == "1":
        return "auto"
    elif opcao.strip() == "2":
        return "ask"
    else:
        print("❌ Opção inválida")
        sys.exit(1)


def escolher_inicio_contas(contas):
    """Ao processar todas as contas, permite escolher de qual índice iniciar (1..N)."""
    total = len(contas)
    escolha = input(f"\nDigite o número da conta para começar (1..{total}) [1]: ")
    if escolha.strip() == "":
        return 1
    try:
        v = int(escolha)
    except ValueError:
        print("❌ Entrada inválida")
        sys.exit(1)
    if 1 <= v <= total:
        return v
    else:
        print("❌ Opção fora do intervalo")
        sys.exit(1)


def executar_backup(conta, tipo):
    # arquivo `backup.csv` contém colunas `email` e `senha`
    email = conta.get("email")
    senha = conta.get("senha")

    # cria uma pasta separada por caixa de email dentro do caminho base
    safe_dir = email.replace("@", "_").replace("/", "_")
    destino = os.path.join(BACKUP_DIR, safe_dir)
    os.makedirs(destino, exist_ok=True)

    # verify imapsync exists on PATH
    def _get_imapsync_path():
        candidates = ["imapsync", "imapsync.exe"]
        for c in candidates:
            p = shutil.which(c)
            if p:
                return p
        return None

    imapsync_path = _get_imapsync_path()
    if not imapsync_path:
        raise FileNotFoundError(
            "imapsync executable not found on PATH. Install imapsync and ensure it's available in your PATH (or place imapsync.exe on Windows)."
        )

    start = datetime.now()
    safe_email = safe_dir
    log_file = os.path.join(LOG_DIR, f"backup_{safe_email}_{start.strftime('%Y%m%d_%H%M%S')}.log")

    print(f"\n🚀 Iniciando backup {tipo.upper()} de {email} — início: {start.isoformat()}\n")

    if tipo == "mbox":
        cmd = [
            imapsync_path,
            "--host1", IMAP_HOST,
            "--user1", email,
            "--password1", senha,
            "--ssl1",
            "--backup",
            f"--backupdir={destino}",
            "--nofoldersizes",
            "--usecache"
        ]
    else:  # eml
        # we'll perform direct IMAP download for EML instead of relying on imapsync
        cmd = None

    def _dir_stats(path):
        total_files = 0
        total_bytes = 0
        for root, _, files in os.walk(path):
            for f in files:
                total_files += 1
                try:
                    total_bytes += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
        return total_files, total_bytes

    # Executa e faz streaming do stdout/stderr para console e log
    with open(log_file, "w", encoding="utf-8", errors="replace") as log:
        log.write(f"Backup iniciado: {start.isoformat()}\n")
        log.write(f"Conta: {email}\n")
        if cmd:
            log.write(f"Comando: {' '.join(cmd)}\n\n")
        else:
            log.write(f"Comando: direct IMAP download (EML)\n\n")
        log.flush()

        returncode = 0
        if cmd:
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, universal_newlines=True)
                # stream
                for line in proc.stdout:
                    print(line, end='')
                    log.write(line)
                    log.flush()
                proc.wait()
                returncode = proc.returncode
            except KeyboardInterrupt:
                log.write('\nBackup interrompido pelo usuário (KeyboardInterrupt)\n')
                log.flush()
                try:
                    proc.terminate()
                except Exception:
                    pass
                raise
            except Exception as e:
                log.write(f"\nErro ao executar imapsync: {e}\n")
                log.flush()
                raise
        else:
            # we'll perform IMAP download for EML below
            returncode = None

        # if EML mode failed due to unknown option, fallback to MBOX+conversion
        end = datetime.now()
        duration = end - start

        files_count, bytes_count = _dir_stats(destino)
        if tipo == 'eml' and returncode is None:
            log.write('\nEML mode: performing direct IMAP download to EML files\n')
            log.flush()
            try:
                c_files, c_bytes, c_skipped, c_total = imap_download_eml(IMAP_HOST, IMAP_PORT, email, senha, destino, log)
            except Exception as e:
                log.write(f"IMAP EML download failed: {e}\n")
                log.flush()
                raise
            files_count, bytes_count = _dir_stats(destino)
            # resumo por conta: baixados / pulados / total
            log.write(f"Resumo desta execução: baixados={c_files}, pulados={c_skipped}, total_imap={c_total}\n")
            log.flush()
            print(f"Resumo desta execução: baixados={c_files}, pulados={c_skipped}, total_imap={c_total}")

        log.write("\n=== Resumo do backup ===\n")
        log.write(f"Fim: {end.isoformat()}\n")
        log.write(f"Duração: {duration}\n")
        log.write(f"Exit code: {returncode}\n")
        log.write(f"Arquivos no destino: {files_count}\n")
        log.write(f"Tamanho total (bytes): {bytes_count}\n")
        log.write(f"Destino: {destino}\n")
        log.flush()

    print(f"\n✅ Backup finalizado — conta: {email}")
    print(f"📁 Arquivos em: {destino} ({files_count} arquivos, {bytes_count} bytes)")
    print(f"📄 Log: {log_file}")


def main():
    contas = carregar_contas()

    # Check imapsync availability once and exit with helpful message if missing
    if not get_imapsync_path():
        print("❌ 'imapsync' not found in PATH. Install imapsync and ensure it's available in your PATH. On Windows place imapsync.exe on PATH or run via WSL.")
        sys.exit(1)

    conta = escolher_conta(contas)
    tipo = escolher_tipo_backup()

    if conta is None:
        # processar todas as contas em sequência, com opção de fluxo e índice inicial
        fluxo = escolher_fluxo_multiplas_contas()
        start_idx = escolher_inicio_contas(contas)
        for i in range(start_idx - 1, len(contas)):
            idx = i + 1
            c = contas[i]
            if fluxo == 'ask' and idx > start_idx:
                resp = input(f"\nContinuar para ({idx}/{len(contas)}) {c.get('email')}? (s/n): ")
                if resp.strip().lower() not in ('s', 'sim', 'y', 'yes'):
                    print("Operação interrompida pelo usuário.")
                    break

            print(f"\n--- ({idx}/{len(contas)}) Processando: {c.get('email')} ---")
            try:
                executar_backup(c, tipo)
            except Exception as e:
                print(f"Erro no backup de {c.get('email')}: {e}")
                # continuar com próxima conta
                continue
    else:
        executar_backup(conta, tipo)


if __name__ == "__main__":
    main()
