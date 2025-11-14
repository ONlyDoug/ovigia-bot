import discord
from discord.ext import commands
from discord import app_commands
import logging
import asyncpg
import random
import string
from datetime import datetime, timedelta
from utils.permissions import has_permission, check_admin_prefix # Importa as novas permissões

# --- Funções Auxiliares (Não mudam) ---
def gerar_codigo(tamanho=6):
    caracteres = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ''.join(random.choice(caracteres) for _ in range(tamanho))

async def log_to_channel(bot, guild_id, message, color=None):
    try:
        config_data = await bot.db_manager.execute_query("SELECT canal_logs_id FROM server_config WHERE server_id = $1", guild_id, fetch="one")
        if not config_data or not config_data.get('canal_logs_id'): return
        log_channel = bot.get_channel(config_data['canal_logs_id'])
        if log_channel:
            if color: await log_channel.send(embed=discord.Embed(description=message, color=color))
            else: await log_channel.send(message)
    except Exception as e: print(f"Erro ao enviar log para o canal: {e}")

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
                    fame_total BIGINT DEFAULT 0, 
                    fame_pvp BIGINT DEFAULT 0,
                    recruta_role_id BIGINT,
                    mode TEXT DEFAULT 'guild', -- 'guild' ou 'alliance' (NOVO)
                    alliance_name TEXT -- (NOVO)
                );
            """)
            try: await self.bot.db_manager.execute_query("ALTER TABLE server_config ADD COLUMN IF NOT EXISTS recruta_role_id BIGINT;")
            except Exception: pass
            try: await self.bot.db_manager.execute_query("ALTER TABLE server_config ADD COLUMN IF NOT EXISTS mode TEXT DEFAULT 'guild';")
            except Exception: pass
            try: await self.bot.db_manager.execute_query("ALTER TABLE server_config ADD COLUMN IF NOT EXISTS alliance_name TEXT;")
            except Exception: pass
            
            # Tabela de Permissões
            await self.bot.db_manager.execute_query("""
                CREATE TABLE IF NOT EXISTS server_config_permissoes (
                    server_id BIGINT, chave TEXT, valor TEXT,
                    PRIMARY KEY (server_id, chave)
                );
            """)

            # Tabela de Membros (Removido 'verification_code')
            await self.bot.db_manager.execute_query("""
                CREATE TABLE IF NOT EXISTS guild_members (
                    discord_id BIGINT PRIMARY KEY, server_id BIGINT, albion_nick TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMPTZ DEFAULT now() 
                );
            """)
            try: await self.bot.db_manager.execute_query("ALTER TABLE guild_members DROP COLUMN IF EXISTS verification_code;")
            except Exception: pass
            
            # Tabela de Logs
            await self.bot.db_manager.execute_query("""
                CREATE TABLE IF NOT EXISTS recruitment_log (
                    id SERIAL PRIMARY KEY, server_id BIGINT, discord_id BIGINT,
                    albion_nick TEXT, action TEXT NOT NULL, admin_id BIGINT,
                    timestamp TIMESTAMPTZ DEFAULT now()
                );
            """)
            
            await self.bot.db_manager.execute_query("DROP TABLE IF EXISTS pending_users;")
            try:
                await self.bot.db_manager.execute_query("""
                    ALTER TABLE guild_members
                    ADD CONSTRAINT fk_server_config
                    FOREIGN KEY(server_id) REFERENCES server_config(server_id) ON DELETE CASCADE;
                """)
            except asyncpg.exceptions.DuplicateObjectError: pass 
            
            try: await self.bot.db_manager.execute_query("ALTER TABLE server_config DROP COLUMN IF EXISTS admin_role_id;")
            except Exception: pass

            print("Base de dados (O Vigia Bot) v2.1 (Modo Aliança) verificada e pronta.")
        except Exception as e:
            print(f"❌ Erro CRÍTICO ao inicializar DB (Vigia): {e}")
            raise e

    # --- Grupo de Comandos ---
    admin = app_commands.Group(name="admin", description="Comandos de administração do O Vigia Bot.")
    
    # --- Comandos de Setup ---
    
    @admin.command(name="setup_permissoes", description="Passo 1: Define os cargos de staff (Suporte, Admin, etc).")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(nivel="Nível de permissão (1=Suporte, 4=Admin Total)", cargos="Os cargos que terão este nível.")
    async def setup_permissoes(self, interaction: discord.Interaction, nivel: int, cargos: str):
        if not 1 <= nivel <= 4:
            return await interaction.response.send_message("O nível deve estar entre 1 e 4.", ephemeral=True)
        role_ids = [role.id for role in interaction.data['resolved']['roles'].values()]
        if not role_ids:
            return await interaction.response.send_message("Nenhum cargo válido mencionado.", ephemeral=True)
        ids_str = ",".join(str(rid) for rid in role_ids)
        await self.bot.db_manager.execute_query(
            "INSERT INTO server_config_permissoes (server_id, chave, valor) VALUES ($1, $2, $3) "
            "ON CONFLICT (server_id, chave) DO UPDATE SET valor = $3",
            interaction.guild.id, f"perm_nivel_{nivel}", ids_str
        )
        await interaction.response.send_message(f"✅ **Permissões de Nível {nivel} definidas!**\n**Próximo Passo:** Use `/admin set_mode`.", ephemeral=True)

    @admin.command(name="set_mode", description="Passo 2: Define o modo de operação do bot neste servidor.")
    @has_permission(4)
    @app_commands.describe(modo="O modo de operação: recrutar para Guilda ou verificar uma Aliança inteira.")
    @app_commands.choices(modo=[
        app_commands.Choice(name="Modo Guilda (Filtro de Fama + 1 Cargo)", value="guild"),
        app_commands.Choice(name="Modo Aliança (Sem Filtro + Tags de Guilda)", value="alliance"),
    ])
    async def set_mode(self, interaction: discord.Interaction, modo: str):
        await self.bot.db_manager.execute_query(
            "INSERT INTO server_config (server_id, mode) VALUES ($1, $2) "
            "ON CONFLICT (server_id) DO UPDATE SET mode = $2",
            interaction.guild.id, modo
        )
        if modo == 'guild':
            await interaction.response.send_message(f"✅ **Modo do Bot: Guilda**\nO bot irá filtrar por Fama e atribuir um único cargo de membro.\n**Próximo Passo:** `/admin criar_estrutura`.", ephemeral=True)
        else: # Alliance
            await interaction.response.send_message(f"✅ **Modo do Bot: Aliança**\nO bot irá ignorar Fama e atribuir cargos dinâmicos baseados na guilda do jogador.\n**Próximo Passo:** `/admin criar_estrutura`.", ephemeral=True)

    @admin.command(name="criar_estrutura", description="Passo 3: Cria os canais de recrutamento.")
    @has_permission(4)
    async def criar_estrutura(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        
        # Overwrites padrão para canais de admin
        admin_overwrites = { guild.default_role: discord.PermissionOverwrite(view_channel=False), guild.me: discord.PermissionOverwrite(view_channel=True) }
        try:
            staff_roles = set()
            for i in range(1, 5): # Puxa todos os cargos Nível 1+
                config_perm = await self.bot.db_manager.execute_query("SELECT valor FROM server_config_permissoes WHERE server_id = $1 AND chave = $2", guild.id, f"perm_nivel_{i}", fetch="one")
                if config_perm and config_perm['valor']:
                    staff_roles.update(config_perm['valor'].split(','))
            for role_id in staff_roles:
                if role := guild.get_role(int(role_id)):
                    admin_overwrites[role] = discord.PermissionOverwrite(view_channel=True)
        except Exception as e: print(f"Não foi possível pré-definir permissões de staff: {e}")

        # Criação dos canais
        cat_publica = await guild.create_category("➡️ BEM-VINDO", overwrites={guild.default_role: discord.PermissionOverwrite(read_messages=True, send_messages=False, view_channel=True)})
        cat_privada = await guild.create_category("🔒 ADMINISTRAÇÃO", overwrites=admin_overwrites)
        await guild.create_text_channel("📜-regras-e-info", category=cat_publica)
        canal_recrutamento = await guild.create_text_channel("✅-recrutamento", category=cat_publica)
        canal_comandos = await guild.create_text_channel("🔒-bot-comandos", category=cat_privada)
        canal_logs = await guild.create_text_channel("📢-bot-logs", category=cat_privada)
        
        # --- NOVO CANAL DE APROVAÇÕES ---
        canal_aprovacoes = await guild.create_text_channel("⏳-aprovações", category=cat_privada)

        await canal_recrutamento.set_permissions(guild.default_role, send_messages=True, read_messages=True, view_channel=True, use_application_commands=True)
        
        # Salva os canais importantes
        await self.bot.db_manager.execute_query(
            "UPDATE server_config SET canal_registo_id = $1, canal_logs_id = $2, canal_aprovacao_id = $3 WHERE server_id = $4",
            canal_recrutamento.id, canal_logs.id, canal_aprovacoes.id, guild.id
        )
        await interaction.followup.send(f"✅ **Estrutura de Canais Criada!**\nNovo canal `#⏳-aprovações` adicionado para a equipa de Suporte.\n**Próximo Passo:** Use os comandos de setup restantes em {canal_comandos.mention}.", ephemeral=True)

    @admin.command(name="setup_requisitos", description="Passo 4 (Modo Guilda): Define os requisitos mínimos de Fama.")
    @has_permission(4)
    async def setup_requisitos(self, interaction: discord.Interaction, fama_total: int, fama_pvp: int):
        await self.bot.db_manager.execute_query("UPDATE server_config SET fame_total = $1, fame_pvp = $2 WHERE server_id = $3", fama_total, fama_pvp, interaction.guild.id)
        await interaction.response.send_message(f"✅ **Requisitos Definidos!**\nFama Total: `{fama_total:,}` | Fama PvP: `{fama_pvp:,}`\n**Próximo Passo:** Use `/admin setup_guilda` ou `/admin setup_alianca`.", ephemeral=True)

    @admin.command(name="setup_guilda", description="Passo 5 (Modo Guilda): Define a Guilda e o cargo de Membro.")
    @has_permission(4)
    async def setup_guilda(self, interaction: discord.Interaction, nome_guilda: str, cargo_membro: discord.Role):
        await self.bot.db_manager.execute_query("UPDATE server_config SET guild_name = $1, role_id = $2, mode = 'guild' WHERE server_id = $3", nome_guilda, cargo_membro.id, interaction.guild.id)
        await interaction.response.send_message(f"✅ **Guilda Definida!**\nO bot está em **Modo Guilda**, a recrutar para `{nome_guilda}` e a dar o cargo {cargo_membro.mention}.\n**Próximo Passo:** `/admin setup_tag_recruta` (opcional).", ephemeral=True)

    @admin.command(name="setup_alianca", description="Passo 5 (Modo Aliança): Define o nome da Aliança.")
    @has_permission(4)
    async def setup_alianca(self, interaction: discord.Interaction, nome_alianca: str):
        await self.bot.db_manager.execute_query("UPDATE server_config SET alliance_name = $1, mode = 'alliance' WHERE server_id = $2", nome_alianca, interaction.guild.id)
        await interaction.response.send_message(f"✅ **Aliança Definida!**\nO bot está em **Modo Aliança**, a verificar membros da `{nome_alianca}` e a dar cargos dinâmicos (ex: @GuildaA, @GuildaB).\n**Próximo Passo:** `/admin setup_tag_recruta` (opcional).", ephemeral=True)

    @admin.command(name="setup_tag_recruta", description="Passo 6 (Opcional): Define a tag de 'Recruta' a ser removida.")
    @has_permission(4)
    async def setup_tag_recruta(self, interaction: discord.Interaction, cargo: discord.Role):
        await self.bot.db_manager.execute_query("UPDATE server_config SET recruta_role_id = $1 WHERE server_id = $2", cargo.id, interaction.guild.id)
        await interaction.response.send_message(f"✅ **Tag de Recruta Definida!**\nO bot irá **remover** o cargo {cargo.mention} na verificação.", ephemeral=True)

    @admin.command(name="status", description="Mostra a configuração atual e o número de pendentes.")
    @has_permission(1) # Nível 1 (Suporte) pode ver
    async def status(self, interaction: discord.Interaction):
        config_data = await self.bot.db_manager.execute_query("SELECT * FROM server_config WHERE server_id = $1", interaction.guild.id, fetch="one")
        if not config_data: return await interaction.response.send_message("O bot ainda não foi configurado.", ephemeral=True)
        def format_mention(id_val, type):
            if not id_val: return 'N/D'
            obj = None
            if type == 'role': obj = interaction.guild.get_role(id_val)
            if type == 'channel': obj = interaction.guild.get_channel(id_val)
            return obj.mention if obj else f"ID Inválido ({id_val})"
        
        embed = discord.Embed(title="Status da Configuração - O Vigia Bot", color=discord.Color.blue())
        modo = config_data.get('mode', 'guild')
        embed.add_field(name="Modo de Operação", value=f"**{modo.upper()}**", inline=False)
        
        if modo == 'guild':
            embed.add_field(name="Guilda Alvo", value=f"`{config_data.get('guild_name', 'N/D')}`", inline=True)
            embed.add_field(name="Cargo de Membro", value=f"{format_mention(config_data.get('role_id'), 'role')}", inline=True)
            embed.add_field(name="Requisitos", value=(f"Fama Total: `{config_data.get('fame_total', 0):,}`\nFama PvP: `{config_data.get('fame_pvp', 0):,}`"), inline=False)
        else:
            embed.add_field(name="Aliança Alvo", value=f"`{config_data.get('alliance_name', 'N/D')}`", inline=True)
            embed.add_field(name="Cargo de Membro", value="`Dinâmico (pelo nome da guilda)`", inline=True)
        
        perm_texto = ""
        for i in range(1, 5):
            perm_data = await self.bot.db_manager.execute_query("SELECT valor FROM server_config_permissoes WHERE server_id = $1 AND chave = $2", interaction.guild.id, f"perm_nivel_{i}", fetch="one")
            if perm_data and perm_data['valor']:
                nomes_cargos = [f"<@&{rid}>" for rid in perm_data['valor'].split(',')]
                perm_texto += f"**Nível {i}:** {', '.join(nomes_cargos)}\n"
        if not perm_texto: perm_texto = "Nenhum cargo de staff definido."
        embed.add_field(name="Cargos de Staff", value=perm_texto, inline=False)
        
        embed.add_field(name="Cargos Gerais", value=(f"Recruta (a remover): {format_mention(config_data.get('recruta_role_id'), 'role')}"), inline=False)
        embed.add_field(name="Canais Discord", value=(f"Registo: {format_mention(config_data.get('canal_registo_id'), 'channel')}\nLogs: {format_mention(config_data.get('canal_logs_id'), 'channel')}\nAprovações: {format_mention(config_data.get('canal_aprovacao_id'), 'channel')}"), inline=True)
        
        pendentes_count_raw = await self.bot.db_manager.execute_query("SELECT COUNT(*) as total FROM guild_members WHERE status = 'pending' AND server_id = $1", interaction.guild.id, fetch="one")
        embed.add_field(name="Membros Pendentes", value=f"**{pendentes_count_raw['total']}** utilizadores na fila.", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @admin.command(name="fix_permissions", description="Força a correção de permissões nos canais de recrutamento e admin.")
    @has_permission(4)
    async def fix_permissions(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        config_data = await self.bot.db_manager.execute_query("SELECT canal_registo_id, canal_aprovacao_id FROM server_config WHERE server_id = $1", interaction.guild.id, fetch="one")
        if not config_data: return await interaction.followup.send("❌ O bot ainda não foi configurado.")
        
        # 1. Canal de Recrutamento
        canal_recrutamento = interaction.guild.get_channel(config_data.get('canal_registo_id', 0))
        if canal_recrutamento:
            try:
                await canal_recrutamento.set_permissions(interaction.guild.default_role, send_messages=True, read_messages=True, view_channel=True, use_application_commands=True)
            except discord.Forbidden:
                await interaction.followup.send("❌ Falha ao corrigir {canal_recrutamento.mention}: Sem permissão de 'Gerir Permissões'.")
                return
        
        # 2. Canal de Aprovações (Dar permissão à Staff)
        canal_aprovacoes = interaction.guild.get_channel(config_data.get('canal_aprovacao_id', 0))
        if canal_aprovacoes:
            try:
                # Pega em todos os cargos de Nível 1+
                staff_roles = set()
                for i in range(1, 5):
                    config_perm = await self.bot.db_manager.execute_query("SELECT valor FROM server_config_permissoes WHERE server_id = $1 AND chave = $2", interaction.guild.id, f"perm_nivel_{i}", fetch="one")
                    if config_perm and config_perm['valor']:
                        staff_roles.update(config_perm['valor'].split(','))
                
                # Atualiza as permissões
                overwrites = canal_aprovacoes.overwrites
                overwrites[interaction.guild.default_role] = discord.PermissionOverwrite(view_channel=False) # Esconde de @everyone
                overwrites[interaction.guild.me] = discord.PermissionOverwrite(view_channel=True) # Bot pode ver
                for role_id in staff_roles:
                    if role := interaction.guild.get_role(int(role_id)):
                        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_messages=True)
                
                await canal_aprovacoes.edit(overwrites=overwrites)
            except discord.Forbidden:
                await interaction.followup.send(f"❌ Falha ao corrigir {canal_aprovacoes.mention}: Sem permissão de 'Gerir Permissões'.")
                return

        await interaction.followup.send("✅ Permissões dos canais de recrutamento e aprovações foram atualizadas para a staff.")


    @admin.command(name="relatorio", description="Gera um relatório de recrutamento dos últimos dias.")
    @has_permission(2)
    async def relatorio(self, interaction: discord.Interaction, dias: int = 7):
        await interaction.response.defer(ephemeral=True)
        data_limite = datetime.utcnow() - timedelta(days=dias)
        query = "SELECT action, COUNT(*) as total FROM recruitment_log WHERE server_id = $1 AND timestamp >= $2 GROUP BY action;"
        log_data = await self.bot.db_manager.execute_query(query, interaction.guild.id, data_limite, fetch="all")
        if not log_data: return await interaction.followup.send(f"Nenhuma atividade de recrutamento encontrada nos últimos {dias} dias.")
        stats = {'filtered_low_fame': 0, 'registered': 0, 'verified_auto': 0, 'approved_manual': 0, 'kicked_auto': 0, 'force_verified': 0, 'rejected_manual': 0}
        for row in log_data:
            if row['action'] in stats: stats[row['action']] = row['total']
        total_entradas = stats['verified_auto'] + stats['approved_manual'] + stats['force_verified']
        embed = discord.Embed(title=f"📊 Relatório de Recrutamento (Últimos {dias} Dias)", color=discord.Color.blue(), timestamp=datetime.utcnow())
        embed.add_field(name="🏁 Entradas", value=f"**{total_entradas}** Membros Verificados\n`{stats['verified_auto']}` (Automáticos)\n`{stats['approved_manual']}` (Aprov. Suporte)\n`{stats['force_verified']}` (Forçados)", inline=True)
        embed.add_field(name="⛔ Ações de Filtro", value=f"**{stats['filtered_low_fame']}** (Avisos de Fama Baixa)\n**{stats['rejected_manual']}** (Rejeitados Suporte)\n`{stats['registered']}` (Registos Totais)", inline=True)
        embed.add_field(name="🚪 Saídas", value=f"**{stats['kicked_auto']}** Membros Expulsos (Sync)", inline=True)
        admin_query = "SELECT admin_id, COUNT(*) as total FROM recruitment_log WHERE server_id = $1 AND timestamp >= $2 AND action IN ('approved_manual', 'force_verified', 'rejected_manual') GROUP BY admin_id ORDER BY total DESC LIMIT 5;"
        admin_data = await self.bot.db_manager.execute_query(admin_query, interaction.guild.id, data_limite, fetch="all")
        admin_texto = "Nenhuma ação manual."
        if admin_data:
            admin_texto = "\n".join([f"`{row['total']}` ações - <@{row['admin_id']}>" for row in admin_data])
        embed.add_field(name="🏆 Staff Ativo (Ações Manuais)", value=admin_texto, inline=False)
        await interaction.followup.send(embed=embed)

    # --- COMANDO SYNC (SECRETO) ---
    @commands.command(name="sync", hidden=True)
    @check_admin_prefix()
    async def sync_commands(self, ctx: commands.Context):
        """Força a sincronização de comandos de barra para este servidor."""
        msg = await ctx.send("🔄 A sincronizar comandos de barra para este servidor...")
        await self.bot.tree.sync(guild=ctx.guild)
        await msg.edit(content="✅ Comandos de barra sincronizados! Pode demorar alguns minutos a aparecer.")

async def setup(bot):
    await bot.add_cog(AdminCog(bot))