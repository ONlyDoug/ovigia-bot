import aiohttp

API_SEARCH_URL = "https://gameinfo.albiononline.com/api/gameinfo/search?q="
API_PLAYER_INFO_URL = "https://gameinfo.albiononline.com/api/gameinfo/players/"

class AlbionAPI:
    def __init__(self):
        self._session = aiohttp.ClientSession()

    async def close(self):
        await self._session.close()

    async def search_player(self, player_name):
        try:
            async with self._session.get(f"{API_SEARCH_URL}{player_name}") as resp:
                if resp.status != 200:
                    print(f"API Search falhou: {resp.status}")
                    return None
                data = await resp.json()
                for player in data.get('players', []):
                    if player.get('Name').lower() == player_name.lower():
                        return player.get('Id')
                return None
        except Exception as e:
            print(f"Erro ao procurar jogador: {e}")
            return None

    async def get_player_info(self, player_id):
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