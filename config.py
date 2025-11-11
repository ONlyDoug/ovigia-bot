import os
from dotenv import load_dotenv
import urllib.parse # Importa a biblioteca para fazer o parse de URLs

# Carrega o .env para testes locais
load_dotenv()

TOKEN = os.environ.get("DISCORD_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL") # Ex: postgresql://user:pass@host:port/db

if not TOKEN or not DATABASE_URL:
    print("ERRO CRÍTICO: DISCORD_TOKEN ou DATABASE_URL não definidos!")
    exit()

# --- NOVA LÓGICA DE PARSE ---
try:
    # Desmonta a URL da base de dados
    url = urllib.parse.urlparse(DATABASE_URL)
    
    DB_USER = url.username
    DB_PASSWORD = url.password
    DB_HOST = url.hostname
    DB_PORT = url.port
    DB_NAME = url.path[1:] # Remove o '/' inicial do caminho
    
    # Verifica se conseguimos desmontar tudo
    if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME]):
        raise ValueError("A URL da base de dados está incompleta ou mal formatada.")
        
except Exception as e:
    print(f"ERRO CRÍTICO: Falha ao 'desmontar' o DATABASE_URL.")
    print("Verifique se o link está completo: postgresql://utilizador:senha@host:porta/base_de_dados")
    print(f"Erro: {e}")
    exit()