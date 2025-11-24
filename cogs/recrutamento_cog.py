import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger("RecrutamentoCog")

class ApprovalView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(label="Aprovar", style=discord.ButtonStyle.green, custom_id="approval:approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        try:
            # Recuperar dados do embed
            embed = interaction.message.embeds[0]
            user_id = int(embed.footer.text.split("ID: ")[1])
            albion_nick = embed.fields[0].value
            
            # Buscar config
            config = await self.bot.db.fetchrow_query(
                "SELECT * FROM server_config WHERE guild_id = $1", interaction.guild_id
            )
            
            if not config:
                await interaction.followup.send("❌ Configuração perdida.", ephemeral=True)
                return

            member = interaction.guild.get_member(user_id)
            if not member:
                await interaction.followup.send("❌ Usuário saiu do servidor.", ephemeral=True)
                return

            # Atualizar Cargos
            try:
                recruit_role = interaction.guild.get_role(config['recruit_role_id'])
                member_role = interaction.guild.get_role(config['member_role_id'])
                
                if recruit_role: await member.remove_roles(recruit_role)
                if member_role: await member.add_roles(member_role)
                
                # Atualizar Nick: [TAG] Nickname
                tag = config['guild_tag'] or "GUILD"
                new_nick = f"[{tag}] {albion_nick}"
                await member.edit(nick=new_nick[:32])
                
                await interaction.followup.send(f"✅ {member.mention} aprovado com sucesso! Nick alterado para `{new_nick}`.")
                
                # Desabilitar view
                for item in self.children: item.disabled = True
                await interaction.message.edit(view=self)
                
            except discord.Forbidden:
                await interaction.followup.send("❌ Sem permissão para alterar cargos/nick. Verifique a hierarquia de cargos.", ephemeral=True)

        except Exception as e:
            logger.error(f"Erro na aprovação: {e}")
            await interaction.followup.send("❌ Erro interno.", ephemeral=True)

    @discord.ui.button(label="Rejeitar", style=discord.ButtonStyle.red, custom_id="approval:reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("❌ Rejeitado.", ephemeral=True)
        # Futuro: Implementar log de rejeição

class RecrutamentoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Registrar view persistente no startup
        self.bot.add_view(ApprovalView(bot))

    @app_commands.command(name="registrar", description="Registrar-se na guilda")
    async def registrar(self, interaction: discord.Interaction, nickname: str):
        await interaction.response.defer(ephemeral=True)
        
        # 1. Verificar Config e Modo
        config = await self.bot.db.fetchrow_query(
            "SELECT * FROM server_config WHERE guild_id = $1", interaction.guild_id
        )
        
        if not config:
            await interaction.followup.send("❌ Bot não configurado. Use `/auto_setup`.")
            return
            
        if config['server_type'] not in ['GUILD', 'HYBRID']:
            await interaction.followup.send("⚠️ Comando desativado neste modo de servidor.")
            return

        if not config['approval_channel_id']:
            await interaction.followup.send("❌ Canal de aprovação não configurado.")
            return

        # 2. Buscar na API
        player = await self.bot.albion.search_player(nickname)
        if not player:
            await interaction.followup.send(f"❌ Jogador `{nickname}` não encontrado no Albion.")
            return

        # 3. Verificar Requisitos
        pve = player.get('LifetimeStatistics', {}).get('PvE', {}).get('Total', 0)
        pvp = player.get('KillFame', 0)
        min_pve = config['min_fame_pve'] or 0
        min_pvp = config['min_fame_pvp'] or 0
        
        status = "✅ Atende" if (pve >= min_pve and pvp >= min_pvp) else "⚠️ Não atende (Análise Manual)"
        
        # 4. Enviar para Aprovação
        channel = interaction.guild.get_channel(config['approval_channel_id'])
        if channel:
            embed = discord.Embed(title="Solicitação de Registro", color=discord.Color.blue())
            embed.add_field(name="Nick", value=player['Name'])
            embed.add_field(name="Guilda Atual", value=player.get('GuildName', 'Nenhuma'))
            embed.add_field(name="Fama", value=f"PvE: {pve:,} | PvP: {pvp:,}")
            embed.add_field(name="Status", value=status)
            embed.set_footer(text=f"ID: {interaction.user.id}")
            
            await channel.send(embed=embed, view=ApprovalView(self.bot))
            await interaction.followup.send("✅ Solicitação enviada para aprovação!")
        else:
            await interaction.followup.send("❌ Canal de aprovação inacessível.")

async def setup(bot):
    await bot.add_cog(RecrutamentoCog(bot))