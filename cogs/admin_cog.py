import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncpg # Importa para apanhar o erro

# --- Função de Verificação de Admin ---
async def check_admin(interaction: discord.Interaction):
    config_data = await interaction.client.db_manager.execute_query(
        "SELECT admin_role_id FROM server_config WHERE server_id = $1",
        interaction.guild.id, fetch="one"
    )
    if not config_data or not config_data.get('admin_role_id'):
        await interaction.response.send_message("O cargo de admin ainda não foi configurado. Use `/admin setup_cargo_admin` primeiro.", ephemeral=True)
        return False
    
    admin_role_id = config_data['admin_role_id']
    if not any(role.id == admin_role_id for role in interaction.user.roles):
        await interaction.response.send_message("Não tem permissão para usar este comando.", ephemeral=True)
        return False
    return True

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- FUNÇÃO DE CRIAÇÃO DA DB (ATUALIZADA) ---
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
                    fame_pvp BIGINT DEFAULT 0,
                    recruta_role_id BIGINT  -- <- NOVO
                );
            """)
            
            # Adiciona a coluna se ela não existir (para quem já tem a DB)
            try:
                await self.bot.db_manager.execute_query("""
                    ALTER TABLE server_config
                    ADD COLUMN IF NOT EXISTS recruta_role_id BIGINT;
                """)
            except Exception as e:
                print(f"Nota: Falha ao tentar adicionar coluna 'recruta_role_id' (pode já existir): {e}")

            # Tabela de Membros
            await self.bot.db_manager.execute_query("""
                CREATE TABLE IF NOT EXISTS guild_members (
                    discord_id BIGINT PRIMARY KEY,
                    server_id BIGINT,
                    albion_nick TEXT NOT NULL,
                    verification_code TEXT,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTPTZ DEFAULT now()
                );
            """)
            
            await self.bot.db_manager.execute_query("DROP TABLE IF EXISTS pending_users;")

            try:
                await self.bot.db_manager.execute_query("""
                    ALTER TABLE guild_members
                    ADD CONSTRAINT fk_server_config
                    FOREIGN KEY(server_id) 
                    REFERENCES server_config(server_id)
                    ON DELETE CASCADE;
                """)
            except asyncpg.exceptions.DuplicateObjectError:
                pass 
            
            print("Base de dados (O Vigia Bot) verificada e pronta.")
            
        except Exception as e:
            print(f"❌ Erro CRÍTICO ao inicializar DB (Vigia): {e}")
            raise e

    # --- Grupo de Comandos ---
    admin = app_commands.Group(name="admin", description="Comandos de administração do O Vigia Bot.")

    # --- COMANDO 1: SETUP ADMIN ---
    @admin.command(name="setup_cargo_admin", description="Passo 1: Define o cargo que pode usar os comandos de admin.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(cargo="O cargo que terá permissões de admin do bot.")
    async def setup_admin_role(self, interaction: discord.Interaction, cargo: discord.Role):
        await self.bot.db_manager.execute_query(
            "INSERT INTO server_config (server_id, admin_role_id) VALUES ($1, $2) "
            "ON CONFLICT (server_id) DO UPDATE SET admin_role_id = $2",
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
    @app_commands.check(check_admin)
    async def criar_estrutura(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        config_data = await self.bot.db_manager.execute_query(
            "SELECT admin_role_id FROM server_config WHERE server_id = $1",
            guild.id, fetch="one"
        )
        admin_role = guild.get_role(config_data['admin_role_id'])
        if not admin_role:
            await interaction.followup.send("ERRO: Cargo de admin não encontrado. Use `/admin setup_cargo_admin` novamente.")
            return

        perms_public_everyone = discord.PermissionOverwrite(read_messages=True, send_messages=False, view_channel=True)
        perms_admin_private = discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)
        
        try:
            cat_publica = await guild.create_category("➡️ BEM-VINDO", overwrites={guild.default_role: perms_public_everyone})
            cat_privada = await guild.create_category(
                "🔒 ADMINISTRAÇÃO",
                overwrites={
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    admin_role: perms_admin_private,
                    guild.me: perms_admin_private
                }
            )
            canal_info = await guild.create_text_channel("📜-regras-e-info", category=cat_publica)
            canal_recrutamento = await guild.create_text_channel("✅-recrutamento", category=cat_publica)
            canal_comandos = await guild.create_text_channel("🔒-bot-comandos", category=cat_privada)
            canal_logs = await guild.create_text_channel("📢-bot-logs", category=cat_privada)
            
            await canal_recrutamento.set_permissions(
                guild.default_role, 
                send_messages=True, 
                read_messages=True, 
                view_channel=True,
                use_application_commands=True
            )
            
            await self.bot.db_manager.execute_query(
                "UPDATE server_config SET canal_registo_id = $1, canal_logs_id = $2 WHERE server_id = $3",
                canal_recrutamento.id, canal_logs.id, guild.id
            )
            
            await interaction.followup.send(
                "✅ **Estrutura de Canais Criada!**\n\n"
                f"**Categoria Pública:** {cat_publica.mention}\n"
                f"  ↳ {canal_info.mention}\n"
                f"  ↳ {canal_recrutamento.mention}\n\n"
                f"**Categoria Privada:** {cat_privada.mention}\n"
                f"  ↳ {canal_comandos.mention}\n"
                f"  ↳ {canal_logs.mention}\n\n"
                f"**Próximo Passo:** Use `/admin setup_requisitos` no canal {canal_comandos.mention}."
            )
        except discord.Forbidden:
            await interaction.followup.send("ERRO: Não tenho permissão para `Gerir Canais`.")
        except Exception as e:
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
            "UPDATE server_config SET fame_total = $1, fame_pvp = $2 WHERE server_id = $3",
            fama_total, fama_pvp, interaction.guild.id
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
            "UPDATE server_config SET guild_name = $1, role_id = $2 WHERE server_id = $3",
            nome_guilda, cargo_membro.id, interaction.guild.id
        )
        await interaction.response.send_message(
            f"✅ **Guilda Definida!**\n"
            f"Nome da Guilda: `{nome_guilda}`\n"
            f"Cargo de Membro: {cargo_membro.mention}\n\n"
            "**Próximo Passo:** Use `/admin setup_tag_recruta` (opcional).",
            ephemeral=True
        )

    # --- COMANDO 5: SETUP TAG RECRUTA (NOVO) ---
    @admin.command(name="setup_tag_recruta", description="Passo 5 (Opcional): Define a tag de 'Recruta' a ser removida.")
    @app_commands.check(check_admin)
    @app_commands.describe(cargo="A tag que os novos membros recebem (ex: @Não Verificado).")
    async def setup_tag_recruta(self, interaction: discord.Interaction, cargo: discord.Role):
        await self.bot.db_manager.execute_query(
            "UPDATE server_config SET recruta_role_id = $1 WHERE server_id = $2",
            cargo.id, interaction.guild.id
        )
        await interaction.response.send_message(
            f"✅ **Tag de Recruta Definida!**\n"
            f"O bot irá **remover** o cargo {cargo.mention} dos membros quando forem verificados.",
            ephemeral=True
        )

    # --- COMANDO 6: STATUS (ATUALIZADO) ---
    @admin.command(name="status", description="Mostra a configuração atual e o número de pendentes.")
    @app_commands.check(check_admin)
    async def status(self, interaction: discord.Interaction):
        config_data = await self.bot.db_manager.execute_query(
             "SELECT * FROM server_config WHERE server_id = $1",
             interaction.guild.id, fetch="one"
        )
        if not config_data:
            return await interaction.response.send_message("O bot ainda não foi configurado.", ephemeral=True)
        
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
        
        # ATUALIZADO
        embed.add_field(name="Cargos Discord", value=(
            f"Admin: {format_mention(config_data.get('admin_role_id'), 'role')}\n"
            f"Membro: {format_mention(config_data.get('role_id'), 'role')}\n"
            f"Recruta (a remover): {format_mention(config_data.get('recruta_role_id'), 'role')}"
        ), inline=True)
        
        embed.add_field(name="Canais Discord", value=(
            f"Registo: {format_mention(config_data.get('canal_registo_id'), 'channel')}\n"
            f"Logs: {format_mention(config_data.get('canal_logs_id'), 'channel')}"
        ), inline=True)
        
        pendentes_count_raw = await self.bot.db_manager.execute_query(
            "SELECT COUNT(*) as total FROM guild_members WHERE status = 'pending' AND server_id = $1",
            interaction.guild.id, fetch="one"
        )
        pendentes = pendentes_count_raw['total']
        embed.add_field(name="Membros Pendentes", value=f"**{pendentes}** utilizadores na fila.", inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# Obrigatório para carregar o Cog
async def setup(bot):
    await bot.add_cog(AdminCog(bot))