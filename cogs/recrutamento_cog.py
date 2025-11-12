import discord
from discord.ext import commands, tasks
from discord import app_commands
import database as db
import random
import string
import logging

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

# --- Função de Gerar Código (Auxiliar) ---
def gerar_codigo(tamanho=6):
    caracteres = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ''.join(random.choice(caracteres) for _ in range(tamanho))

# --- LÓGICA DE VERIFICAÇÃO (SEPARADA) ---
async def verificar_membro(bot, config_data, membro: discord.Member, user_data: dict):
    guild = membro.guild
    albion_nick = user_data['albion_nick']
    codigo_esperado = user_data['verification_code']

    player_info = await bot.albion_client.get_player_info(await bot.albion_client.search_player(albion_nick))
    if not player_info:
        logging.warning(f"Falha ao obter info de {albion_nick} (ID: {membro.id}).")
        return (False, "Não foi possível encontrar a sua conta Albion. Tente usar `/registrar` novamente.")
        
    player_bio = player_info.get('About', '')
    player_guild = player_info.get('GuildName', '')

    bio_ok = codigo_esperado in player_bio
    guild_ok = player_guild.lower() == config_data['guild_name'].lower()

    if bio_ok and guild_ok:
        # SUCESSO!
        logging.info(f"SUCESSO: {membro.name} ({albion_nick}) verificado.")
        try:
            cargo_membro = guild.get_role(config_data['role_id'])
            cargo_recruta = None
            if config_data.get('recruta_role_id'):
                cargo_recruta = guild.get_role(config_data['recruta_role_id'])

            if not cargo_membro:
                await log_to_channel(bot, guild.id, f"❌ ERRO ADMIN: Cargo de Membro ID `{config_data['role_id']}` não encontrado.", discord.Color.dark_red())
                return (False, "Erro de configuração do servidor (Admin foi notificado).")
                
            cargos_para_adicionar = [cargo_membro]
            cargos_para_remover = []
            if cargo_recruta and cargo_recruta in membro.roles:
                cargos_para_remover.append(cargo_recruta)

            await membro.edit(nick=albion_nick)
            if cargos_para_adicionar: await membro.add_roles(*cargos_para_adicionar, reason="Verificação de Recrutamento")
            if cargos_para_remover: await membro.remove_roles(*cargos_para_remover, reason="Verificação de Recrutamento")
            
            await log_to_channel(bot, guild.id,
                f"✅ **Verificado!** {membro.mention} (`{albion_nick}`) foi promovido.\n"
                f"**Adicionado:** {cargo_membro.mention}\n"
                f"**Removido:** {cargo_recruta.mention if cargo_recruta else 'Nenhum'}",
                discord.Color.green()
            )
            
            await bot.db_manager.execute_query("INSERT INTO recruitment_log (server_id, discord_id, albion_nick, action) VALUES ($1, $2, $3, 'verified_auto')", guild.id, membro.id, albion_nick)
            await bot.db_manager.execute_query("UPDATE guild_members SET status = 'verified', verification_code = NULL WHERE discord_id = $1", membro.id)
            return (True, f"**Bem-vindo(a) à {guild.name}, {membro.mention}!**\n\nA sua conta `{albion_nick}` foi verificada com sucesso. O seu nick e cargos foram atualizados.")

        except discord.Forbidden:
            await log_to_channel(bot, guild.id, f"❌ ERRO ADMIN: Não tenho permissão para dar/remover cargos ou mudar o nick de {membro.mention}.", discord.Color.dark_red())
            return (False, "Erro: Não tenho permissão para alterar os seus cargos ou nick. (Admin foi notificado).")
        except Exception as e:
            logging.error(f"Erro ao promover {membro.name}: {e}")
            return (False, "Ocorreu um erro inesperado ao tentar promovê-lo.")
    else:
        # Falha na verificação
        if not bio_ok:
            logging.info(f"Falha na verificação (Bio): {membro.name} ({albion_nick})")
            return (False, f"Não encontrei o código `{codigo_esperado}` na sua bio do Albion. Por favor, verifique se o copiou corretamente e tente novamente.")
        else: # not guild_ok
            logging.info(f"Falha na verificação (Guilda): {membro.name} ({albion_nick})")
            return (False, f"Ainda não o detectámos na guilda **{config_data['guild_name']}**. Por favor, aguarde que um oficial o aceite no jogo e tente novamente.")


class RecrutamentoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.verificacao_automatica.start()

    # --- Comando /registrar (Lógica do filtro de Fama corrigida) ---
    @app_commands.command(name="registrar", description="Inicia o seu processo de registo na guilda.")
    @app_commands.describe(nick="O seu nick exato no Albion Online.")
    async def registrar(self, interaction: discord.Interaction, nick: str):
        config_data = await self.bot.db_manager.execute_query("SELECT * FROM server_config WHERE server_id = $1", interaction.guild.id, fetch="one")
        
        if not all([config_data, config_data.get('canal_registo_id'), config_data.get('guild_name'), config_data.get('role_id')]):
            return await interaction.response.send_message("O bot ainda não foi totalmente configurado por um admin.", ephemeral=True)
        if interaction.channel.id != config_data['canal_registo_id']:
            canal_correto = interaction.guild.get_channel(config_data['canal_registo_id'])
            return await interaction.response.send_message(f"Por favor, use este comando no canal {canal_correto.mention}.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        player_info = await self.bot.albion_client.get_player_info(
            await self.bot.albion_client.search_player(nick)
        )

        if not player_info:
            await log_to_channel(self.bot, interaction.guild.id, f"⚠️ Tentativa de registo falhou: Nick `{nick}` não encontrado (Utilizador: {interaction.user.mention}).")
            await interaction.followup.send(f"Não encontrei o jogador **{nick}**. Verifique o nome e tente novamente.")
            return

        # --- LÓGICA DE BYPASS E "ANÁLISE MANUAL" ---
        player_guild_name = player_info.get('GuildName', '')
        is_already_member = player_guild_name.lower() == config_data.get('guild_name', '').lower()
        
        log_msg_title = "📝 Novo Registo Aceite"
        embed_title = "✅ Requisitos Atingidos!"
        log_filtro = "OK"

        if not is_already_member:
            pve_data = player_info.get('PvE', {})
            total_fame = pve_data.get('Total', 0)
            kill_fame = player_info.get('KillFame', 0)
            req_total_fame = config_data.get('fame_total', 0)
            req_kill_fame = config_data.get('fame_pvp', 0)

            if total_fame < req_total_fame or kill_fame < req_kill_fame:
                log_msg = (
                    f"⚠️ **Filtro Falhou (Análise Manual)**\n"
                    f"Utilizador: {interaction.user.mention} (`{nick}`)\n"
                    f"Fama Total: `{total_fame:,}` (Req: `{req_total_fame:,}`)\n"
                    f"Fama PvP: `{kill_fame:,}` (Req: `{req_kill_fame:,}`)"
                )
                await log_to_channel(self.bot, interaction.guild.id, log_msg, discord.Color.orange())
                await self.bot.db_manager.execute_query("INSERT INTO recruitment_log (server_id, discord_id, albion_nick, action) VALUES ($1, $2, $3, 'filtered')", interaction.guild.id, interaction.user.id, nick)
                log_filtro = "FALHOU (Pendente Manual)"
                embed_title = "⚠️ Análise Manual Pendente"
        else:
            log_msg_title = "📝 Registo de Membro Antigo"
            embed_title = "👋 Olá, Membro!"
            log_filtro = "Ignorado (Já é membro)"

        # 5. Sucesso (ou bypass) - Gerar código e guardar
        codigo = gerar_codigo()
        await self.bot.db_manager.execute_query(
            "INSERT INTO guild_members (discord_id, server_id, albion_nick, verification_code, status) VALUES ($1, $2, $3, $4, 'pending') "
            "ON CONFLICT (discord_id) DO UPDATE SET "
            "server_id = EXCLUDED.server_id, albion_nick = EXCLUDED.albion_nick, "
            "verification_code = EXCLUDED.verification_code, status = 'pending'",
            interaction.user.id, interaction.guild.id, nick, codigo
        )
        
        log_msg = (
            f"**{log_msg_title}**\n"
            f"Utilizador: {interaction.user.mention} (`{nick}`)\n"
            f"Filtro de Fama: **{log_filtro}**\n"
            f"Código Gerado: `{codigo}`"
        )
        await log_to_channel(self.bot, interaction.guild.id, log_msg, discord.Color.blue())
        await self.bot.db_manager.execute_query("INSERT INTO recruitment_log (server_id, discord_id, albion_nick, action) VALUES ($1, $2, $3, 'registered')", interaction.guild.id, interaction.user.id, nick)

        # 6. Enviar instruções (Embed)
        embed = discord.Embed(title=embed_title, description=f"Olá, {interaction.user.mention}! O seu registo para **{nick}** foi aceite. Siga os passos finais:", color=discord.Color.green())
        if is_already_member:
             embed.add_field(name="Passo 1: No Albion", value=(f"Para confirmar que a conta é sua, cole na sua 'Bio' o código: **`{codigo}`**"), inline=False)
        else:
            embed.add_field(name="Passo 1: No Albion", value=(f"1. Aplique para: **{config_data['guild_name']}**\n2. Cole na sua 'Bio' o código: **`{codigo}`**"), inline=False)
        embed.add_field(name="Passo 2: Aguardar", value=(f"É tudo! O bot irá verificar automaticamente.\n**Para acelerar, use `/verificar`** assim que estiver pronto."), inline=False)
        if log_filtro.startswith("FALHOU"):
             embed.set_footer(text="Nota: A sua fama está abaixo dos requisitos. A sua verificação será concluída, mas um oficial irá rever o seu caso.")
        await interaction.followup.send(embed=embed)

    # --- COMANDO /verificar (CORRIGIDO) ---
    @app_commands.command(name="verificar", description="Tenta verificar manualmente a sua conta após colocar o código na bio.")
    async def verificar(self, interaction: discord.Interaction):
        config_data = await self.bot.db_manager.execute_query("SELECT * FROM server_config WHERE server_id = $1", interaction.guild.id, fetch="one")
        if not config_data or interaction.channel.id != config_data.get('canal_registo_id'):
            return await interaction.response.send_message("Este comando só pode ser usado no canal de recrutamento.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        user_data = await self.bot.db_manager.execute_query("SELECT * FROM guild_members WHERE discord_id = $1 AND status = 'pending'", interaction.user.id, fetch="one")
        if not user_data:
            return await interaction.followup.send("Não encontrei um registo pendente para si. Use `/registrar <nick>` primeiro.")

        sucesso, mensagem = await verificar_membro(self.bot, config_data, interaction.user, user_data)
        
        if sucesso:
            await interaction.followup.send(mensagem, ephemeral=False)
        else:
            # --- CORREÇÃO DE ERRO DE DIGITAÇÃO ---
            await interaction.followup.send(mensagem, ephemeral=True)

    # --- Loop de Verificação (Registo) ---
    @tasks.loop(minutes=3)
    async def verificacao_automatica(self):
        pending_list = await self.bot.db_manager.execute_query("SELECT * FROM guild_members WHERE status = 'pending'", fetch="all")
        if not pending_list: return
        logging.info(f"[Loop de Registo] A verificar {len(pending_list)} utilizadores...")
        
        for user_data in pending_list:
            server_id = user_data['server_id']
            config_data = await self.bot.db_manager.execute_query("SELECT * FROM server_config WHERE server_id = $1", server_id, fetch="one")
            guild = self.bot.get_guild(server_id)
            if not guild or not config_data:
                await self.bot.db_manager.execute_query("DELETE FROM guild_members WHERE discord_id = $1", user_data['discord_id'])
                continue
            
            membro = guild.get_member(user_data['discord_id'])
            if not membro:
                await self.bot.db_manager.execute_query("DELETE FROM guild_members WHERE discord_id = $1", user_data['discord_id'])
                continue
            
            await verificar_membro(self.bot, config_data, membro, user_data)

    @verificacao_automatica.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RecrutamentoCog(bot))