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
        if not config_data or not config_data.get('canal_logs_id'):
            return
        log_channel = bot.get_channel(config_data['canal_logs_id'])
        if log_channel:
            if color: await log_channel.send(embed=discord.Embed(description=message, color=color))
            else: await log_channel.send(message)
    except Exception as e: print(f"Erro ao enviar log para o canal: {e}")

# --- Função de Gerar Código (Auxiliar) ---
def gerar_codigo(tamanho=6):
    caracteres = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return ''.join(random.choice(caracteres) for _ in range(tamanho))

class RecrutamentoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.verificacao_automatica.start()

    # --- Comando /registrar (ATUALIZADO) ---
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
            await interaction.followup.send(f"Não encontrei o jogador **{nick}**. Verifique o nome (maiúsculas/minúsculas) e tente novamente.")
            return

        # --- LÓGICA DE BYPASS (CORRIGIDA) ---
        player_guild_name = player_info.get('GuildName', '')
        is_already_member = player_guild_name.lower() == config_data.get('guild_name', '').lower()

        # Se NÃO for membro, aplicamos o filtro.
        if not is_already_member:
            # --- CORREÇÃO DO BUG DA FAMA ---
            pve_data = player_info.get('PvE', {}) # Objeto PvE
            total_fame = pve_data.get('Total', 0) # Fama PvE Total
            kill_fame = player_info.get('KillFame', 0) # Fama PvP
            # --- FIM DA CORREÇÃO ---
            
            req_total_fame = config_data.get('fame_total', 0)
            req_kill_fame = config_data.get('fame_pvp', 0)

            if total_fame < req_total_fame or kill_fame < req_kill_fame:
                log_msg = (
                    f"❌ **Filtro Falhou**\n"
                    f"Utilizador: {interaction.user.mention} (`{nick}`)\n"
                    f"Fama Total: `{total_fame:,}` (Req: `{req_total_fame:,}`)\n"
                    f"Fama PvP: `{kill_fame:,}` (Req: `{req_kill_fame:,}`)\n"
                    f"*Para aprovar manualmente, use `/admin aprovar_manual`.*"
                )
                await log_to_channel(self.bot, interaction.guild.id, log_msg, discord.Color.red())
                # Log para a DB
                await self.bot.db_manager.execute_query(
                    "INSERT INTO recruitment_log (server_id, discord_id, albion_nick, action) VALUES ($1, $2, $3, 'filtered')",
                    interaction.guild.id, interaction.user.id, nick
                )
                
                await interaction.followup.send(
                    f"Olá, {interaction.user.mention}! Vimos que não cumpre todos os requisitos mínimos:\n\n"
                    f"**Sua Fama Total:** `{total_fame:,}` (Mínimo: `{req_total_fame:,}`)\n"
                    f"**Sua Fama PvP:** `{kill_fame:,}` (Mínimo: `{req_kill_fame:,}`)\n\n"
                    "Continue a jogar e volte a tentar quando atingir os objetivos! "
                    "Se acha que isto é um erro ou se é um caso especial, contacte um Oficial."
                )
                return

        # 5. Sucesso no Filtro (ou filtro ignorado)
        codigo = gerar_codigo()
        await self.bot.db_manager.execute_query(
            "INSERT INTO guild_members (discord_id, server_id, albion_nick, verification_code, status) VALUES ($1, $2, $3, $4, 'pending') "
            "ON CONFLICT (discord_id) DO UPDATE SET "
            "server_id = EXCLUDED.server_id, albion_nick = EXCLUDED.albion_nick, "
            "verification_code = EXCLUDED.verification_code, status = 'pending'",
            interaction.user.id, interaction.guild.id, nick, codigo
        )
        
        log_msg_title = "📝 Novo Registo Aceite" if not is_already_member else "📝 Registo de Membro Antigo"
        embed_title = "✅ Requisitos Atingidos!" if not is_already_member else "👋 Olá, Membro!"

        log_msg = (
            f"**{log_msg_title}**\n"
            f"Utilizador: {interaction.user.mention} (`{nick}`)\n"
            f"Filtro de Fama: {'Ignorado (Já é membro)' if is_already_member else 'OK'}\n"
            f"Código Gerado: `{codigo}`"
        )
        await log_to_channel(self.bot, interaction.guild.id, log_msg, discord.Color.blue())
        # Log para a DB
        await self.bot.db_manager.execute_query(
            "INSERT INTO recruitment_log (server_id, discord_id, albion_nick, action) VALUES ($1, $2, $3, 'registered')",
            interaction.guild.id, interaction.user.id, nick
        )

        # 6. Enviar instruções (Embed)
        embed = discord.Embed(title=embed_title, description=f"Olá, {interaction.user.mention}! O seu registo para **{nick}** foi aceite. Siga os passos finais:", color=discord.Color.green())
        if is_already_member:
             embed.add_field(name="Passo 1: No Albion", value=(f"Para confirmar que a conta é sua, cole na sua 'Bio' o código: **`{codigo}`**"), inline=False)
        else:
            embed.add_field(name="Passo 1: No Albion", value=(f"1. Aplique para: **{config_data['guild_name']}**\n2. Cole na sua 'Bio' o código: **`{codigo}`**"), inline=False)
        embed.add_field(name="Passo 2: Aguardar", value="É tudo! O bot irá verificar automaticamente.", inline=False)
        await interaction.followup.send(embed=embed)

    # --- Loop de Verificação (Registo) ---
    @tasks.loop(minutes=3)
    async def verificacao_automatica(self):
        pending_list = await self.bot.db_manager.execute_query("SELECT * FROM guild_members WHERE status = 'pending'", fetch="all")
        if not pending_list: return
        logging.info(f"[Loop de Registo] A verificar {len(pending_list)} utilizadores...")
        
        for user_data in pending_list:
            user_id = user_data['discord_id']
            server_id = user_data['server_id']
            albion_nick = user_data['albion_nick']
            codigo_esperado = user_data['verification_code']
            
            config_data = await self.bot.db_manager.execute_query("SELECT * FROM server_config WHERE server_id = $1", server_id, fetch="one")
            guild = self.bot.get_guild(server_id)
            
            if not guild or not config_data:
                await self.bot.db_manager.execute_query("DELETE FROM guild_members WHERE discord_id = $1", user_id)
                continue
            membro = guild.get_member(user_id)
            if not membro:
                await self.bot.db_manager.execute_query("DELETE FROM guild_members WHERE discord_id = $1", user_id)
                continue
            if not all([config_data.get('guild_name'), config_data.get('role_id')]):
                continue

            player_info = await self.bot.albion_client.get_player_info(await self.bot.albion_client.search_player(albion_nick))
            if not player_info:
                logging.warning(f"[Loop de Registo] Falha ao obter info de {albion_nick}.")
                continue
                
            player_bio = player_info.get('About', '')
            player_guild = player_info.get('GuildName', '')

            bio_ok = codigo_esperado in player_bio
            guild_ok = player_guild.lower() == config_data['guild_name'].lower()

            if bio_ok and guild_ok:
                logging.info(f"SUCESSO: {membro.name} ({albion_nick}) verificado.")
                try:
                    cargo_membro = guild.get_role(config_data['role_id'])
                    cargo_recruta = None
                    if config_data.get('recruta_role_id'):
                        cargo_recruta = guild.get_role(config_data['recruta_role_id'])

                    if not cargo_membro:
                        await log_to_channel(self.bot, guild.id, f"❌ ERRO ADMIN: Cargo de Membro ID `{config_data['role_id']}` não encontrado.", discord.Color.dark_red())
                        continue
                        
                    cargos_para_adicionar = [cargo_membro]
                    cargos_para_remover = []
                    if cargo_recruta and cargo_recruta in membro.roles:
                        cargos_para_remover.append(cargo_recruta)

                    await membro.edit(nick=albion_nick)
                    if cargos_para_adicionar: await membro.add_roles(*cargos_para_adicionar, reason="Verificação de Recrutamento")
                    if cargos_para_remover: await membro.remove_roles(*cargos_para_remover, reason="Verificação de Recrutamento")
                    
                    await log_to_channel(self.bot, guild.id,
                        f"✅ **Verificado!** {membro.mention} (`{albion_nick}`) foi promovido.\n"
                        f"**Adicionado:** {cargo_membro.mention}\n"
                        f"**Removido:** {cargo_recruta.mention if cargo_recruta else 'Nenhum'}",
                        discord.Color.green()
                    )
                    
                    # Log para a DB
                    await self.bot.db_manager.execute_query(
                        "INSERT INTO recruitment_log (server_id, discord_id, albion_nick, action) VALUES ($1, $2, $3, 'verified_auto')",
                        guild.id, membro.id, albion_nick
                    )
                    
                    await self.bot.db_manager.execute_query(
                        "UPDATE guild_members SET status = 'verified', verification_code = NULL WHERE discord_id = $1",
                        user_id
                    )
                except discord.Forbidden:
                    await log_to_channel(self.bot, guild.id, f"❌ ERRO ADMIN: Não tenho permissão para dar/remover cargos ou mudar o nick de {membro.mention}.", discord.Color.dark_red())
                except Exception as e:
                    logging.error(f"Erro ao promover {membro.name}: {e}")
            else:
                logging.info(f"[Loop de Registo] {membro.name} ({albion_nick}) pendente (Bio: {bio_ok}, Guilda: {guild_ok})")

    @verificacao_automatica.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(RecrutamentoCog(bot))