import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger("AliancaCog")

class AliancaCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="aplicar_alianca", description="Aplicar para cargo de aliança")
    @app_commands.describe(nickname="Seu apelido no Albion Online")
    async def aplicar_alianca(self, interaction: discord.Interaction, nickname: str):
        await interaction.response.defer(ephemeral=True)
        
        config = await self.bot.db.fetchrow_query("SELECT * FROM server_config WHERE guild_id = $1", interaction.guild_id)
        if not config:
            await interaction.followup.send("Servidor não configurado.")
            return

        # Verificar Modo de Operação
        server_type = config.get('server_type', 'GUILD')
        if server_type not in ['ALLIANCE', 'HYBRID']:
            await interaction.followup.send(f"⚠️ Comando desativado. Este servidor está operando em modo **{server_type}** (apenas Guilda).")
            return

        # Verificar se o sistema de aliança está ativo
        if not config['alliance_tag'] or not config['ally_role_id']:
            await interaction.followup.send("O sistema de aliança não está configurado neste servidor.")
            return

        player = await self.bot.albion.search_player(nickname)
        if not player:
            await interaction.followup.send("Jogador não encontrado.")
            return

        full_player = await self.bot.albion.get_player_info(player['Id'])
        
        player_alliance_tag = full_player.get('AllianceTag', '')
        config_alliance_tag = config['alliance_tag']
        
        # Verificar se pertence à Aliança configurada
        if player_alliance_tag == config_alliance_tag:
            try:
                # Gerenciar Cargos
                ally_role_id = config['ally_role_id']
                recruit_role_id = config['recruit_role_id']
                
                ally_role = interaction.guild.get_role(ally_role_id)
                recruit_role = interaction.guild.get_role(recruit_role_id) if recruit_role_id else None
                
                if ally_role:
                    await interaction.user.add_roles(ally_role)
                
                if recruit_role:
                    await interaction.user.remove_roles(recruit_role)
                    
                # Atualizar Nickname
                guild_name = full_player.get('GuildName', '')
                new_nick = f"[{guild_name}] {player['Name']}"
                await interaction.user.edit(nick=new_nick[:32])
                
                msg = f"✅ Sucesso! Você foi verificado como membro da aliança **{config_alliance_tag}**."
                if ally_role:
                    msg += f"\n+ Cargo: {ally_role.name}"
                if recruit_role:
                    msg += f"\n- Cargo: {recruit_role.name}"
                    
                await interaction.followup.send(msg)
                
            except discord.Forbidden:
                await interaction.followup.send("⚠️ Verificado, mas falhei ao atualizar cargos/nick. Verifique minhas permissões.")
            except Exception as e:
                logger.error(f"Erro ao atualizar membro de aliança: {e}")
                await interaction.followup.send("Erro interno ao atualizar permissões.")
                
        else:
            await interaction.followup.send(f"❌ Sua guilda não faz parte da aliança **{config_alliance_tag}**.\nSua Aliança: {player_alliance_tag if player_alliance_tag else 'Nenhuma'}")

async def setup(bot):
    await bot.add_cog(AliancaCog(bot))