import asyncpg
import logging
import asyncio
from config import Config

logger = logging.getLogger("Database")

class DatabaseManager:
    """Gerencia a conexão e operações com o banco de dados PostgreSQL."""
    
    def __init__(self):
        self.pool = None

    async def connect(self):
        """Cria o pool de conexões."""
        if not Config.DB_HOST:
            logger.critical("Tentativa de conexão sem configuração de DB válida.")
            raise ValueError("Configuração de DB inválida")

        try:
            logger.info(f"Conectando ao banco de dados em {Config.DB_HOST}...")
            self.pool = await asyncpg.create_pool(
                user=Config.DB_USER,
                password=Config.DB_PASSWORD,
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                database=Config.DB_NAME,
                # CRÍTICO: statement_cache_size=0 para Supabase Transaction Mode
                statement_cache_size=0,
                min_size=1,
                max_size=10,
                timeout=30,
                command_timeout=30
            )
            logger.info("Conexão com PostgreSQL estabelecida com sucesso.")
        except Exception as e:
            logger.critical(f"Falha fatal na conexão com DB: {e}")
            raise e

    async def close(self):
        """Fecha o pool de conexões."""
        if self.pool:
            await self.pool.close()
            logger.info("Conexão com DB fechada.")

    async def execute_query(self, query, *args):
        """Executa queries de escrita (INSERT, UPDATE, DELETE)."""
        if not self.pool:
            await self.connect()

        try:
            async with self.pool.acquire() as conn:
                return await conn.execute(query, *args)
        except Exception as e:
            logger.error(f"Erro em execute_query: {e} | Query: {query}")
            raise e

    async def fetchrow_query(self, query, *args):
        """Busca uma única linha (SELECT)."""
        if not self.pool:
            await self.connect()

        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchrow(query, *args)
        except Exception as e:
            logger.error(f"Erro em fetchrow_query: {e} | Query: {query}")
            raise e

    async def fetch_query(self, query, *args):
        """Busca múltiplas linhas (SELECT)."""
        if not self.pool:
            await self.connect()

        try:
            async with self.pool.acquire() as conn:
                return await conn.fetch(query, *args)
        except Exception as e:
            logger.error(f"Erro em fetch_query: {e} | Query: {query}")
            raise e