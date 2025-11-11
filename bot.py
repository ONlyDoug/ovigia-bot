import discord
from discord.ext import commands
import config # O nosso novo config.py
import albion_api
import asyncio
import os
from database import DatabaseManager # A nossa nova classe de DB

# --- Configuração dos Intents ---
intents = discord.Intents.default()
intents.members = True 
intents.message_content = True 

class VigiaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
        # Inicializa os nossos clientes
        self.db_manager = DatabaseManager(dsn=config.DATABASE_URL)
        self.albion_client = albion_api.AlbionAPI()
        
    async def setup_hook(self):
        """Este 'hook' corre antes do bot ligar."""
        
        print("A executar setup_hook...")
        # 1. Ligar à Base de Dados
        await self.db_manager.connect()

        # 2. Carregar Admin Cog PRIMEIRO para criar as tabelas
        try:
            await self.load_extension('cogs.admin_cog')
            admin_cog = self.get_cog('AdminCog')
            if admin_cog:
                print("A inicializar o esquema da base de dados...")
                await admin_cog.initialize_database_schema()
            else:
                raise Exception("Não foi possível obter o AdminCog.")
        except Exception as e:
            print(f"ERRO CRÍTICO ao carregar/inicializar o AdminCog: {e}")
            return

        # 3. Carregar os outros Cogs
        cogs_to_load = ['cogs.recrutamento_cog', 'cogs.sync_cog']
        for cog_name in cogs_to_load:
            try:
                await self.load_extension(cog_name)
                print(f"Cog '{cog_name}' carregado com sucesso.")
            except Exception as e:
                print(f"ERRO ao carregar o cog '{cog_name}': {e}")

        # 4. Sincronizar Comandos de Barra
        await self.tree.sync()
        print("Setup_hook concluído.")

    async def on_ready(self):
        print(f'Bot ligado como {self.user}')

    async def on_close(self):
        """Quando o bot desliga, fecha as sessões."""
        await self.albion_client.close()
        await self.db_manager.close()
        print("Bot a desligar. Sessões fechadas.")

# --- Ligar o Bot ---
if __name__ == "__main__":
    bot = VigiaBot()
    bot.run(config.TOKEN)