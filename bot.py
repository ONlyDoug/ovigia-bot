import discord
from discord.ext import commands
import logging
import asyncio
from config import Config
from database import DatabaseManager
from albion_api import AlbionAPI
from cogs.recrutamento_cog import ApprovalView

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
        
        self.db = None
        self.albion = None
        
    async def setup_hook(self):
        """Inicialização assíncrona do bot"""
        logger.info("Iniciando setup_hook...")
        
        # Inicializar Database
        try:
            self.db = DatabaseManager(
                host=Config.DB_HOST,
                port=Config.DB_PORT,
                database=Config.DB_NAME,
                user=Config.DB_USER,
                password=Config.DB_PASSWORD
            )
            await self.db.connect()
        except Exception as e:
            logger.error(f"Erro ao conectar ao banco de dados: {e}")
            raise
        
        # Inicializar Albion API
        self.albion = AlbionAPI()
        
        # Carregar Cogs
        cogs_to_load = [
            'cogs.admin_cog',
            'cogs.recrutamento_cog',
            'cogs.alianca_cog'
        ]
        
        for cog in cogs_to_load:
            try:
                await self.load_extension(cog)
                logger.info(f"Extensão carregada: {cog}")
            except Exception as e:
                logger.error(f"Falha ao carregar extensão {cog}: {e}")
        
        # Criar tabelas (via AdminCog se disponível)
        admin_cog = self.get_cog('AdminCog')
        if admin_cog:
            try:
                await admin_cog.create_tables()
            except Exception as e:
                logger.error(f"Erro ao criar tabelas: {e}")
        else:
            logger.warning("AdminCog não encontrado. Tabelas não criadas.")
        
        # Registrar Views Persistentes
        self.add_view(ApprovalView(self))
        logger.info("Views persistentes registradas.")
    
    async def on_ready(self):
        """Evento chamado quando o bot está pronto"""
        logger.info(f"Logado como {self.user} (ID: {self.user.id})")
        logger.info("Bot está pronto!")
    
    async def close(self):
        """Cleanup ao fechar o bot"""
        if self.db:
            await self.db.close()
        await super().close()

async def main():
    """Função principal para iniciar o bot"""
    bot = OVigiaBot()
    
    try:
        await bot.start(Config.DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Bot interrompido pelo usuário")
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
    finally:
        await bot.close()

if __name__ == "__main__":
    asyncio.run(main())