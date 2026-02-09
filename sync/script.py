import csv
import imaplib
import subprocess
import sys
import socket
import time
import os
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
      # only set if not present
      if k and k not in os.environ:
        os.environ[k] = v


def _get_required_env(name):
  v = os.getenv(name)
  if v is None or v == "":
    _fatal(f"Variável obrigatória '{name}' não encontrada no .env. Atualize sync/.env e tente novamente.")
  return v


# Carrega .env obrigatoriamente (encerra se não existir)
_load_env_required()

# =========================
# CONFIGURAÇÕES FIXAS
# =========================
# Lê configurações sensíveis obrigatórias do .env
try:
  ORIGEM = {
    "host": _get_required_env("HOST_ORIGEM"),
    "porta": int(_get_required_env("PORTA_ORIGEM")),
    "ssl": _get_required_env("SSL_ORIGEM").strip().lower() in ("1", "true", "yes", "y", "on"),
  }
except ValueError:
  _fatal("ORIGEM deve ser um número inteiro válido no .env")

try:
  DESTINO = {
    "host": _get_required_env("HOST_DESTINO"),
    "porta": int(_get_required_env("PORTA_DESTINO")),
    "ssl": _get_required_env("SSL_DESTINO").strip().lower() in ("1", "true", "yes", "y", "on"),
  }
except ValueError:
  _fatal("DESTINO deve ser um número inteiro válido no .env")

CSV_FILE = _get_required_env("CSV_FILE")

# Tempo máximo (segundos) para tentativas de conexão de socket
try:
  TIMEOUT = int(_get_required_env("TIMEOUT"))
except ValueError:
  _fatal("TIMEOUT deve ser um número inteiro válido no .env")
socket.setdefaulttimeout(TIMEOUT)

# Se True: ao ocorrer erro na migração de uma caixa, pergunta ao usuário se deve continuar.
# Se False: continua automaticamente até processar todas as contas do CSV.
PROMPT_ON_ERROR = _get_required_env("PROMPT_ON_ERROR").strip().lower() in ("1", "true", "yes", "y", "on")


# =========================
# FUNÇÕES
# =========================

def testar_login(email, senha, host, porta, ssl):
  print(f"   → Conectando {host}:{porta} (ssl={ssl})...")
  sys.stdout.flush()
  try:
    if ssl:
      imap = imaplib.IMAP4_SSL(host, porta)
    else:
      imap = imaplib.IMAP4(host, porta)

    print("   → Conexão estabelecida, tentando login...")
    sys.stdout.flush()

    imap.login(email, senha)
    imap.logout()
    return True, "OK"
  except socket.timeout:
    return False, f"Timeout ao conectar em {host}:{porta}"
  except Exception as e:
    return False, str(e)


def testar_todos_logins(contas):
  print("\n🔍 TESTE DE LOGIN DAS CONTAS\n")
  erros = False

  for c in contas:
    print(f"📧 {c['email_origem']}")

    ok_origem, msg_origem = testar_login(
      c["email_origem"],
      c["senha_origem"],
      ORIGEM["host"],
      ORIGEM["porta"],
      ORIGEM["ssl"]
    )

    ok_destino, msg_destino = testar_login(
      c["email_destino"],
      c["senha_destino"],
      DESTINO["host"],
      DESTINO["porta"],
      DESTINO["ssl"]
    )

    print(f"   Origem  : {'✅ OK' if ok_origem else '❌ ERRO'}")
    if not ok_origem:
      print(f"     ↳ {msg_origem}")

    print(f"   Destino : {'✅ OK' if ok_destino else '❌ ERRO'}")
    if not ok_destino:
      print(f"     ↳ {msg_destino}")

    if not ok_origem or not ok_destino:
      erros = True

    print("-" * 50)

  return not erros


