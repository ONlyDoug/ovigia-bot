import os

# Token do Bot
TOKEN = os.environ.get("DISCORD_TOKEN")

# Chaves do Supabase
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not all([TOKEN, SUPABASE_URL, SUPABASE_KEY]):
    print("ERRO CRÍTICO: Variáveis de ambiente em falta!")
    print("Verifique: DISCORD_TOKEN, SUPABASE_URL, SUPABASE_KEY")
    exit()