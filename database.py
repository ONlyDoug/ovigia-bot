import asyncpg
import asyncio

class DatabaseManager:
    def __init__(self, dsn: str, min_conn: int = 2, max_conn: int = 10):
        self._dsn = dsn
        self._pool = None
        print(f"DatabaseManager inicializado para DSN.")

    async def connect(self):
        """Inicializa o pool de conexões com asyncpg."""
        try:
            self._pool = await asyncpg.create_pool(
                dsn=self._dsn,
                min_size=min_conn,
                max_size=max_conn
            )
            print("Pool de conexões com a base de dados (asyncpg) inicializado com sucesso.")
        except Exception as e:
            print(f"ERRO CRÍTICO ao inicializar o pool de conexões: {e}")
            raise

    async def close(self):
        """Fecha o pool de conexões."""
        if self._pool:
            await self._pool.close()
            print("Pool de conexões fechado.")

    async def execute_query(self, query, *params, fetch=None):
        """Executa uma query de forma assíncrona."""
        if not self._pool:
            print("Pool de conexões não inicializado. A tentar conectar...")
            await self.connect()
            
        async with self._pool.acquire() as conn:
            if fetch == "one":
                return await conn.fetchrow(query, *params)
            elif fetch == "all":
                return await conn.fetch(query, *params)
            else:
                await conn.execute(query, *params)
                return None