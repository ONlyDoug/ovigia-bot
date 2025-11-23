import asyncpg
import logging
from config import Config

logger = logging.getLogger("Database")

class DatabaseManager:
    def __init__(self, host, port, database, user, password):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.pool = None

    async def connect(self):
        """Estabelece o pool de conexão com o banco de dados."""
        if not self.host:
            logger.critical("Configuração do banco de dados ausente. Não é possível conectar.")
            return

        try:
            # statement_cache_size=0 é CRÍTICO para Transaction Poolers do Supabase
            self.pool = await asyncpg.create_pool(
                user=self.user,
                password=self.password,
                host=self.host,
                port=self.port,
                database=self.database,
                statement_cache_size=0,
                min_size=1,
                max_size=10
            )
            logger.info("Conectado ao banco de dados PostgreSQL com sucesso.")
        except Exception as e:
            logger.critical(f"Falha ao conectar ao banco de dados: {e}")
            raise e

    async def close(self):
        """Fecha o pool de conexão com o banco de dados."""
        if self.pool:
            await self.pool.close()
            logger.info("Conexão com o banco de dados fechada.")

    async def execute_query(self, query, *args):
        """Executa uma query (INSERT, UPDATE, DELETE) com lógica de reconexão automática."""
        if not self.pool:
            await self.connect()

        try:
            async with self.pool.acquire() as connection:
                return await connection.execute(query, *args)
        except (asyncpg.InterfaceError, asyncpg.PostgresConnectionError) as e:
            logger.warning(f"Conexão com o banco de dados perdida durante execute. Reconectando... Erro: {e}")
            await self.connect()
            # Tentar novamente uma vez
            async with self.pool.acquire() as connection:
                return await connection.execute(query, *args)
        except Exception as e:
            logger.error(f"Erro ao executar query: {query} | Args: {args} | Erro: {e}")
            raise e

    async def fetch_query(self, query, *args):
        """Busca resultados (SELECT) com lógica de reconexão automática."""
        if not self.pool:
            await self.connect()

        try:
            async with self.pool.acquire() as connection:
                return await connection.fetch(query, *args)
        except (asyncpg.InterfaceError, asyncpg.PostgresConnectionError) as e:
            logger.warning(f"Conexão com o banco de dados perdida durante fetch. Reconectando... Erro: {e}")
            await self.connect()
            # Tentar novamente uma vez
            async with self.pool.acquire() as connection:
                return await connection.fetch(query, *args)
        except Exception as e:
            logger.error(f"Erro ao buscar query: {query} | Args: {args} | Erro: {e}")
            raise e

    async def fetchrow_query(self, query, *args):
        """Busca uma única linha."""
        if not self.pool:
            await self.connect()

        try:
            async with self.pool.acquire() as connection:
                return await connection.fetchrow(query, *args)
        except (asyncpg.InterfaceError, asyncpg.PostgresConnectionError) as e:
            logger.warning(f"Conexão com o banco de dados perdida durante fetchrow. Reconectando... Erro: {e}")
            await self.connect()
            # Tentar novamente uma vez
            async with self.pool.acquire() as connection:
                return await connection.fetchrow(query, *args)
        except Exception as e:
            logger.error(f"Erro ao buscar linha: {query} | Args: {args} | Erro: {e}")
            raise e