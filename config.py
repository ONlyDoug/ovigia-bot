import os
import re
import logging
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configuração de Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Config")

# Token do Bot
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")

# Configuração do Banco de Dados
DATABASE_URL = os.getenv("DATABASE_URL")

DB_USER = None
DB_PASSWORD = None
DB_HOST = None
DB_PORT = None
DB_NAME = None

if DATABASE_URL:
    # Regex para analisar a string de conexão
    # Formato: postgresql://user:password@host:port/dbname
    # ou postgres://...
    pattern = r"(?:postgresql|postgres)://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/([^?]+)"
    match = re.search(pattern, DATABASE_URL)
    
    if match:
        DB_USER = match.group(1)
        DB_PASSWORD = match.group(2)
        DB_HOST = match.group(3)
        DB_PORT = match.group(4) or "5432" # Padrão 5432 se ausente
        DB_NAME = match.group(5)
        logger.info(f"Configuração do banco de dados analisada com sucesso: Host={DB_HOST}, DB={DB_NAME}")
    else:
        logger.error("Não foi possível analisar DATABASE_URL. Certifique-se de que segue o formato postgresql://user:pass@host:port/dbname.")
else:
    logger.error("DATABASE_URL não encontrada nas variáveis de ambiente.")

# Configuração da API do Albion
ALBION_API_URL = "https://gameinfo.albiononline.com/api/gameinfo"