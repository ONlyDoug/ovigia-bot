import aiohttp
import logging
from config import Config

logger = logging.getLogger("AlbionAPI")

class AlbionAPI:
    """Cliente para a API do Albion Online."""
    
    def __init__(self):
        self.session = None

    async def start(self):
        """Inicia a sessão HTTP."""
        if not self.session:
            self.session = aiohttp.ClientSession()

    async def close(self):
        """Fecha a sessão HTTP."""
        if self.session:
            await self.session.close()
            self.session = None

    async def search_player(self, player_name):
        """Busca um jogador pelo nome exato ou parcial."""
        if not self.session:
            await self.start()
        
        url = f"{Config.ALBION_API_URL}/search?q={player_name}"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    players = data.get("players", [])
                    
                    # Tentar match exato primeiro (case-insensitive)
                    for p in players:
                        if p['Name'].lower() == player_name.lower():
                            return p
                    
                    # Se não achar exato, retorna o primeiro da lista
                    return players[0] if players else None
                else:
                    logger.warning(f"API retornou status {response.status} na busca por {player_name}")
                    return None
        except Exception as e:
            logger.error(f"Erro de conexão na busca de jogador: {e}")
            return None

    async def get_player_info(self, player_id):
        """Obtém detalhes completos de um jogador pelo ID."""
        if not self.session:
            await self.start()

        url = f"{Config.ALBION_API_URL}/players/{player_id}"
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    logger.warning(f"API retornou status {response.status} ao buscar ID {player_id}")
                    return None
        except Exception as e:
            logger.error(f"Erro de conexão ao obter detalhes do jogador: {e}")
            return None