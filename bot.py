import discord
from discord.ext import commands
import config
import albion_api
import asyncio
import os
import database as db # Importar o módulo da base de dados

# --- Configuração dos Intents ---
intents = discord.Intents.default()
intents.members = True # Necessário para gerir membros
intents.message_content = True # Apenas por precaução

# --- O Bot ---
class RecrutamentoBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        # Criamos uma instância da API do Albion que será partilhada
        self.albion_client = albion_api.AlbionAPI()
        
    async def setup_hook(self):
        """Este 'hook' corre antes do bot ligar."""
        
        # 1. Inicializar a Base de Dados
        # Garante que as tabelas existem antes de carregar os Cogs
        try:
            await db.initialize_database()
        except Exception as e:
            print(f"Não foi possível iniciar a base de dados. O bot não pode continuar.")
            await self.close() # Desliga o bot se a DB falhar
            return

        # 2. Carregar os Cogs (extensões)
        cogs_folder = "cogs"
        for filename in os.listdir(cogs_folder):
            if filename.endswith(".py") and not filename.startswith("_"):
                await self.load_extension(f"{cogs_folder}.{filename[:-3]}")
                print(f"Carregado: {filename}")

        # 3. Sincronizar os Comandos de Barra (/) com o Discord
        await self.tree.sync()

    async def on_ready(self):
        print(f'Bot ligado como {self.user}')
        print(f'Pronto para sincronizar comandos...')

    async def on_close(self):
        """Quando o bot desliga, fecha a sessão da API."""
        await self.albion_client.close()
        print("Bot a desligar. Sessão da API fechada.")

# --- Ligar o Bot ---
if __name__ == "__main__":
    bot = RecrutamentoBot()
    if not config.TOKEN:
        print("TOKEN não encontrado. O bot não pode iniciar.")
    else:
        print("A ligar o bot...")
        bot.run(config.TOKEN)