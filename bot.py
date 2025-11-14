import discord
from discord.ext import commands
import config # O nosso config.py atualizado
import albion_api
import asyncio
import os
from database import DatabaseManager

# --- Configuração dos Intents ---
intents = discord.Intents.default()
intents.members = True 
intents.message_content = True 

class VigiaBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
        self.db_manager = DatabaseManager(
            user=config.DB_USER,
            password=config.DB_PASSWORD,
            host=config.DB_HOST,
            port=config.DB_PORT,
            db_name=config.DB_NAME
        )
        self.albion_client = albion_api.AlbionAPI()
        
    async def setup_hook(self):
        """Este 'hook' corre antes do bot ligar."""
        
        print("A executar setup_hook...")
        
        await self.db_manager.connect()
        await self.albion_client.connect()

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
            # Não retornamos, para que possamos ver os erros dos outros cogs se houver
            
        # 4. Carregar os outros Cogs (LISTA CORRIGIDA)
        cogs_to_load = ['cogs.recrutamento_cog', 'cogs.sync_cog', 'cogs.suporte_cog', 'cogs.alianca_cog']
        
        for cog_name in cogs_to_load:
            try:
                await self.load_extension(cog_name)
                print(f"Cog '{cog_name}' carregado com sucesso.")
            except Exception as e:
                print(f"ERRO ao carregar o cog '{cog_name}': {e}")

        # 5. Sincronizar Comandos de Barra (Desativado para !sync)
        # await self.tree.sync()
        print("Setup_hook concluído. (Use !sync por servidor para sincronizar comandos)")

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