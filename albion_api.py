import aiohttp

# Endpoints da API
API_SEARCH_URL = "https://gameinfo.albiononline.com/api/gameinfo/search?q="
API_PLAYER_INFO_URL = "https://gameinfo.albiononline.com/api/gameinfo/players/"

class AlbionAPI:
    def __init__(self):
        # A sessão é criada uma vez e reutilizada
        self._session = aiohttp.ClientSession()

    async def close(self):
        """Fecha a sessão aiohttp. Deve ser chamado no 'on_close' do bot."""
        await self._session.close()

    async def search_player(self, player_name):
        """
        Procura um jogador pelo nome e retorna o ID se encontrar uma correspondência exata.
        """
        try:
            async with self._session.get(f"{API_SEARCH_URL}{player_name}") as resp:
                if resp.status != 200:
                    print(f"API Search falhou: {resp.status}")
                    return None
                data = await resp.json()
                for player in data.get('players', []):
                    # Correspondência exata (ignorando maiúsculas/minúsculas)
                    if player.get('Name').lower() == player_name.lower():
                        return player.get('Id')
                return None # Não encontrou correspondência exata
        except Exception as e:
            print(f"Erro ao procurar jogador: {e}")
            return None

    async def get_player_info(self, player_id):
        """
        Busca a informação completa de um jogador (incluindo bio e guilda) pelo ID.
        """
        if not player_id:
            return None
            
        try:
            async with self._session.get(f"{API_PLAYER_INFO_URL}{player_id}") as resp:
                if resp.status != 200:
                    print(f"API Info falhou: {resp.status}")
                    return None
                return await resp.json()
        except Exception as e:
            print(f"Erro ao obter info do jogador: {e}")
            return None