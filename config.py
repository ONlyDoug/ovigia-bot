import os
from dotenv import load_dotenv

# Carrega o .env para testes locais
load_dotenv()

TOKEN = os.environ.get("DISCORD_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL")

if not TOKEN or not DATABASE_URL:
    print("ERRO CRÍTICO: DISCORD_TOKEN ou DATABASE_URL não definidos!")
    print("Verifique as Variáveis de Ambiente na Discloud.")
    exit()