def executar_migracao(contas):
  print("\n🚀 INICIANDO MIGRAÇÃO COM IMAPSYNC\n")

  for c in contas:
    print(f"\n📧 Migrando {c['email_origem']} → {c['email_destino']}")

    cmd = [
      "imapsync",
      "--host1", ORIGEM["host"],
      "--user1", c["email_origem"],
      "--password1", c["senha_origem"],
      "--ssl1",

      "--host2", DESTINO["host"],
      "--user2", c["email_destino"],
      "--password2", c["senha_destino"],
      "--ssl2",
      "--sslargs2", "SSL_verify_mode=0",
      "--automap",
      "--syncinternaldates"
    ]

    # print comando (mascarando senhas) para diagnóstico
    import shlex

    redacted = []
    i = 0
    while i < len(cmd):
      token = cmd[i]
      if token in ("--password1", "--password2") and i + 1 < len(cmd):
        redacted.append(token)
        redacted.append("****")
        i += 2
        continue
      redacted.append(token)
      i += 1

    print("   → Executando:", " ".join(shlex.quote(x) for x in redacted))
    sys.stdout.flush()

    try:
      # executa diretamente para que o imapsync escreva no stdout em tempo real
      subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
      print(f"❌ Erro ao migrar {c['email_origem']} (codigo {e.returncode})")
      if PROMPT_ON_ERROR:
        resp = input("Deseja continuar com os próximos? (s/n): ").lower()
        if resp != "s":
          print("⛔ Migração interrompida pelo usuário.")
          sys.exit(1)
      else:
        print("⚠ Continuando automaticamente (PROMPT_ON_ERROR=False)")

  print("\n✅ Migração finalizada com sucesso!")


def executar_migracao_conta(c, vezes):
  """Executa o imapsync para a conta `c` repetidas `vezes` vezes, aguardando 2 minutos entre execuções."""
  print(f"\n📧 Migrando {c['email_origem']} → {c['email_destino']}")

  for i in range(1, vezes + 1):
    print(f"Executando: {i}")

    cmd = [
      "imapsync",
      "--host1", ORIGEM["host"],
      "--user1", c["email_origem"],
      "--password1", c["senha_origem"],
      "--ssl1",

      "--host2", DESTINO["host"],
      "--user2", c["email_destino"],
      "--password2", c["senha_destino"],
      "--ssl2",
      "--sslargs2", "SSL_verify_mode=0",
      "--automap",
      "--syncinternaldates"
    ]

    import shlex

    # mascarar senhas para imprimir
    redacted = []
    j = 0
    while j < len(cmd):
      token = cmd[j]
      if token in ("--password1", "--password2") and j + 1 < len(cmd):
        redacted.append(token)
        redacted.append("****")
        j += 2
        continue
      redacted.append(token)
      j += 1

    print("   → Executando:", " ".join(shlex.quote(x) for x in redacted))
    sys.stdout.flush()

    try:
      subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
      print(f"❌ Erro ao migrar {c['email_origem']} (codigo {e.returncode})")
      print("⚠ Continuando automaticamente (sem prompts)")

    # se ainda falta executar mais vezes, aguardar 2 minutos antes da próxima execução
    if i < vezes:
      print("Aguardando 2 minutos antes da próxima execução...")
      time.sleep(120)

  print(f"\n✅ Migração da conta {c['email_origem']} finalizada ({vezes} execuções).")


def carregar_contas():
  with open(CSV_FILE, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    contas = list(reader)

  if not contas:
    raise Exception("CSV vazio ou inválido.")

  return contas


def main():
  contas = carregar_contas()

  print("\nO que você deseja fazer?")
  print("1 - Testar login das contas")
  print("2 - Iniciar migração diretamente")
  print("3 - Migrar uma caixa selecionada (execuções múltiplas)")
  opcao = input("Escolha (1 ou 2): ").strip()

  if opcao == "1":
    sucesso = testar_todos_logins(contas)
    if sucesso:
      resp = input("\nTodos os logins OK. Deseja iniciar a migração agora? (s/n): ").lower()
      if resp == "s":
        executar_migracao(contas)
      else:
        print("✔ Encerrado sem migrar.")
    else:
      print("\n⚠️ Existem erros de login. Corrija antes de migrar.")

  elif opcao == "2":
    executar_migracao(contas)

  elif opcao == "3":
    print("\nEscolha a conta para executar:")
    for i, c in enumerate(contas, start=1):
      print(f"{i} - {c['email_origem']} -> {c['email_destino']}")

    escolha = input("Escolha o número da conta: ").strip()
    try:
      idx = int(escolha) - 1
      if idx < 0 or idx >= len(contas):
        raise ValueError()
    except Exception:
      print("❌ Escolha inválida.")
      return

    vezes_str = input("Quantas vezes deve ser executado? ").strip()
    try:
      vezes = int(vezes_str)
      if vezes <= 0:
        raise ValueError()
    except Exception:
      print("❌ Número de execuções inválido.")
      return

    executar_migracao_conta(contas[idx], vezes)

  else:
    print("❌ Opção inválida.")


if __name__ == "__main__":
  main()
