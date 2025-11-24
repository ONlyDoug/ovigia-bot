import os
import re
import logging
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configuração de Logging Centralizada
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("Config")

class Config:
    """Centraliza e valida as configurações do bot."""
    
    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL")
    ALBION_API_URL = "https://gameinfo.albiononline.com/api/gameinfo"
    
    # Variáveis de conexão DB (preenchidas via parse)
    DB_USER = None
    DB_PASSWORD = None
    DB_HOST = None
    DB_PORT = None
    DB_NAME = None

    @classmethod
    def validate(cls):
        """Valida se as configurações críticas estão presentes."""
        if not cls.DISCORD_TOKEN:
            logger.critical("DISCORD_TOKEN não encontrado nas variáveis de ambiente!")
            return False
        if not cls.DATABASE_URL:
            logger.critical("DATABASE_URL não encontrada nas variáveis de ambiente!")
            return False
        
        # Parse da URL do Banco
        return cls._parse_database_url()

    @classmethod
    def _parse_database_url(cls):
        """Analisa a string de conexão do PostgreSQL."""
        try:
            # Regex para postgresql://user:pass@host:port/dbname
            pattern = r"(?:postgresql|postgres)://([^:]+):([^@]+)@([^:/]+)(?::(\d+))?/([^?]+)"
            match = re.search(pattern, cls.DATABASE_URL)
            
            if match:
                cls.DB_USER = match.group(1)
                cls.DB_PASSWORD = match.group(2)
                cls.DB_HOST = match.group(3)
                cls.DB_PORT = match.group(4) or "5432"
                cls.DB_NAME = match.group(5)
                logger.info(f"Configuração DB carregada: Host={cls.DB_HOST}, DB={cls.DB_NAME}")
                return True
            else:
                logger.error("Formato de DATABASE_URL inválido.")
                return False
        except Exception as e:
            logger.error(f"Erro ao analisar DATABASE_URL: {e}")
            return False

# Executar validação ao importar
if not Config.validate():
    logger.warning("Configuração inicial falhou ou está incompleta.")