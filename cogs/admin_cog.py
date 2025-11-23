import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger("AdminCog")

class AdminCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def create_tables(self):
        """Cria as tabelas necessárias no banco de dados."""
        queries = [
            """
            CREATE TABLE IF NOT EXISTS server_config (
                guild_id BIGINT PRIMARY KEY,
                recruitment_channel_id BIGINT,
                approval_channel_id BIGINT,
                member_role_id BIGINT,
                recruit_role_id BIGINT,
                ally_role_id BIGINT,
                alliance_tag TEXT,
                guild_tag TEXT,
                min_fame_pve BIGINT DEFAULT 0,
                min_fame_pvp BIGINT DEFAULT 0,
                server_type TEXT DEFAULT 'GUILD',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS guild_members (
                user_id BIGINT PRIMARY KEY,
                guild_id BIGINT,
                albion_nick TEXT,
                joined_at TIMESTAMPTZ DEFAULT NOW()
            );
            """,
            """
            CREATE TABLE IF NOT EXISTS recruitment_log (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                guild_id BIGINT,
                albion_nick TEXT,
                status TEXT,
                reviewed_by BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        ]
        
        logger.info("Criando tabelas...")
        for query in queries:
            await self.bot.db.execute_query(query)
        
        # Migração simples para adicionar coluna se não existir (para deploys existentes)
        try:
            await self.bot.db.execute_query("ALTER TABLE server_config ADD COLUMN IF NOT EXISTS server_type TEXT DEFAULT 'GUILD';")
        except Exception as e:
            logger.warning(f"Erro ao tentar migrar tabela (pode já estar atualizada): {e}")

        logger.info("Tabelas criadas/verificadas.")

    @commands.command(name="sync")
    @commands.has_permissions(administrator=True)
    async def sync_tree(self, ctx):
        """Sincroniza manualmente os comandos de barra para o servidor atual."""
        logger.info(f"Sincronizando comandos para o servidor: {ctx.guild.name} ({ctx.guild.id})")
        try:
            synced = await self.bot.tree.sync(guild=ctx.guild)
            await ctx.send(f"Sincronizado {len(synced)} comandos para este servidor.")
            logger.info(f"Sucesso ao sincronizar {len(synced)} comandos.")
        except Exception as e:
            logger.error(f"Falha ao sincronizar comandos: {e}")
            await ctx.send(f"Falha ao sincronizar comandos: {e}")

    @app_commands.command(name="admin_setup", description="Configurar definições do bot e Modo de Operação")
    @app_commands.describe(
        mode="Modo de operação do bot neste servidor",
        recruitment_channel="Canal para logs de recrutamento (Modo Guilda)",
        approval_channel="Canal para mensagens de aprovação (Modo Guilda)",
        member_role="Cargo para membros efetivos (Modo Guilda)",
        recruit_role="Cargo para recrutas (Modo Guilda)",
        ally_role="Cargo para aliados (Modo Aliança)",
        guild_tag="Tag da guilda principal (Modo Guilda)",
        alliance_tag="Tag da aliança (Modo Aliança)"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Modo Guilda (Recrutamento)", value="GUILD"),
        app_commands.Choice(name="Modo Aliança (Gestão de Aliados)", value="ALLIANCE"),
        app_commands.Choice(name="Modo Híbrido (Ambos)", value="HYBRID")
    ])
    @app_commands.default_permissions(administrator=True)
    async def admin_setup(self, interaction: discord.Interaction, 
                          mode: app_commands.Choice[str],
                          recruitment_channel: discord.TextChannel = None,
                          approval_channel: discord.TextChannel = None,
                          member_role: discord.Role = None,
                          recruit_role: discord.Role = None,
                          ally_role: discord.Role = None,
                          guild_tag: str = None,
                          alliance_tag: str = None):
        
        # Extrair IDs se os objetos forem fornecidos, senão None
        recruitment_channel_id = recruitment_channel.id if recruitment_channel else None
        approval_channel_id = approval_channel.id if approval_channel else None
        member_role_id = member_role.id if member_role else None
        recruit_role_id = recruit_role.id if recruit_role else None
        ally_role_id = ally_role.id if ally_role else None
        
        server_type = mode.value

        query = """
        INSERT INTO server_config (guild_id, recruitment_channel_id, approval_channel_id, member_role_id, recruit_role_id, ally_role_id, guild_tag, alliance_tag, server_type)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (guild_id) DO UPDATE SET
        recruitment_channel_id = COALESCE($2, server_config.recruitment_channel_id),
        approval_channel_id = COALESCE($3, server_config.approval_channel_id),
        member_role_id = COALESCE($4, server_config.member_role_id),
        recruit_role_id = COALESCE($5, server_config.recruit_role_id),
        ally_role_id = COALESCE($6, server_config.ally_role_id),
        guild_tag = COALESCE($7, server_config.guild_tag),
        alliance_tag = COALESCE($8, server_config.alliance_tag),
        server_type = $9;
        """
        
        await self.bot.db.execute_query(query, interaction.guild_id, recruitment_channel_id, approval_channel_id, member_role_id, recruit_role_id, ally_role_id, guild_tag, alliance_tag, server_type)
        
        msg = f"Configuração atualizada! **Modo: {mode.name}**."
        if not any([recruitment_channel, approval_channel, member_role, recruit_role, ally_role, guild_tag, alliance_tag]):
            msg += "\n(Apenas o modo foi alterado, nenhum outro parâmetro foi fornecido)"
            
        await interaction.response.send_message(msg, ephemeral=True)

async def setup(bot):
    await bot.add_cog(AdminCog(bot))