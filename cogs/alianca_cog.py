import discord
from discord.ext import commands
from discord import app_commands
import logging
from utils.permissions import has_permission
from datetime import datetime

# --- Função de Log (Auxiliar) ---
async def log_to_channel(bot, guild_id, message, color=None):
    try:
        config_data = await bot.db_manager.execute_query("SELECT canal_logs_id FROM server_config WHERE server_id = $1", guild_id, fetch="one")
        if not config_data or not config_data.get('canal_logs_id'): return
        log_channel = bot.get_channel(config_data['canal_logs_id'])
        if log_channel:
            if color: await log_channel.send(embed=discord.Embed(description=message, color=color))
            else: await log_channel.send(message)
    except Exception as e: print(f"Erro ao enviar log para o canal: {e}")

class AliancaCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="aplicar_alianca", description="Verifica 100% automático se você está na aliança.")
    @app_commands.describe(nick="O seu nick exato no Albion Online.")
    async def aplicar_alianca(self, interaction: discord.Interaction, nick: str):
        config_data = await self.bot.db_manager.execute_query("SELECT * FROM server_config WHERE server_id = $1", interaction.guild.id, fetch="one")
        
        # Verifica se o bot está em "Modo Aliança"
        modo = config_data.get('mode', 'guild')
        if modo != 'alliance':
            return await interaction.response.send_message("Este servidor não está configurado para verificação de aliança.", ephemeral=True)

        if not all([config_data, config_data.get('canal_registo_id'), config_data.get('alliance_name'), config_data.get('alliance_role_id')]):
            return await interaction.response.send_message("O bot ainda não foi totalmente configurado por um admin.", ephemeral=True)
        if interaction.channel.id != config_data['canal_registo_id']:
            canal_correto = interaction.guild.get_channel(config_data['canal_registo_id'])
            return await interaction.response.send_message(f"Por favor, use este comando no canal {canal_correto.mention}.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        player_info = await self.bot.albion_client.get_player_info(
            await self.bot.albion_client.search_player(nick)
        )

        if not player_info:
            await log_to_channel(self.bot, interaction.guild.id, f"⚠️ Tentativa de registo de aliança falhou: Nick `{nick}` não encontrado (Utilizador: {interaction.user.mention}).")
            await interaction.followup.send(f"Não encontrei o jogador **{nick}**. Verifique o nome e tente novamente.")
            return
            
        existing_member = await self.bot.db_manager.execute_query("SELECT status FROM guild_members WHERE discord_id = $1", interaction.user.id, fetch="one")
        if existing_member and existing_member['status'] == 'verified':
            return await interaction.followup.send("Você já está verificado neste servidor.")

        # --- LÓGICA DE VERIFICAÇÃO AUTOMÁTICA DA ALIANÇA ---
        player_guild_name = player_info.get('GuildName', '')
        player_alliance_name = player_info.get('AllianceName', '')
        
        main_guild_name = config_data.get('main_guild_name', '').lower()
        alliance_name = config_data.get('alliance_name', '').lower()

        is_in_main_guild = player_guild_name.lower() == main_guild_name
        is_in_alliance = player_alliance_name.lower() == alliance_name

        # Define o TAG da guilda para o nick
        guild_tag = f"[{player_info.get('GuildTag', 'N/A')}] " if player_info.get('GuildTag') else ""
        novo_nick = f"{guild_tag}{nick}"
        
        if len(novo_nick) > 32:
            novo_nick = novo_nick[:32]

        try:
            cargos_para_adicionar = []
            cargos_para_remover = []
            log_cargos_add = []

            # 1. Definir o cargo a adicionar
            if main_guild_name and is_in_main_guild:
                # É da Guilda Principal (exceção)
                cargo_principal = interaction.guild.get_role(config_data.get('main_guild_role_id', 0))
                if cargo_principal:
                    cargos_para_adicionar.append(cargo_principal)
                    log_cargos_add.append(cargo_principal.mention)
            
            elif alliance_name and is_in_alliance:
                # É de uma Guilda Aliada
                cargo_aliado = interaction.guild.get_role(config_data.get('alliance_role_id', 0))
                if cargo_aliado:
                    cargos_para_adicionar.append(cargo_aliado)
                    log_cargos_add.append(cargo_aliado.mention)
                
                # Lógica de Tag Dinâmica
                cargo_guilda_dinamico = discord.utils.get(interaction.guild.roles, name=player_guild_name)
                if cargo_guilda_dinamico:
                    cargos_para_adicionar.append(cargo_guilda_dinamico)
                    log_cargos_add.append(cargo_guilda_dinamico.mention)
            
            else:
                # Não está em nenhuma
                await log_to_channel(self.bot, interaction.guild.id, f"❌ Verificação de Aliança Falhou: {interaction.user.mention} (`{nick}`) não está na aliança '{alliance_name}'.", discord.Color.red())
                return await interaction.followup.send(f"**Falha na Verificação!**\nO jogador `{nick}` **não** parece estar na aliança (`{alliance_name}`).\n\nSe acabou de entrar, aguarde 10-15 minutos e tente novamente (devido ao cache da API).")
            
            # 2. Cargo de Recruta (Remover)
            if config_data.get('recruta_role_id'):
                cargo_recruta = interaction.guild.get_role(config_data['recruta_role_id'])
                if cargo_recruta and cargo_recruta in interaction.user.roles:
                    cargos_para_remover.append(cargo_recruta)

            # 3. Executar Ações
            await interaction.user.edit(nick=novo_nick)
            if cargos_para_adicionar: await interaction.user.add_roles(*cargos_para_adicionar, reason="Verificação Automática de Aliança")
            if cargos_para_remover: await interaction.user.remove_roles(*cargos_para_remover, reason="Verificação Automática de Aliança")
            
            # 4. Atualizar DB
            await self.bot.db_manager.execute_query(
                "INSERT INTO guild_members (discord_id, server_id, albion_nick, status) VALUES ($1, $2, $3, 'verified') "
                "ON CONFLICT (discord_id) DO UPDATE SET "
                "server_id = EXCLUDED.server_id, albion_nick = EXCLUDED.albion_nick, "
                "status = 'verified'",
                interaction.user.id, interaction.guild.id, nick
            )
            await self.bot.db_manager.execute_query("INSERT INTO recruitment_log (server_id, discord_id, albion_nick, action) VALUES ($1, $2, $3, 'verified_auto')", interaction.guild.id, interaction.user.id, nick)
            
            # 5. Enviar Log
            log_cargos_rem = cargo_recruta.mention if cargo_recruta and cargos_para_remover else 'Nenhum'
            await log_to_channel(self.bot, interaction.guild.id,
                f"✅ **Verificado Automaticamente (Aliança)!**\n"
                f"**Membro:** {interaction.user.mention} (`{nick}`)\n"
                f"**Nick:** `{novo_nick}`\n"
                f"**Adicionado:** {', '.join(log_cargos_add) or 'Nenhum'}\n"
                f"**Removido:** {log_cargos_rem}",
                discord.Color.green()
            )
            
            await interaction.followup.send(f"🎉 **Bem-vindo(a) à Aliança!**\nO seu nick e cargos foram atualizados automaticamente.", ephemeral=True)

        except discord.Forbidden:
            await log_to_channel(self.bot, interaction.guild.id, f"❌ ERRO ADMIN: Tentei aprovar {interaction.user.mention}, mas não tenho permissão para alterar cargos ou nicks.", discord.Color.dark_red())
            await interaction.followup.send("Erro: Não tenho permissão para alterar os seus cargos ou nick. (Admin foi notificado).", ephemeral=True)
        except Exception as e:
            logging.error(f"Erro ao verificar {interaction.user.name}: {e}")
            await interaction.followup.send(f"Ocorreu um erro inesperado: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AliancaCog(bot))