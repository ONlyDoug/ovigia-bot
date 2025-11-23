import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger("RecrutamentoCog")

class ApprovalView(discord.ui.View):
    """View persistente para aprovação de recrutas"""
    
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    @discord.ui.button(
        label="Aprovar",
        style=discord.ButtonStyle.green,
        custom_id="approval_view:approve"
    )
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Aprova um recruta"""
        await interaction.response.defer()
        
        try:
            embed = interaction.message.embeds[0]
            user_id = int(embed.footer.text.split("ID: ")[1])
            albion_nick = embed.fields[0].value
            
            # Buscar configuração
            config = await self.bot.db.fetchrow_query(
                "SELECT * FROM server_config WHERE guild_id = $1",
                interaction.guild_id
            )
            
            if not config:
                await interaction.followup.send("❌ Configuração não encontrada.", ephemeral=True)
                return
            
            # Verificar se jogador ainda existe na API
            player = await self.bot.albion.search_player(albion_nick)
            if not player:
                await interaction.followup.send("❌ Jogador não encontrado na API.", ephemeral=True)
                return
            
            # Obter membro do Discord
            member = interaction.guild.get_member(user_id)
            if not member:
                await interaction.followup.send("❌ Membro não encontrado no servidor.", ephemeral=True)
                return
            
            # Atualizar cargos e nickname
            try:
                recruit_role = interaction.guild.get_role(config['recruit_role_id'])
                member_role = interaction.guild.get_role(config['member_role_id'])
                
                if recruit_role and recruit_role in member.roles:
                    await member.remove_roles(recruit_role)
                
                if member_role:
                    await member.add_roles(member_role)
                
                # Atualizar nickname
                guild_tag = config['guild_tag']
                new_nick = f"[{guild_tag}] {albion_nick}"
                await member.edit(nick=new_nick[:32])
                
                # Atualizar log no banco
                await self.bot.db.execute_query(
                    "UPDATE recruitment_log SET status = 'APPROVED', reviewed_by = $1 WHERE user_id = $2 AND status = 'PENDING'",
                    interaction.user.id,
                    user_id
                )
                
                # Desabilitar botões
                for item in self.children:
                    item.disabled = True
                await interaction.message.edit(view=self)
                
                await interaction.followup.send(
                    f"✅ {member.mention} aprovado! Cargos e nickname atualizados."
                )
                
            except discord.Forbidden:
                await interaction.followup.send(
                    "❌ Sem permissões para gerenciar cargos/nicknames.",
                    ephemeral=True
                )
            except Exception as e:
                logger.error(f"Erro ao aprovar: {e}")
                await interaction.followup.send(f"❌ Erro: {e}", ephemeral=True)
                
        except Exception as e:
            logger.error(f"Erro ao processar aprovação: {e}")
            await interaction.followup.send("❌ Erro ao processar aprovação.", ephemeral=True)
    
    @discord.ui.button(
        label="Rejeitar",
        style=discord.ButtonStyle.red,
        custom_id="approval_view:reject"
    )
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Rejeita um recruta"""
        await interaction.response.send_message(
            "❌ Rejeitado (funcionalidade em desenvolvimento).",
            ephemeral=True
        )


class RecrutamentoCog(commands.Cog):
    """Cog para sistema de recrutamento"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="registrar",
        description="Registrar-se na guilda"
    )
    @app_commands.describe(nickname="Seu nickname no Albion Online")
    async def registrar(self, interaction: discord.Interaction, nickname: str):
        """Comando para registrar-se na guilda"""
        await interaction.response.defer(ephemeral=True)
        
        # Buscar configuração
        config = await self.bot.db.fetchrow_query(
            "SELECT * FROM server_config WHERE guild_id = $1",
            interaction.guild_id
        )
        
        if not config:
            await interaction.followup.send(
                "❌ Bot não configurado. Peça a um admin para usar `/admin_setup`."
            )
            return
        
        # Verificar modo de operação
        server_type = config.get('server_type', 'GUILD')
        if server_type not in ['GUILD', 'HYBRID']:
            await interaction.followup.send(
                f"⚠️ Este comando está desativado. Servidor em modo **{server_type}**."
            )
            return
        
        # Verificar se canais estão configurados
        if not config['recruitment_channel_id'] or not config['approval_channel_id']:
            await interaction.followup.send(
                "❌ Sistema de recrutamento não configurado (canais faltando)."
            )
            return
        
        # Buscar jogador na API do Albion
        player = await self.bot.albion.search_player(nickname)
        if not player:
            await interaction.followup.send(
                f"❌ Jogador '{nickname}' não encontrado no Albion Online."
            )
            return
        
        # Verificar requisitos de fama
        pve_fame = player.get('LifetimeStatistics', {}).get('PvE', {}).get('Total', 0)
        pvp_fame = player.get('KillFame', 0)
        
        min_pve = config['min_fame_pve'] or 0
        min_pvp = config['min_fame_pvp'] or 0
        
        meets_requirements = pve_fame >= min_pve and pvp_fame >= min_pvp
        
        # Criar embed para aprovação
        approval_channel = interaction.guild.get_channel(config['approval_channel_id'])
        
        if not approval_channel:
            await interaction.followup.send("❌ Canal de aprovação não encontrado.")
            return
        
        embed = discord.Embed(
            title="📋 Solicitação de Recrutamento",
            color=discord.Color.green() if meets_requirements else discord.Color.orange()
        )
        embed.add_field(name="Nickname", value=player['Name'], inline=True)
        embed.add_field(
            name="Guilda Atual",
            value=player.get('GuildName', 'Nenhuma'),
            inline=True
        )
        embed.add_field(name="Fama PvE", value=f"{pve_fame:,}", inline=True)
        embed.add_field(name="Fama PvP", value=f"{pvp_fame:,}", inline=True)
        embed.add_field(
            name="Requisitos",
            value=f"PvE: {min_pve:,} | PvP: {min_pvp:,}",
            inline=True
        )
        embed.add_field(
            name="Status",
            value="✅ Atende" if meets_requirements else "⚠️ Não atende (análise manual)",
            inline=True
        )
        embed.add_field(
            name="Usuário Discord",
            value=interaction.user.mention,
            inline=False
        )
        embed.set_footer(text=f"ID: {interaction.user.id}")
        
        # Enviar para canal de aprovação
        view = ApprovalView(self.bot)
        await approval_channel.send(embed=embed, view=view)
        
        # Registrar no banco
        await self.bot.db.execute_query(
            "INSERT INTO recruitment_log (user_id, guild_id, albion_nick, status) VALUES ($1, $2, $3, 'PENDING')",
            interaction.user.id,
            interaction.guild_id,
            player['Name']
        )
        
        await interaction.followup.send(
            "✅ Registro enviado para aprovação! Aguarde a análise da equipe."
        )

async def setup(bot):
    await bot.add_cog(RecrutamentoCog(bot))