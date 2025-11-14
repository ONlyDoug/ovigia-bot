import discord
from discord.ext import commands, tasks
from discord import app_commands
import database as db
import random
import string
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


# --- View de Aprovação (Botões) ---
class ApprovalView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None) # Botões persistentes
        self.bot = bot

    async def handle_approval(self, interaction: discord.Interaction, action: str):
        # Apenas staff Nível 1+ pode clicar
        if not await has_permission(1).predicate(interaction): return

        await interaction.response.defer() # Reconhece o clique

        # 1. Obter dados da DB
        user_data = await self.bot.db_manager.execute_query(
            "SELECT * FROM guild_members WHERE discord_id = $1",
            int(interaction.message.embeds[0].footer.text.split("ID: ")[1]), # Puxa o ID do rodapé
            fetch="one"
        )
        
        if not user_data or user_data['status'] == 'verified':
            embed = interaction.message.embeds[0]
            embed.title = "Ação já processada"
            embed.color = discord.Color.greyple()
            for item in self.children: item.disabled = True
            await interaction.edit_original_message(embed=embed, view=self)
            return

        config_data = await self.bot.db_manager.execute_query("SELECT * FROM server_config WHERE server_id = $1", interaction.guild.id, fetch="one")
        membro = interaction.guild.get_member(user_data['discord_id'])
        albion_nick = user_data['albion_nick']

        if not membro:
            await log_to_channel(self.bot, interaction.guild.id, f"❌ Falha na aprovação: Membro <@{user_data['discord_id']}> (`{albion_nick}`) não está no servidor.", discord.Color.red())
            await self.bot.db_manager.execute_query("DELETE FROM guild_members WHERE discord_id = $1", user_data['discord_id'])
            return await interaction.followup.send(f"Erro: O membro <@{user_data['discord_id']}> saiu do servidor. Registo apagado.", ephemeral=True)

        # --- AÇÃO: REJEITAR ---
        if action == 'reject':
            await self.bot.db_manager.execute_query("DELETE FROM guild_members WHERE discord_id = $1", membro.id)
            await self.bot.db_manager.execute_query("INSERT INTO recruitment_log (server_id, discord_id, albion_nick, action, admin_id) VALUES ($1, $2, $3, 'rejected_manual', $4)", interaction.guild.id, membro.id, albion_nick, interaction.user.id)
            
            embed = interaction.message.embeds[0]
            embed.title = "❌ Aplicação REJEITADA"
            embed.color = discord.Color.red()
            embed.set_footer(text=f"Rejeitado por: {interaction.user.display_name}")
            for item in self.children: item.disabled = True
            await interaction.edit_original_message(embed=embed, view=self)
            
            try: await membro.send(f"Olá! A sua aplicação para a guilda foi revista pela nossa equipa de Suporte e **rejeitada**. Contacte um recrutador se achar que isto foi um erro.")
            except discord.Forbidden: pass
            return

        # --- AÇÃO: APROVAR ---
        player_info = await self.bot.albion_client.get_player_info(await self.bot.albion_client.search_player(albion_nick))
        if not player_info:
            return await interaction.followup.send(f"Falha na aprovação: Não consigo encontrar o jogador `{albion_nick}` na API.", ephemeral=True)

        player_guild_name = player_info.get('GuildName', '')
        player_alliance_name = player_info.get('AllianceName', '')
        modo = config_data.get('mode', 'guild')
        
        main_guild_name = config_data.get('main_guild_name', '').lower()
        alliance_name = config_data.get('alliance_name', '').lower()

        is_in_main_guild = player_guild_name.lower() == main_guild_name
        is_in_alliance = player_alliance_name.lower() == alliance_name

        # Define o TAG da guilda para o nick
        guild_tag = f"[{player_info.get('GuildTag', 'N/A')}] " if player_info.get('GuildTag') else ""
        novo_nick = f"{guild_tag}{albion_nick}"
        
        if len(novo_nick) > 32:
            novo_nick = novo_nick[:32]

        try:
            cargos_para_adicionar = []
            cargos_para_remover = []
            log_cargos_add = []

            # 1. Definir o cargo a adicionar (SÓ PARA MODO GUILDA)
            if modo == 'guild':
                if not is_in_main_guild:
                    return await interaction.followup.send(f"**Falha na Aprovação!**\nO jogador `{albion_nick}` **não** está na guilda principal (`{main_guild_name}`).\n\nPor favor, aceite-o **dentro do jogo** primeiro e depois clique em 'Aprovar' novamente.", ephemeral=True)
                
                cargo_membro = interaction.guild.get_role(config_data['main_guild_role_id'])
                if cargo_membro: 
                    cargos_para_adicionar.append(cargo_membro)
                    log_cargos_add.append(cargo_membro.mention)
                else: 
                    await log_to_channel(self.bot, interaction.guild.id, f"❌ ERRO ADMIN: Cargo de Membro (Principal) ID `{config_data['main_guild_role_id']}` não encontrado.", discord.Color.dark_red())
            else:
                 await log_to_channel(self.bot, interaction.guild.id, f"⚠️ AVISO: O comando /registrar foi usado, mas o bot está em 'Modo Aliança'. Use /alianca_registrar para automação.", discord.Color.orange())
                 # Se mesmo assim quiser adicionar o cargo principal (para a "galera")
                 if is_in_main_guild and config_data.get('main_guild_role_id'):
                     cargo_principal = interaction.guild.get_role(config_data['main_guild_role_id'])
                     if cargo_principal:
                         cargos_para_adicionar.append(cargo_principal)
                         log_cargos_add.append(cargo_principal.mention)
            
            # 2. Cargo de Recruta (Remover)
            if config_data.get('recruta_role_id'):
                cargo_recruta = interaction.guild.get_role(config_data['recruta_role_id'])
                if cargo_recruta and cargo_recruta in membro.roles:
                    cargos_para_remover.append(cargo_recruta)

            # 3. Executar Ações
            await membro.edit(nick=novo_nick)
            if cargos_para_adicionar: await membro.add_roles(*cargos_para_adicionar, reason=f"Aprovado por {interaction.user.name}")
            if cargos_para_remover: await membro.remove_roles(*cargos_para_remover, reason=f"Aprovado por {interaction.user.name}")
            
            # 4. Atualizar DB
            await self.bot.db_manager.execute_query("UPDATE guild_members SET status = 'verified' WHERE discord_id = $1", membro.id)
            await self.bot.db_manager.execute_query("INSERT INTO recruitment_log (server_id, discord_id, albion_nick, action, admin_id) VALUES ($1, $2, $3, 'approved_manual', $4)", interaction.guild.id, membro.id, albion_nick, interaction.user.id)
            
            # 5. Atualizar Mensagem (Log e Embed)
            log_cargos_rem = cargo_recruta.mention if cargo_recruta and cargos_para_remover else 'Nenhum'
            await log_to_channel(self.bot, interaction.guild.id,
                f"✅ **Aprovado Manualmente!**\n"
                f"**Staff:** {interaction.user.mention}\n"
                f"**Membro:** {membro.mention} (`{albion_nick}`)\n"
                f"**Nick:** `{novo_nick}`\n"
                f"**Adicionado:** {', '.join(log_cargos_add) or 'Nenhum'}\n"
                f"**Removido:** {log_cargos_rem}",
                discord.Color.green()
            )
            
            embed = interaction.message.embeds[0]
            embed.title = "✅ Aplicação APROVADA"
            embed.color = discord.Color.green()
            embed.set_footer(text=f"Aprovado por: {interaction.user.display_name}")
            for item in self.children: item.disabled = True
            await interaction.edit_original_message(embed=embed, view=self)

            try: await membro.send(f"🎉 **Bem-vindo(a)!** A sua aplicação foi **aprovada** pela nossa equipa de Suporte. O seu nick e cargos foram atualizados.")
            except discord.Forbidden: pass

        except discord.Forbidden:
            await log_to_channel(self.bot, interaction.guild.id, f"❌ ERRO ADMIN: Tentei aprovar {membro.mention}, mas não tenho permissão para alterar cargos ou nicks.", discord.Color.dark_red())
            await interaction.followup.send("Erro: Não tenho permissão para alterar os cargos ou nick deste membro.", ephemeral=True)
        except Exception as e:
            logging.error(f"Erro ao aprovar {membro.name}: {e}")
            await interaction.followup.send(f"Ocorreu um erro inesperado: {e}", ephemeral=True)


    @discord.ui.button(label="Aprovar", style=discord.ButtonStyle.success, custom_id="approve_recruit_v3") # ID alterado
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_approval(interaction, "approve")

    @discord.ui.button(label="Rejeitar", style=discord.ButtonStyle.danger, custom_id="reject_recruit_v3") # ID alterado
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.handle_approval(interaction, "reject")


class RecrutamentoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Adiciona a View persistente
        self.bot.add_view(ApprovalView(bot))

    @app_commands.command(name="registrar", description="Inicia o seu processo de registo na GUILDA.")
    @app_commands.describe(nick="O seu nick exato no Albion Online.")
    async def registrar(self, interaction: discord.Interaction, nick: str):
        config_data = await self.bot.db_manager.execute_query("SELECT * FROM server_config WHERE server_id = $1", interaction.guild.id, fetch="one")
        
        if not all([config_data, config_data.get('canal_registo_id'), config_data.get('canal_aprovacao_id')]):
            return await interaction.response.send_message("O bot ainda não foi totalmente configurado por um admin.", ephemeral=True)
        if interaction.channel.id != config_data['canal_registo_id']:
            canal_correto = interaction.guild.get_channel(config_data['canal_registo_id'])
            return await interaction.response.send_message(f"Por favor, use este comando no canal {canal_correto.mention}.", ephemeral=True)

        # Se o bot estiver em Modo Aliança, avisa o utilizador para usar o comando /alianca
        modo = config_data.get('mode', 'guild')
        if modo == 'alliance':
            return await interaction.response.send_message("Este servidor está em **Modo Aliança**. Por favor, use o comando `/alianca_registrar`.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        
        player_info = await self.bot.albion_client.get_player_info(await self.bot.albion_client.search_player(nick))
        if not player_info:
            await log_to_channel(self.bot, interaction.guild.id, f"⚠️ Tentativa de registo falhou: Nick `{nick}` não encontrado (Utilizador: {interaction.user.mention}).")
            await interaction.followup.send(f"Não encontrei o jogador **{nick}**. Verifique o nome e tente novamente.")
            return
            
        existing_member = await self.bot.db_manager.execute_query("SELECT status FROM guild_members WHERE discord_id = $1", interaction.user.id, fetch="one")
        if existing_member:
            if existing_member['status'] == 'pending':
                return await interaction.followup.send("Você já tem uma aplicação pendente de aprovação pela staff. Por favor, aguarde.")
            if existing_member['status'] == 'verified':
                return await interaction.followup.send("Você já está verificado neste servidor.")

        guild_name = config_data.get('main_guild_name', '')
        player_guild_name = player_info.get('GuildName', '')
        is_already_member = player_guild_name.lower() == guild_name.lower()
        
        # --- LÓGICA DE FILTRO (Apenas Modo Guilda) ---
        if not is_already_member:
            pve_data = player_info.get('PvE', {})
            total_fame = pve_data.get('Total', 0) 
            kill_fame = player_info.get('KillFame', 0)
            req_total_fame = config_data.get('fame_total', 0)
            req_kill_fame = config_data.get('fame_pvp', 0)

            if total_fame < req_total_fame or kill_fame < req_kill_fame:
                log_msg = (
                    f"❌ **Filtro Falhou**\n"
                    f"Utilizador: {interaction.user.mention} (`{nick}`)\n"
                    f"Fama Total: `{total_fame:,}` (Req: `{req_total_fame:,}`)\n"
                    f"Fama PvP: `{kill_fame:,}` (Req: `{req_kill_fame:,}`)"
                )
                await log_to_channel(self.bot, interaction.guild.id, log_msg, discord.Color.red())
                await self.bot.db_manager.execute_query("INSERT INTO recruitment_log (server_id, discord_id, albion_nick, action) VALUES ($1, $2, $3, 'filtered_low_fame')", interaction.guild.id, interaction.user.id, nick)
                
                await interaction.followup.send(
                    f"Olá, {interaction.user.mention}! Vimos que não cumpre todos os requisitos mínimos:\n\n"
                    f"**Sua Fama Total:** `{total_fame:,}` (Mínimo: `{req_total_fame:,}`)\n"
                    f"**Sua Fama PvP:** `{kill_fame:,}` (Mínimo: `{req_kill_fame:,}`)\n\n"
                    "Contacte um Oficial se for um caso especial."
                )
                return
        
        # --- SUCESSO NO FILTRO (ou Membro Antigo) ---
        await self.bot.db_manager.execute_query(
            "INSERT INTO guild_members (discord_id, server_id, albion_nick, status) VALUES ($1, $2, $3, 'pending') "
            "ON CONFLICT (discord_id) DO UPDATE SET "
            "server_id = EXCLUDED.server_id, albion_nick = EXCLUDED.albion_nick, status = 'pending'",
            interaction.user.id, interaction.guild.id, nick
        )
        
        pve_fame = player_info.get('PvE', {}).get('Total', 0)
        pvp_fame = player_info.get('KillFame', 0)
        player_alliance_name = player_info.get('AllianceName', '')

        log_msg_title = "📝 Nova Aplicação Recebida"
        if is_already_member: log_msg_title = "📝 Sincronização de Membro Antigo"
        
        await log_to_channel(self.bot, interaction.guild.id, 
            f"**{log_msg_title}**\n"
            f"Utilizador: {interaction.user.mention} (`{nick}`)\n"
            f"Fama: `PvE: {pve_fame:,} | PvP: {pvp_fame:,}`\n"
            f"**Aguardando aprovação da equipa de Suporte...**",
            discord.Color.blue()
        )
        await self.bot.db_manager.execute_query("INSERT INTO recruitment_log (server_id, discord_id, albion_nick, action) VALUES ($1, $2, $3, 'registered')", interaction.guild.id, interaction.user.id, nick)

        # Envia o cartão para o canal #⏳-aprovações
        canal_aprovacao = self.bot.get_channel(config_data['canal_aprovacao_id'])
        if canal_aprovacao:
            embed_aprovacao = discord.Embed(title="⏳ Nova Aplicação (PENDENTE)", color=discord.Color.orange(), timestamp=datetime.utcnow())
            embed_aprovacao.add_field(name="Discord", value=interaction.user.mention, inline=True)
            embed_aprovacao.add_field(name="Albion Nick", value=nick, inline=True)
            embed_aprovacao.add_field(name="Status no Jogo", value=f"Guilda: `{player_guild_name or 'N/A'}`\nAliança: `{player_alliance_name or 'N/A'}`", inline=False)
            embed_aprovacao.add_field(name="Fama PvE Total", value=f"`{pve_fame:,}`", inline=True)
            embed_aprovacao.add_field(name="Fama PvP Total", value=f"`{pvp_fame:,}`", inline=True)
            embed_aprovacao.set_thumbnail(url=interaction.user.display_avatar.url)
            embed_aprovacao.set_footer(text=f"ID do Utilizador: {interaction.user.id}")
            
            await canal_aprovacao.send(embed=embed_aprovacao, view=ApprovalView(self.bot))
        else:
            logging.error(f"Canal de aprovações (ID: {config_data['canal_aprovacao_id']}) não encontrado!")

        # Envia DM/Resposta ao utilizador
        msg_final = f"✅ **Aplicação Recebida!**\nO seu registo para `{nick}` foi enviado para a nossa equipa de Suporte.\n**Próximo Passo:** Por favor, aplique para a guilda **dentro do jogo** e aguarde a aprovação."
        if is_already_member:
            msg_final = f"👋 **Olá, Membro!**\nRecebemos o seu pedido para sincronizar a conta `{nick}`.\nUma notificação foi enviada à equipa de Suporte para confirmar e atualizar o seu nick/cargos."
        
        await interaction.followup.send(msg_final, ephemeral=True)

async def setup(bot):
    await bot.add_cog(RecrutamentoCog(bot))