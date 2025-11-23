import aiohttp
import logging
import config

logger = logging.getLogger("AlbionAPI")

class AlbionAPI:
    def __init__(self):
        self.session = None

    async def start(self):
        self.session = aiohttp.ClientSession()

    async def close(self):
        if self.session:
            await self.session.close()

    async def search_player(self, player_name):
        """Busca por um jogador pelo nome."""
        if not self.session:
            await self.start()
        
        url = f"{config.ALBION_API_URL}/search?q={player_name}"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    # Filtrar por jogadores
                    players = data.get("players", [])
                    # Preferência por correspondência exata ou retornar o primeiro
                    for p in players:
                        if p['Name'].lower() == player_name.lower():
                            return p
                    return players[0] if players else None
                else:
                    logger.error(f"Erro na API do Albion (Busca): {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Exceção em search_player: {e}")
            return None

    async def get_player_info(self, player_id):
        """Obtém informações detalhadas de um jogador."""
        if not self.session:
            await self.start()

        url = f"{config.ALBION_API_URL}/players/{player_id}"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.error(f"Erro na API do Albion (Obter Info): {response.status}")
                    return None
        except Exception as e:
            logger.error(f"Exceção em get_player_info: {e}")
            return None