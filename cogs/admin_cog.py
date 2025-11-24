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
        
        logger.info("Verificando tabelas do banco de dados...")
        for query in queries:
            try:
                await self.bot.db.execute_query(query)
            except Exception as e:
                logger.error(f"Erro ao criar tabela: {e}")

        try:
            await self.bot.db.execute_query(
                "ALTER TABLE server_config ADD COLUMN IF NOT EXISTS server_type TEXT DEFAULT 'GUILD';"
            )
        except Exception:
            pass

    @commands.command(name="sync")
    @commands.has_permissions(administrator=True)
    async def sync_commands(self, ctx):
        """
        Sincroniza os comandos de barra para o servidor atual.
        COPIA os comandos globais para o servidor para aparecerem instantaneamente.
        """
        msg = await ctx.send("⏳ Sincronizando comandos (Copiando Globais -> Guilda)...")
        try:
            # Passo CRÍTICO: Copiar comandos globais para este servidor específico
            # Isso faz com que eles apareçam instantaneamente, em vez de demorar 1 hora
            self.bot.tree.copy_global_to(guild=ctx.guild)
            
            # Sincronizar
            synced = await self.bot.tree.sync(guild=ctx.guild)
            
            await msg.edit(content=f"✅ **Sucesso!** {len(synced)} comandos sincronizados para este servidor.\n\nComandos disponíveis:\n" + "\n".join([f"`/{cmd.name}`" for cmd in synced]))
            logger.info(f"Comandos sincronizados para {ctx.guild.name}: {len(synced)}")
        except Exception as e:
            await msg.edit(content=f"❌ Falha ao sincronizar: {e}")
            logger.error(f"Erro de sync: {e}")

    @app_commands.command(name="admin_setup", description="Configurar o bot (Modo e Canais)")
    @app_commands.describe(
        mode="Modo de operação do bot",
        recruitment_channel="Canal de logs (Modo Guilda)",
        approval_channel="Canal de aprovação (Modo Guilda)",
        member_role="Cargo de Membro (Modo Guilda)",
        recruit_role="Cargo de Recruta (Modo Guilda)",
        ally_role="Cargo de Aliado (Modo Aliança)",
        guild_tag="Tag da Guilda",
        alliance_tag="Tag da Aliança"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Guilda (Recrutamento)", value="GUILD"),
        app_commands.Choice(name="Aliança (Gestão de Aliados)", value="ALLIANCE"),
        app_commands.Choice(name="Híbrido (Ambos)", value="HYBRID")
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
        
        await interaction.response.defer(ephemeral=True)
        
        rec_id = recruitment_channel.id if recruitment_channel else None
        app_id = approval_channel.id if approval_channel else None
        mem_id = member_role.id if member_role else None
        rec_role_id = recruit_role.id if recruit_role else None
        ally_id = ally_role.id if ally_role else None
        
        query = """
        INSERT INTO server_config (
            guild_id, recruitment_channel_id, approval_channel_id, 
            member_role_id, recruit_role_id, ally_role_id, 
            guild_tag, alliance_tag, server_type
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
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
        
        try:
            await self.bot.db.execute_query(query, 
                interaction.guild_id, rec_id, app_id, mem_id, rec_role_id, ally_id, 
                guild_tag, alliance_tag, mode.value
            )
            
            msg = f"✅ **Configuração Salva!**\nModo: `{mode.name}`"
            await interaction.followup.send(msg)
            
        except Exception as e:
            logger.error(f"Erro ao salvar config: {e}")
            await interaction.followup.send("❌ Erro ao salvar configuração no banco de dados.")

async def setup(bot):
    await bot.add_cog(AdminCog(bot))