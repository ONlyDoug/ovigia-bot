import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger("RecrutamentoCog")

class ApprovalView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None) # View persistente
        self.bot = bot

    @discord.ui.button(label="Aprovar", style=discord.ButtonStyle.green, custom_id="approval_view:approve")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        # Extrair info do embed
        try:
            embed = interaction.message.embeds[0]
            # Assumindo que o User ID está no rodapé
            user_id = int(embed.footer.text.split("ID: ")[1])
            albion_nick = embed.fields[0].value
            
            # Obter config
            config = await self.bot.db.fetchrow_query("SELECT * FROM server_config WHERE guild_id = $1", interaction.guild_id)
            if not config:
                await interaction.followup.send("Configuração do servidor não encontrada.", ephemeral=True)
                return

            # Verificar API novamente
            player_info = await self.bot.albion.search_player(albion_nick)
            if not player_info:
                await interaction.followup.send("Jogador não encontrado na API.", ephemeral=True)
                return
                
            guild_tag = config['guild_tag']
            
            # Obter o membro
            guild = interaction.guild
            member = guild.get_member(user_id)
            if not member:
                await interaction.followup.send("Membro não encontrado no servidor Discord.", ephemeral=True)
                return

            # Atualizar Cargos e Nick
            try:
                recruit_role = guild.get_role(config['recruit_role_id'])
                member_role = guild.get_role(config['member_role_id'])
                
                if recruit_role:
                    await member.remove_roles(recruit_role)
                if member_role:
                    await member.add_roles(member_role)
                
                new_nick = f"[{guild_tag}] {albion_nick}"
                await member.edit(nick=new_nick[:32]) # Limite do Discord
                
                await interaction.followup.send(f"Aprovado {member.mention}. Cargos e Nick atualizados.")
                
                # Atualizar Log
                await self.bot.db.execute_query("UPDATE recruitment_log SET status = 'APPROVED', reviewed_by = $1 WHERE user_id = $2 AND status = 'PENDING'", interaction.user.id, user_id)
                
                # Desabilitar botões
                for item in self.children:
                    item.disabled = True
                await interaction.message.edit(view=self)

            except discord.Forbidden:
                await interaction.followup.send("Bot sem permissões para gerenciar cargos/apelidos.", ephemeral=True)
            except Exception as e:
                logger.error(f"Erro na aprovação: {e}")
                await interaction.followup.send(f"Erro: {e}", ephemeral=True)

        except Exception as e:
            logger.error(f"Erro ao analisar embed de aprovação: {e}")
            await interaction.followup.send("Erro ao processar aprovação.", ephemeral=True)

    @discord.ui.button(label="Rejeitar", style=discord.ButtonStyle.red, custom_id="approval_view:reject")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Lógica similar ao aprovar mas apenas atualiza log e notifica
        await interaction.response.send_message("Rejeitado (Ainda não implementado completamente).", ephemeral=True)


class RecrutamentoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="registrar", description="Registrar-se na guilda")
    @app_commands.describe(nickname="Seu apelido no Albion Online")
    async def registrar(self, interaction: discord.Interaction, nickname: str):
        await interaction.response.defer(ephemeral=True)
        
        guild_id = interaction.guild_id
        config = await self.bot.db.fetchrow_query("SELECT * FROM server_config WHERE guild_id = $1", guild_id)
        
        if not config:
            await interaction.followup.send("Bot não configurado. Peça a um admin para rodar /admin_setup.")
            return

        # Verificar Modo de Operação
        server_type = config.get('server_type', 'GUILD')
        if server_type not in ['GUILD', 'HYBRID']:
            await interaction.followup.send(f"⚠️ Comando desativado. Este servidor está operando em modo **{server_type}** (apenas Aliança).")
            return

        # Verificar se o sistema de recrutamento está ativo
        if not config['recruitment_channel_id'] or not config['approval_channel_id']:
            await interaction.followup.send("O sistema de recrutamento não está ativado neste servidor (canais não configurados).")
            return

        # 1. Verificar API
        player = await self.bot.albion.search_player(nickname)
        if not player:
            await interaction.followup.send(f"Jogador '{nickname}' não encontrado na API do Albion.")
            return

        # 2. Verificar requisitos
        pve_fame = player.get('LifetimeStatistics', {}).get('PvE', {}).get('Total', 0)
        pvp_fame = player.get('KillFame', 0)
        
        min_pve = config['min_fame_pve']
        min_pvp = config['min_fame_pvp']
        
        passed_reqs = True
        if pve_fame < min_pve or pvp_fame < min_pvp:
            passed_reqs = False
            
        msg = f"Solicitação de registro para {nickname}.\n"
        if not passed_reqs:
            msg += f"⚠️ Não atende aos requisitos automáticos (PvE: {pve_fame}/{min_pve}, PvP: {pvp_fame}/{min_pvp}). Enviado para análise manual."
        else:
            msg += "✅ Atende aos requisitos."

        # Enviar para Canal de Aprovação
        approval_channel_id = config['approval_channel_id']
        approval_channel = interaction.guild.get_channel(approval_channel_id)
        
        if approval_channel:
            embed = discord.Embed(title="Solicitação de Recrutamento", color=discord.Color.blue())
            embed.add_field(name="Apelido", value=player['Name'], inline=True)
            embed.add_field(name="Guilda", value=player.get('GuildName', 'Nenhuma'), inline=True)
            embed.add_field(name="Fama PvE", value=f"{pve_fame:,}", inline=True)
            embed.add_field(name="Fama PvP", value=f"{pvp_fame:,}", inline=True)
            embed.add_field(name="Usuário Discord", value=interaction.user.mention, inline=False)
            embed.set_footer(text=f"ID: {interaction.user.id}")
            
            view = ApprovalView(self.bot)
            await approval_channel.send(embed=embed, view=view)
            await interaction.followup.send("Registro enviado para aprovação.")
            
            # Logar no DB
            await self.bot.db.execute_query(
                "INSERT INTO recruitment_log (user_id, guild_id, albion_nick, status) VALUES ($1, $2, $3, 'PENDING')",
                interaction.user.id, guild_id, player['Name']
            )
        else:
            await interaction.followup.send("Canal de aprovação não configurado.")

async def setup(bot):
    await bot.add_cog(RecrutamentoCog(bot))