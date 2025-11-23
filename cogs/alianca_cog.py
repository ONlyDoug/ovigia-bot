import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger("AliancaCog")

class AliancaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        full_player = await self.bot.albion.get_player_info(player['Id'])
        
        player_alliance_tag = full_player.get('AllianceTag', '')
        config_alliance_tag = config['alliance_tag']
        
        if player_alliance_tag == config_alliance_tag:
            # Dar Cargo de Aliado
            ally_role_id = config['ally_role_id']
            role = interaction.guild.get_role(ally_role_id)
            if role:
                try:
                    await interaction.user.add_roles(role)
                    
                    # Verificar se é da guilda principal
                    if full_player.get('GuildName') == config['guild_tag']: # Assuming guild_tag is name or we check tag
                         # Lógica para membro da guilda principal se necessário
                         pass
                         
                    await interaction.followup.send(f"Verificado! Cargo {role.name} adicionado.")
                    
                    # Atualizar Nick
                    new_nick = f"[{player.get('GuildName', '')}] {player['Name']}"
                    await interaction.user.edit(nick=new_nick[:32])
                    
                except discord.Forbidden:
                    await interaction.followup.send("Sem permissões para adicionar cargo.")
            else:
                await interaction.followup.send("Cargo de aliado não encontrado no servidor.")
        else:
            await interaction.followup.send(f"Sua tag de aliança ({player_alliance_tag}) não corresponde à do servidor ({config_alliance_tag}).")

async def setup(bot):
    await bot.add_cog(AliancaCog(bot))