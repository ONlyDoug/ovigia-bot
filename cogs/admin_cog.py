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

    @app_commands.command(name="auto_setup", description="🚀 Configuração Automática (Cria canais e cargos)")
    @app_commands.describe(
        mode="Modo de operação do bot",
        guild_tag="Tag da sua Guilda (Ex: VEX)",
        alliance_tag="Tag da Aliança (Ex: ALLY)"
    )
    @app_commands.choices(mode=[
        app_commands.Choice(name="Guilda (Recrutamento)", value="GUILD"),
        app_commands.Choice(name="Aliança (Gestão de Aliados)", value="ALLIANCE"),
        app_commands.Choice(name="Híbrido (Ambos)", value="HYBRID")
    ])
    @app_commands.default_permissions(administrator=True)
    async def auto_setup(self, interaction: discord.Interaction, mode: app_commands.Choice[str], guild_tag: str = None, alliance_tag: str = None):
        await interaction.response.defer()
        guild = interaction.guild
        
        # 1. Criar Categoria
        category = discord.utils.get(guild.categories, name="🛡️ Sistema O Vigia")
        if not category:
            category = await guild.create_category("🛡️ Sistema O Vigia")
            
        # 2. Criar Canais
        rec_channel = discord.utils.get(guild.text_channels, name="📝-registros", category=category)
        if not rec_channel:
            rec_channel = await guild.create_text_channel("📝-registros", category=category)
            
        app_channel = discord.utils.get(guild.text_channels, name="✅-aprovação", category=category)
        if not app_channel:
            app_channel = await guild.create_text_channel("✅-aprovação", category=category)
            
        # 3. Criar Cargos
        member_role = discord.utils.get(guild.roles, name="Membro")
        if not member_role:
            member_role = await guild.create_role(name="Membro", color=discord.Color.blue(), hoist=True)
            
        recruit_role = discord.utils.get(guild.roles, name="Recruta")
        if not recruit_role:
            recruit_role = await guild.create_role(name="Recruta", color=discord.Color.orange(), hoist=True)
            
        ally_role = discord.utils.get(guild.roles, name="Aliado")
        if not ally_role:
            ally_role = await guild.create_role(name="Aliado", color=discord.Color.green(), hoist=True)
            
        # 4. Salvar no Banco
        query = """
        INSERT INTO server_config (
            guild_id, recruitment_channel_id, approval_channel_id, 
            member_role_id, recruit_role_id, ally_role_id, 
            guild_tag, alliance_tag, server_type
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (guild_id) DO UPDATE SET
            recruitment_channel_id = $2,
            approval_channel_id = $3,
            member_role_id = $4,
            recruit_role_id = $5,
            ally_role_id = $6,
            guild_tag = COALESCE($7, server_config.guild_tag),
            alliance_tag = COALESCE($8, server_config.alliance_tag),
            server_type = $9;
        """
        
        await self.bot.db.execute_query(query, 
            guild.id, rec_channel.id, app_channel.id, 
            member_role.id, recruit_role.id, ally_role.id, 
            guild_tag, alliance_tag, mode.value
        )
        
        msg = f"""
✅ **Configuração Automática Concluída!**

**Modo:** {mode.name}
**Canais Criados:** {rec_channel.mention}, {app_channel.mention}
**Cargos Criados:** {member_role.mention}, {recruit_role.mention}, {ally_role.mention}

**Tags Configuradas:**
Guilda: `{guild_tag or 'Não definida'}`
Aliança: `{alliance_tag or 'Não definida'}`

O bot está pronto para uso!
"""
        await interaction.followup.send(msg)

    @app_commands.command(name="admin_setup", description="Configuração Manual (Avançado)")
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
            
            msg = f"✅ **Configuração Manual Salva!**\nModo: `{mode.name}`"
            await interaction.followup.send(msg)
            
        except Exception as e:
            logger.error(f"Erro ao salvar config: {e}")
            await interaction.followup.send("❌ Erro ao salvar configuração no banco de dados.")

async def setup(bot):
    await bot.add_cog(AdminCog(bot))