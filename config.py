import os
from dotenv import load_dotenv
import re # Usaremos a biblioteca de Expressões Regulares (RegEx)

# Carrega o .env para testes locais
load_dotenv()

TOKEN = os.environ.get("DISCORD_TOKEN")
DATABASE_URL = os.environ.get("DATABASE_URL") # Ex: postgresql://user:pass@host:port/db

if not TOKEN or not DATABASE_URL:
    print("ERRO CRÍTICO: DISCORD_TOKEN ou DATABASE_URL não definidos!")
    exit()

# --- NOVA LÓGICA DE PARSE (Manual, sem validação) ---
try:
    # Formato esperado: postgresql://utilizador:senha@host:porta/base_de_dados
    # Usamos RegEx para extrair os grupos de forma segura
    
    # Esta expressão captura os 5 grupos que precisamos
    # Grupo 1: utilizador (Tudo depois de // e antes de :)
    # Grupo 2: senha (Tudo depois de : e antes de @)
    # Grupo 3: host (Tudo depois de @ e antes de :)
    # Grupo 4: porta (Os números depois de : e antes de /)
    # Grupo 5: base_de_dados (Tudo depois de / até o fim)
    match = re.search(r"postgresql://(.*?):(.*?)@(.*?):(\d+)/(.*)", DATABASE_URL)
    
    if not match:
        raise ValueError("Formato da URL do banco de dados não corresponde ao esperado.")

    groups = match.groups()
    
    DB_USER = groups[0]
    DB_PASSWORD = groups[1]
    DB_HOST = groups[2]     # Ex: 'aws-1-us-east-1.pooler.supabase.com'
    DB_PORT = int(groups[3])  # Ex: 6543
    DB_NAME = groups[4]     # Ex: 'postgres'
    
    if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME]):
        raise ValueError("A URL da base de dados está incompleta.")
        
except Exception as e:
    print(f"ERRO CRÍTICO: Falha ao 'desmontar' o DATABASE_URL.")
    print("Verifique se o link está completo: postgresql://utilizador:senha@host:porta/base_de_dados")
    print(f"Erro: {e}")
    exit()