import discord
from discord.ext import commands
import logging
import asyncio
import config
from database import DatabaseManager
from albion_api import AlbionAPI
from cogs.recrutamento_cog import ApprovalView

# Configuração de Logging
logger = logging.getLogger("Bot")

class OVigiaBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        
        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
            case_insensitive=True
        )
        
        self.db = DatabaseManager()
        self.albion = AlbionAPI()

    async def setup_hook(self):
        """Hook de configuração assíncrono para conexão DB, início da API e carregamento de Cogs."""
        logger.info("Iniciando setup_hook...")
        
        # 1. Conectar ao Banco de Dados
        await self.db.connect()
        
        # 2. Iniciar Sessão da API do Albion
        await self.albion.start()
        
        # 3. Carregar Cogs
        cogs = [
            'cogs.admin_cog',
            'cogs.recrutamento_cog',
            'cogs.alianca_cog',
            'cogs.sync_cog',
            'cogs.suporte_cog'
        ]
        
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Extensão carregada: {cog}")
            except Exception as e:
                logger.error(f"Falha ao carregar extensão {cog}: {e}")

        # 4. Criar Tabelas (Garantir que AdminCog seja carregado primeiro ou acessar método diretamente)
        # Podemos acessar a instância do cog para rodar o método
        admin_cog = self.get_cog("AdminCog")
        if admin_cog:
            await admin_cog.create_tables()
        else:
            logger.error("AdminCog não encontrado. Tabelas não criadas.")

        # 5. Registrar Views Persistentes
        self.add_view(ApprovalView(self))
        logger.info("Views persistentes registradas.")
        
        # Nota: NÃO sincronizamos globalmente aqui para evitar limites de taxa.
        # Use o comando !sync no servidor.

    async def on_ready(self):
        logger.info(f"Logado como {self.user} (ID: {self.user.id})")
        logger.info("Bot está pronto!")

    async def close(self):
        """Limpeza ao fechar."""
        await self.db.close()
        await self.albion.close()
        await super().close()

async def main():
    if not config.DISCORD_TOKEN:
        logger.critical("DISCORD_TOKEN não encontrado na configuração. Saindo.")
        return

    bot = OVigiaBot()
    
    async with bot:
        await bot.start(config.DISCORD_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Lidar com Ctrl+C graciosamente
        pass