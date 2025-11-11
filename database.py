import asyncpg
import asyncio

class DatabaseManager:
    def __init__(self, user, password, host, port, db_name, min_conn=2, max_conn=10):
        self._user = user
        self._password = password
        self._host = host
        self._port = port
        self._db_name = db_name
        self._min_conn = min_conn
        self._max_conn = max_conn
        self._pool = None
        print("DatabaseManager inicializado (com componentes separados).")

    async def connect(self):
        """Inicializa o pool de conexões com asyncpg."""
        try:
            self._pool = await asyncpg.create_pool(
                user=self._user,
                password=self._password,
                host=self._host,
                port=self._port,
                database=self._db_name,
                min_size=self._min_conn,
                max_size=self._max_conn,
                # --- CORREÇÃO (Dica do Log) ---
                statement_cache_size=0 # Desativa o cache que causa o erro no pgbouncer
            )
            print("Pool de conexões (asyncpg) inicializado com sucesso.")
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