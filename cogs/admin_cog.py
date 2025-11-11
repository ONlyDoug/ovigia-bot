import discord
from discord.ext import commands
from discord import app_commands
import logging

# --- Função de Verificação de Admin (usa db_manager no client) ---
async def check_admin(interaction: discord.Interaction):
    """Verifica se o utilizador tem o cargo de admin definido na config do bot."""
    try:
        config_data = await interaction.client.db_manager.execute_query(
            "SELECT admin_role_id FROM server_config WHERE server_id = $1",
            interaction.guild.id, fetch="one"
        )
    except Exception as e:
        logging.exception("Erro ao ler config para check_admin")
        await interaction.response.send_message("Erro interno ao verificar permissões.", ephemeral=True)
        return False

    if not config_data or not config_data.get('admin_role_id'):
        await interaction.response.send_message("O cargo de admin ainda não foi configurado.", ephemeral=True)
        return False

    admin_role_id = config_data['admin_role_id']
    if not any(role.id == admin_role_id for role in interaction.user.roles):
        await interaction.response.send_message("Não tem permissão para usar este comando.", ephemeral=True)
        return False
    return True

# --- O Cog de Admin ---
class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- FUNÇÃO DE CRIAÇÃO DA DB (Estilo Arauto Bank) ---
    async def initialize_database_schema(self):
        try:
            # Tabela de Configuração
            await self.bot.db_manager.execute_query("""
                CREATE TABLE IF NOT EXISTS server_config (
                    server_id BIGINT PRIMARY KEY,
                    guild_name TEXT,
                    role_id BIGINT,
                    canal_registo_id BIGINT,
                    canal_logs_id BIGINT,
                    admin_role_id BIGINT,
                    fame_total BIGINT DEFAULT 0,
                    fame_pvp BIGINT DEFAULT 0
                );
            """)
            
            # Tabela de Membros
            await self.bot.db_manager.execute_query("""
                CREATE TABLE IF NOT EXISTS guild_members (
                    discord_id BIGINT PRIMARY KEY,
                    server_id BIGINT,
                    albion_nick TEXT NOT NULL,
                    verification_code TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMPTZ DEFAULT now(),
                    CONSTRAINT fk_server_config FOREIGN KEY(server_id) REFERENCES server_config(server_id) ON DELETE CASCADE
                );
            """)
            
            # Remove tabela antiga se existir
            await self.bot.db_manager.execute_query("DROP TABLE IF EXISTS pending_users;")
            logging.info("Base de dados (O Vigia Bot) verificada e pronta.")
        except Exception:
            logging.exception("❌ Erro CRÍTICO ao inicializar DB (Vigia)")
            raise

    # --- Grupo de comandos /admin ---
    admin = app_commands.Group(name="admin", description="Comandos de administração do O Vigia Bot.")

    # --- COMANDO 1: SETUP ADMIN ---
    @admin.command(name="setup_cargo_admin", description="Passo 1: Define o cargo que pode usar os comandos de admin.")
    @app_commands.checks.has_permissions(administrator=True) # Só Admins do Discord podem usar
    @app_commands.describe(cargo="O cargo que terá permissões de admin do bot.")
    async def setup_admin_role(self, interaction: discord.Interaction, cargo: discord.Role):
        await self.bot.db_manager.execute_query(
            "INSERT INTO server_config (server_id, admin_role_id) VALUES ($1, $2) "
            "ON CONFLICT (server_id) DO UPDATE SET admin_role_id = EXCLUDED.admin_role_id",
            interaction.guild.id, cargo.id
        )
        await interaction.response.send_message(
            f"✅ **Cargo de Admin Definido!**\n"
            f"Apenas membros com o cargo {cargo.mention} poderão usar os comandos `/admin`.\n"
            f"**Próximo Passo:** Use `/admin criar_estrutura`.",
            ephemeral=True
        )

    # --- COMANDO 2: CRIAR ESTRUTURA ---
    @admin.command(name="criar_estrutura", description="Passo 2: Cria as categorias e canais de recrutamento.")
    @app_commands.check(check_admin) # Só o admin do bot pode usar
    async def criar_estrutura(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        config_data = await self.bot.db_manager.execute_query(
            "SELECT * FROM server_config WHERE server_id = $1", guild.id, fetch="one"
        )
        admin_role = None
        if config_data and config_data.get('admin_role_id'):
            admin_role = guild.get_role(config_data['admin_role_id'])

        if not admin_role: # Verificação extra
            await interaction.followup.send("ERRO: Cargo de admin não encontrado. Tente `/admin setup_cargo_admin` novamente.")
            return

        perms_public_everyone = discord.PermissionOverwrite(read_messages=True, send_messages=False, view_channel=True)
        perms_admin_private = discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)
        
        try:
            # 1. Criar Categoria Pública
            cat_publica = await guild.create_category(
                "➡️ BEM-VINDO",
                overwrites={guild.default_role: perms_public_everyone}
            )
            
            # 2. Criar Categoria Privada
            cat_privada = await guild.create_category(
                "🔒 ADMINISTRAÇÃO",
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    admin_role: perms_admin_private,
                    guild.me: perms_admin_private
                }
            )

            # 3. Criar Canais
            canal_info = await guild.create_text_channel("📜-regras-e-info", category=cat_publica)
            canal_recrutamento = await guild.create_text_channel("✅-recrutamento", category=cat_publica)
            canal_comandos = await guild.create_text_channel("🔒-bot-comandos", category=cat_privada)
            canal_logs = await guild.create_text_channel("📢-bot-logs", category=cat_privada)
            
            # 4. Ajustar permissão do canal de recrutamento
            await canal_recrutamento.set_permissions(guild.default_role, send_messages=True, read_messages=True, view_channel=True)
            
            # 5. Salvar na Base de Dados (upsert)
            await self.bot.db_manager.execute_query(
                "INSERT INTO server_config (server_id, canal_registo_id, canal_logs_id) VALUES ($1, $2, $3) "
                "ON CONFLICT (server_id) DO UPDATE SET canal_registo_id = EXCLUDED.canal_registo_id, canal_logs_id = EXCLUDED.canal_logs_id",
                guild.id, canal_recrutamento.id, canal_logs.id
            )
            
            await interaction.followup.send(
                "✅ **Estrutura de Canais Criada!**\n\n"
                f"**Categoria Pública:** {cat_publica.mention}\n"
                f"  ↳ {canal_info.mention} (Escreva as regras e requisitos aqui)\n"
                f"  ↳ {canal_recrutamento.mention} (Onde os recrutas usarão `/registrar`)\n\n"
                f"**Categoria Privada:** {cat_privada.mention}\n"
                f"  ↳ {canal_comandos.mention} (Onde deve usar os próximos comandos)\n"
                f"  ↳ {canal_logs.mention} (Logs automáticos do bot)\n\n"
                f"**Próximo Passo:** Use `/admin setup_requisitos` no canal {canal_comandos.mention}."
            )

        except discord.Forbidden:
            await interaction.followup.send("ERRO: Não tenho permissão para `Gerir Canais`. Por favor, verifique as permissões do bot.")
        except Exception as e:
            logging.exception("Erro ao criar estrutura")
            await interaction.followup.send(f"Ocorreu um erro: {e}")

    # --- COMANDO 3: SETUP REQUISITOS ---
    @admin.command(name="setup_requisitos", description="Passo 3: Define os requisitos mínimos de Fama da guilda.")
    @app_commands.check(check_admin)
    @app_commands.describe(
        fama_total="O mínimo de Fama Total (ex: 10000000 para 10M).",
        fama_pvp="O mínimo de Fama de Abate PvP (ex: 500000 para 500k)."
    )
    async def setup_requisitos(self, interaction: discord.Interaction, fama_total: int, fama_pvp: int):
        await self.bot.db_manager.execute_query(
            "INSERT INTO server_config (server_id, fame_total, fame_pvp) VALUES ($1, $2, $3) "
            "ON CONFLICT (server_id) DO UPDATE SET fame_total = EXCLUDED.fame_total, fame_pvp = EXCLUDED.fame_pvp",
            interaction.guild.id, fama_total, fama_pvp
        )
        await interaction.response.send_message(
            f"✅ **Requisitos Definidos!**\n"
            f"Fama Total Mínima: `{fama_total:,}`\n"
            f"Fama PvP Mínima: `{fama_pvp:,}`\n"
            f"**Próximo Passo:** Use `/admin setup_guilda`.",
            ephemeral=True
        )

    # --- COMANDO 4: SETUP GUILDA ---
    @admin.command(name="setup_guilda", description="Passo 4: Define os dados da guilda do Albion.")
    @app_commands.check(check_admin)
    @app_commands.describe(
        nome_guilda="O nome exato da sua guilda no Albion Online.",
        cargo_membro="O cargo que os membros verificados receberão."
    )
    async def setup_guilda(self, interaction: discord.Interaction, nome_guilda: str, cargo_membro: discord.Role):
        await self.bot.db_manager.execute_query(
            "INSERT INTO server_config (server_id, guild_name, role_id) VALUES ($1, $2, $3) "
            "ON CONFLICT (server_id) DO UPDATE SET guild_name = EXCLUDED.guild_name, role_id = EXCLUDED.role_id",
            interaction.guild.id, nome_guilda, cargo_membro.id
        )
        await interaction.response.send_message(
            f"✅ **Guilda Definida!**\n"
            f"Nome da Guilda: `{nome_guilda}`\n"
            f"Cargo de Membro: {cargo_membro.mention}\n\n"
            "🎉 **Configuração Concluída!** O bot está pronto para recrutar.",
            ephemeral=True
        )

    # --- COMANDO 5: STATUS ---
    @admin.command(name="status", description="Mostra a configuração atual e o número de pendentes.")
    @app_commands.check(check_admin)
    async def status(self, interaction: discord.Interaction):
        config_data = await self.bot.db_manager.execute_query(
            "SELECT * FROM server_config WHERE server_id = $1", interaction.guild.id, fetch="one"
        )
        if not config_data:
            return await interaction.response.send_message("O bot ainda não foi configurado.", ephemeral=True)
        
        # Função auxiliar para formatar
        def format_mention(id_val, type):
            if not id_val: return 'N/D'
            obj = None
            if type == 'role': obj = interaction.guild.get_role(id_val)
            if type == 'channel': obj = interaction.guild.get_channel(id_val)
            return obj.mention if obj else 'N/D (ID inválido?)'

        embed = discord.Embed(title="Status da Configuração - O Vigia Bot", color=discord.Color.blue())
        embed.add_field(name="Guilda Albion", value=f"`{config_data.get('guild_name', 'N/D')}`", inline=False)
        embed.add_field(name="Requisitos", value=(
            f"Fama Total: `{config_data.get('fame_total', 0):,}`\n"
            f"Fama PvP: `{config_data.get('fame_pvp', 0):,}`"
        ), inline=False)
        embed.add_field(name="Cargos Discord", value=(
            f"Admin: {format_mention(config_data.get('admin_role_id'), 'role')}\n"
            f"Membro: {format_mention(config_data.get('role_id'), 'role')}"
        ), inline=True)
        embed.add_field(name="Canais Discord", value=(
            f"Registo: {format_mention(config_data.get('canal_registo_id'), 'channel')}\n"
            f"Logs: {format_mention(config_data.get('canal_logs_id'), 'channel')}"
        ), inline=True)
        
        pendentes_row = await self.bot.db_manager.execute_query(
            "SELECT COUNT(*) AS cnt FROM guild_members WHERE server_id = $1 AND status = 'pending'",
            interaction.guild.id, fetch="one"
        )
        pendentes = pendentes_row.get('cnt', 0) if pendentes_row else 0
        embed.add_field(name="Membros Pendentes", value=f"**{pendentes}** utilizadores na fila de verificação.", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Obrigatório para carregar o Cog e inicializar esquema DB
async def setup(bot):
    cog = AdminCog(bot)
    await bot.add_cog(cog)
    # Inicializa esquema DB (assumindo que bot.db_manager já foi atribuído)
    try:
        await cog.initialize_database_schema()
    except Exception:
        logging.exception("Falha ao inicializar esquema DB no setup do AdminCog")