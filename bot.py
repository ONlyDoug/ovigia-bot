import discord
from discord.ext import commands
import logging
import asyncio
from config import Config
from database import DatabaseManager
from albion_api import AlbionAPI

# Configurar logger principal
logger = logging.getLogger("Bot")

class OVigiaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        
        self.db = DatabaseManager()
        self.albion = AlbionAPI()

    async def setup_hook(self):
        """Inicialização de recursos assíncronos."""
        logger.info("--- Iniciando Setup do Bot ---")
        
        # 1. Conectar ao Banco de Dados
        await self.db.connect()
        
        # 2. Iniciar API
        await self.albion.start()
        
        # 3. Carregar Cogs
        cogs = [
            'cogs.admin_cog',
            'cogs.recrutamento_cog',
            'cogs.alianca_cog'
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Cog carregado: {cog}")
            except Exception as e:
                logger.error(f"Falha ao carregar cog {cog}: {e}")
                
        # 4. Criar tabelas se necessário (via AdminCog)
        admin_cog = self.get_cog('AdminCog')
        if admin_cog:
            await admin_cog.create_tables()
            
        logger.info("--- Setup Concluído ---")

    async def on_ready(self):
        logger.info(f"Bot Online: {self.user} (ID: {self.user.id})")
        logger.info("Aguardando comandos...")

    async def close(self):
        """Limpeza ao desligar."""
        logger.info("Desligando bot...")
        await self.db.close()
        await self.albion.close()
        await super().close()

async def main():
    if not Config.validate():
        logger.critical("Configuração inválida. Encerrando.")
        return

    bot = OVigiaBot()
    
    try:
        await bot.start(Config.DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Interrompido pelo usuário.")
    except Exception as e:
        logger.critical(f"Erro fatal no bot: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())