import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncpg
import random
import string
from datetime import datetime, timedelta

# --- Funções Auxiliares ---
def gerar_codigo(tamanho=6):
    caracteres = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ''.join(random.choice(caracteres) for _ in range(tamanho))

async def log_to_channel(bot, guild_id, message, color=None):
    try:
        config_data = await bot.db_manager.execute_query(
            "SELECT canal_logs_id FROM server_config WHERE server_id = $1",
            guild_id, fetch="one"
        )
        if not config_data or not config_data.get('canal_logs_id'):
            return
        log_channel = bot.get_channel(config_data['canal_logs_id'])
        if log_channel:
            if color:
                embed = discord.Embed(description=message, color=color)
                await log_channel.send(embed=embed)
            else:
                await log_channel.send(message)
    except Exception as e:
        print(f"Erro ao enviar log para o canal: {e}")

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

    # --- FUNÇÃO DE CRIAÇÃO DA DB (CORRIGIDA) ---
    async def initialize_database_schema(self):
        try:
            # Tabela de Configuração
            await self.bot.db_manager.execute_query("""
                CREATE TABLE IF NOT EXISTS server_config (
                    server_id BIGINT PRIMARY KEY, guild_name TEXT, role_id BIGINT,
                    canal_registo_id BIGINT, canal_logs_id BIGINT, admin_role_id BIGINT,
                    fame_total BIGINT DEFAULT 0, fame_pvp BIGINT DEFAULT 0,
                    recruta_role_id BIGINT
                );
            """)
            try:
                await self.bot.db_manager.execute_query("ALTER TABLE server_config ADD COLUMN IF NOT EXISTS recruta_role_id BIGINT;")
            except Exception: pass

            # Tabela de Membros (CORREÇÃO AQUI)
            await self.bot.db_manager.execute_query("""
                CREATE TABLE IF NOT EXISTS guild_members (
                    discord_id BIGINT PRIMARY KEY, server_id BIGINT, albion_nick TEXT NOT NULL,
                    verification_code TEXT, status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMPTZ DEFAULT now() 
                );
            """)
            
            # Tabela de Logs (CORREÇÃO AQUI)
            await self.bot.db_manager.execute_query("""
                CREATE TABLE IF NOT EXISTS recruitment_log (
                    id SERIAL PRIMARY KEY,
                    server_id BIGINT,
                    discord_id BIGINT,
                    albion_nick TEXT,
                    action TEXT NOT NULL,
                    admin_id BIGINT,
                    timestamp TIMESTAMPTZ DEFAULT now()
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

    @admin.command(name="setup_cargo_admin", description="Passo 1: Define o cargo que pode usar os comandos de admin.")
    @app_commands.checks.has_permissions(administrator=True)
    async def setup_admin_role(self, interaction: discord.Interaction, cargo: discord.Role):
        await self.bot.db_manager.execute_query("INSERT INTO server_config (server_id, admin_role_id) VALUES ($1, $2) ON CONFLICT (server_id) DO UPDATE SET admin_role_id = $2", interaction.guild.id, cargo.id)
        await interaction.response.send_message(f"✅ **Cargo de Admin Definido!**\n**Próximo Passo:** Use `/admin criar_estrutura`.", ephemeral=True)

    @admin.command(name="criar_estrutura", description="Passo 2: Cria as categorias e canais de recrutamento.")
    @app_commands.check(check_admin)
    async def criar_estrutura(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        config_data = await self.bot.db_manager.execute_query("SELECT admin_role_id FROM server_config WHERE server_id = $1", guild.id, fetch="one")
        admin_role = guild.get_role(config_data['admin_role_id'])
        perms_public_everyone = discord.PermissionOverwrite(read_messages=True, send_messages=False, view_channel=True)
        perms_admin_private = discord.PermissionOverwrite(read_messages=True, send_messages=True, view_channel=True)
        cat_publica = await guild.create_category("➡️ BEM-VINDO", overwrites={guild.default_role: perms_public_everyone})
        cat_privada = await guild.create_category("🔒 ADMINISTRAÇÃO", overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False), admin_role: perms_admin_private, guild.me: perms_admin_private})
        canal_info = await guild.create_text_channel("📜-regras-e-info", category=cat_publica)
        canal_recrutamento = await guild.create_text_channel("✅-recrutamento", category=cat_publica)
        canal_comandos = await guild.create_text_channel("🔒-bot-comandos", category=cat_privada)
        canal_logs = await guild.create_text_channel("📢-bot-logs", category=cat_privada)
        await canal_recrutamento.set_permissions(guild.default_role, send_messages=True, read_messages=True, view_channel=True, use_application_commands=True)
        await self.bot.db_manager.execute_query("UPDATE server_config SET canal_registo_id = $1, canal_logs_id = $2 WHERE server_id = $3", canal_recrutamento.id, canal_logs.id, guild.id)
        await interaction.followup.send(f"✅ **Estrutura de Canais Criada!**\n**Próximo Passo:** Use `/admin setup_requisitos` no canal {canal_comandos.mention}.", ephemeral=True)

    @admin.command(name="setup_requisitos", description="Passo 3: Define os requisitos mínimos de Fama da guilda.")
    @app_commands.check(check_admin)
    async def setup_requisitos(self, interaction: discord.Interaction, fama_total: int, fama_pvp: int):
        await self.bot.db_manager.execute_query("UPDATE server_config SET fame_total = $1, fame_pvp = $2 WHERE server_id = $3", fama_total, fama_pvp, interaction.guild.id)
        await interaction.response.send_message(f"✅ **Requisitos Definidos!**\n**Próximo Passo:** Use `/admin setup_guilda`.", ephemeral=True)

    @admin.command(name="setup_guilda", description="Passo 4: Define os dados da guilda do Albion.")
    @app_commands.check(check_admin)
    async def setup_guilda(self, interaction: discord.Interaction, nome_guilda: str, cargo_membro: discord.Role):
        await self.bot.db_manager.execute_query("UPDATE server_config SET guild_name = $1, role_id = $2 WHERE server_id = $3", nome_guilda, cargo_membro.id, interaction.guild.id)
        await interaction.response.send_message(f"✅ **Guilda Definida!**\n**Próximo Passo:** Use `/admin setup_tag_recruta` (opcional).", ephemeral=True)

    @admin.command(name="setup_tag_recruta", description="Passo 5 (Opcional): Define a tag de 'Recruta' a ser removida.")
    @app_commands.check(check_admin)
    async def setup_tag_recruta(self, interaction: discord.Interaction, cargo: discord.Role):
        await self.bot.db_manager.execute_query("UPDATE server_config SET recruta_role_id = $1 WHERE server_id = $2", cargo.id, interaction.guild.id)
        await interaction.response.send_message(f"✅ **Tag de Recruta Definida!**\nO bot irá **remover** o cargo {cargo.mention} na verificação.", ephemeral=True)

    @admin.command(name="aprovar_manual", description="Passo 6 (Especial): Aprova um membro que falhou no filtro de fama.")
    @app_commands.check(check_admin)
    async def aprovar_manual(self, interaction: discord.Interaction, membro: discord.Member, nick_albion: str):
        await interaction.response.defer(ephemeral=True)
        player_id = await self.bot.albion_client.search_player(nick_albion)
        if not player_id: await interaction.followup.send(f"❌ Falha: Não encontrei o jogador `{nick_albion}`."); return
        codigo = gerar_codigo()
        await self.bot.db_manager.execute_query("INSERT INTO guild_members (discord_id, server_id, albion_nick, verification_code, status) VALUES ($1, $2, $3, $4, 'pending') ON CONFLICT (discord_id) DO UPDATE SET server_id = EXCLUDED.server_id, albion_nick = EXCLUDED.albion_nick, verification_code = EXCLUDED.verification_code, status = 'pending'", membro.id, interaction.guild.id, nick_albion, codigo)
        log_msg = (f"⚠️ **Aprovação Manual**\nAdmin: {interaction.user.mention}\nUtilizador: {membro.mention} (`{nick_albion}`)\nCódigo Gerado: `{codigo}`")
        await log_to_channel(self.bot, interaction.guild.id, log_msg, discord.Color.gold())
        await self.bot.db_manager.execute_query("INSERT INTO recruitment_log (server_id, discord_id, albion_nick, action, admin_id) VALUES ($1, $2, $3, 'approved_manual', $4)", interaction.guild.id, membro.id, nick_albion, interaction.user.id)
        try:
            config_data = await self.bot.db_manager.execute_query("SELECT guild_name FROM server_config WHERE server_id = $1", interaction.guild.id, fetch="one")
            guild_name = config_data.get('guild_name', 'a sua guilda')
            embed = discord.Embed(title="✅ Aprovação Manual", description=f"Olá, {membro.mention}! Um admin aprovou o seu registo para **{nick_albion}**.", color=discord.Color.green())
            embed.add_field(name="Passo 1: No Albion", value=(f"1. Aplique para: **{guild_name}** (se ainda não o fez)\n2. Cole na sua 'Bio' o código: **`{codigo}`**"), inline=False)
            embed.add_field(name="Passo 2: Aguardar", value="É tudo! O bot irá verificar automaticamente.", inline=False)
            await membro.send(embed=embed)
            await interaction.followup.send(f"✅ Membro `{membro.display_name}` (`{nick_albion}`) foi adicionado à fila. DM enviada com o código `{codigo}`.")
        except discord.Forbidden:
            await interaction.followup.send(f"✅ Membro `{membro.display_name}` adicionado à fila. **Falha ao enviar DM**. Por favor, envie o código `{codigo}` manualmente.")

    @admin.command(name="status", description="Mostra a configuração atual e o número de pendentes.")
    @app_commands.check(check_admin)
    async def status(self, interaction: discord.Interaction):
        config_data = await self.bot.db_manager.execute_query("SELECT * FROM server_config WHERE server_id = $1", interaction.guild.id, fetch="one")
        if not config_data: return await interaction.response.send_message("O bot ainda não foi configurado.", ephemeral=True)
        def format_mention(id_val, type):
            if not id_val: return 'N/D'
            obj = None
            if type == 'role': obj = interaction.guild.get_role(id_val)
            if type == 'channel': obj = interaction.guild.get_channel(id_val)
            return obj.mention if obj else 'N/D (ID inválido?)'
        embed = discord.Embed(title="Status da Configuração - O Vigia Bot", color=discord.Color.blue())
        embed.add_field(name="Guilda Albion", value=f"`{config_data.get('guild_name', 'N/D')}`", inline=False)
        embed.add_field(name="Requisitos", value=(f"Fama Total: `{config_data.get('fame_total', 0):,}`\nFama PvP: `{config_data.get('fame_pvp', 0):,}`"), inline=False)
        embed.add_field(name="Cargos Discord", value=(f"Admin: {format_mention(config_data.get('admin_role_id'), 'role')}\nMembro: {format_mention(config_data.get('role_id'), 'role')}\nRecruta (a remover): {format_mention(config_data.get('recruta_role_id'), 'role')}"), inline=True)
        embed.add_field(name="Canais Discord", value=(f"Registo: {format_mention(config_data.get('canal_registo_id'), 'channel')}\nLogs: {format_mention(config_data.get('canal_logs_id'), 'channel')}"), inline=True)
        pendentes_count_raw = await self.bot.db_manager.execute_query("SELECT COUNT(*) as total FROM guild_members WHERE status = 'pending' AND server_id = $1", interaction.guild.id, fetch="one")
        embed.add_field(name="Membros Pendentes", value=f"**{pendentes_count_raw['total']}** utilizadores na fila.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @admin.command(name="fix_permissions", description="Força a correção de permissões no canal de recrutamento.")
    @app_commands.check(check_admin)
    async def fix_permissions(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config_data = await self.bot.db_manager.execute_query("SELECT canal_registo_id FROM server_config WHERE server_id = $1", interaction.guild.id, fetch="one")
        if not config_data or not config_data.get('canal_registo_id'):
            return await interaction.followup.send("❌ O canal de registo ainda não foi configurado.")
        canal_recrutamento = interaction.guild.get_channel(config_data['canal_registo_id'])
        if not canal_recrutamento:
            return await interaction.followup.send(f"❌ Não encontrei o canal de registo.")
        try:
            await canal_recrutamento.set_permissions(interaction.guild.default_role, send_messages=True, read_messages=True, view_channel=True, use_application_commands=True)
            await interaction.followup.send(f"✅ Permissões do canal {canal_recrutamento.mention} foram corrigidas!")
        except discord.Forbidden:
            await interaction.followup.send("❌ Não tenho permissão para `Gerir Permissões` nesse canal.")

    @admin.command(name="relatorio", description="Gera um relatório de recrutamento dos últimos dias.")
    @app_commands.check(check_admin)
    @app_commands.describe(dias="O número de dias para incluir no relatório (padrão: 7).")
    async def relatorio(self, interaction: discord.Interaction, dias: int = 7):
        await interaction.response.defer(ephemeral=True)
        data_limite = datetime.utcnow() - timedelta(days=dias)
        query = "SELECT action, COUNT(*) as total FROM recruitment_log WHERE server_id = $1 AND timestamp >= $2 GROUP BY action;"
        log_data = await self.bot.db_manager.execute_query(query, interaction.guild.id, data_limite, fetch="all")
        if not log_data:
            return await interaction.followup.send(f"Nenhuma atividade de recrutamento encontrada nos últimos {dias} dias.")
        stats = {'filtered': 0, 'registered': 0, 'verified_auto': 0, 'approved_manual': 0, 'kicked_auto': 0}
        for row in log_data:
            if row['action'] in stats: stats[row['action']] = row['total']
        total_entradas = stats['verified_auto'] + stats['approved_manual']
        embed = discord.Embed(title=f"📊 Relatório de Recrutamento (Últimos {dias} Dias)", color=discord.Color.blue(), timestamp=datetime.utcnow())
        embed.add_field(name="🏁 Entradas", value=f"**{total_entradas}** Membros Verificados\n`{stats['verified_auto']}` (Automáticos)\n`{stats['approved_manual']}` (Manuais)", inline=True)
        embed.add_field(name="⛔ Filtro", value=f"**{stats['filtered']}** Recrutas Rejeitados\n`{stats['registered']}` (Registos bem-sucedidos)\n", inline=True)
        embed.add_field(name="🚪 Saídas", value=f"**{stats['kicked_auto']}** Membros Expulsos (Sync)", inline=True)
        admin_query = "SELECT admin_id, COUNT(*) as total FROM recruitment_log WHERE server_id = $1 AND timestamp >= $2 AND action = 'approved_manual' GROUP BY admin_id ORDER BY total DESC LIMIT 5;"
        admin_data = await self.bot.db_manager.execute_query(admin_query, interaction.guild.id, data_limite, fetch="all")
        admin_texto = "Nenhuma aprovação manual."
        if admin_data:
            admin_texto = "\n".join([f"`{row['total']}` aprovações - <@{row['admin_id']}>" for row in admin_data])
        embed.add_field(name="🏆 Staff Ativo (Aprovações Manuais)", value=admin_texto, inline=False)
        await interaction.followup.send(embed=embed)

# Obrigatório para carregar o Cog
async def setup(bot):
    await bot.add_cog(AdminCog(bot))