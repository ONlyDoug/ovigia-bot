import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger("AliancaCog")

class AliancaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="aplicar_alianca", description="Receber cargo de aliado")
    async def aplicar_alianca(self, interaction: discord.Interaction, nickname: str):
        await interaction.response.defer(ephemeral=True)
        
        # 1. Verificar Config
        config = await self.bot.db.fetchrow_query(
            "SELECT * FROM server_config WHERE guild_id = $1", interaction.guild_id
        )
        
        if not config:
            await interaction.followup.send("❌ Bot não configurado.")
            return
            
        if config['server_type'] not in ['ALLIANCE', 'HYBRID']:
            await interaction.followup.send("⚠️ Comando desativado neste modo de servidor.")
            return

        if not config['alliance_tag'] or not config['ally_role_id']:
            await interaction.followup.send("❌ Configuração de aliança incompleta.")
            return

        # 2. Buscar API
        player = await self.bot.albion.search_player(nickname)
        if not player:
            await interaction.followup.send("❌ Jogador não encontrado.")
            return
            
        full_player = await self.bot.albion.get_player_info(player['Id'])
        player_ally = full_player.get('AllianceTag', '')
        server_ally = config['alliance_tag']
        
        # 3. Verificar Aliança
        if player_ally == server_ally:
            try:
                ally_role = interaction.guild.get_role(config['ally_role_id'])
                recruit_role = interaction.guild.get_role(config['recruit_role_id']) if config['recruit_role_id'] else None
                
                if ally_role: await interaction.user.add_roles(ally_role)
                if recruit_role: await interaction.user.remove_roles(recruit_role)
                
                # Atualizar Nick
                guild_name = full_player.get('GuildName', '')
                new_nick = f"[{guild_name}] {player['Name']}"
                await interaction.user.edit(nick=new_nick[:32])
                
                await interaction.followup.send(f"✅ Verificado! Bem-vindo à aliança **{server_ally}**.")
                
            except discord.Forbidden:
                await interaction.followup.send("⚠️ Verificado, mas sem permissão para alterar cargos/nick.")
        else:
            await interaction.followup.send(f"❌ Sua guilda não está na aliança **{server_ally}**.")

async def setup(bot):
    await bot.add_cog(AliancaCog(bot))