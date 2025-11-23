import discord
from discord.ext import commands
from discord import app_commands
import logging

logger = logging.getLogger("AliancaCog")

class AliancaCog(commands.Cog):
    """Cog para sistema de aliança"""
    
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(
        name="aplicar_alianca",
        description="Aplicar para cargo de aliança"
    )
    @app_commands.describe(nickname="Seu nickname no Albion Online")
    async def aplicar_alianca(self, interaction: discord.Interaction, nickname: str):
        """Comando para aplicar para cargo de aliança"""
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
        if server_type not in ['ALLIANCE', 'HYBRID']:
            await interaction.followup.send(
                f"⚠️ Este comando está desativado. Servidor em modo **{server_type}**."
            )
            return
        
        # Verificar se sistema de aliança está configurado
        if not config['alliance_tag'] or not config['ally_role_id']:
            await interaction.followup.send(
                "❌ Sistema de aliança não configurado neste servidor."
            )
            return
        
        # Buscar jogador na API
        player = await self.bot.albion.search_player(nickname)
        if not player:
            await interaction.followup.send(
                f"❌ Jogador '{nickname}' não encontrado no Albion Online."
            )
            return
        
        # Buscar informações completas do jogador
        full_player = await self.bot.albion.get_player_info(player['Id'])
        
        player_alliance = full_player.get('AllianceTag', '')
        config_alliance = config['alliance_tag']
        
        # Verificar se pertence à aliança
        if player_alliance != config_alliance:
            await interaction.followup.send(
                f"❌ Sua guilda não faz parte da aliança **{config_alliance}**.\n"
                f"Sua aliança: {player_alliance if player_alliance else 'Nenhuma'}"
            )
            return
        
        # Jogador pertence à aliança - atualizar cargos
        try:
            ally_role = interaction.guild.get_role(config['ally_role_id'])
            recruit_role_id = config.get('recruit_role_id')
            recruit_role = interaction.guild.get_role(recruit_role_id) if recruit_role_id else None
            
            roles_changed = []
            
            # Adicionar cargo de aliado
            if ally_role:
                await interaction.user.add_roles(ally_role)
                roles_changed.append(f"+ {ally_role.name}")
            
            # Remover cargo de recruta se existir
            if recruit_role and recruit_role in interaction.user.roles:
                await interaction.user.remove_roles(recruit_role)
                roles_changed.append(f"- {recruit_role.name}")
            
            # Atualizar nickname
            guild_name = full_player.get('GuildName', '')
            new_nick = f"[{guild_name}] {player['Name']}"
            await interaction.user.edit(nick=new_nick[:32])
            
            # Mensagem de sucesso
            msg = f"✅ **Verificado como membro da aliança {config_alliance}!**\n\n"
            if roles_changed:
                msg += "**Cargos atualizados:**\n" + "\n".join(roles_changed)
            
            await interaction.followup.send(msg)
            logger.info(f"Aliança aplicada para {interaction.user} ({nickname})")
            
        except discord.Forbidden:
            await interaction.followup.send(
                "⚠️ Você foi verificado, mas não tenho permissões para atualizar cargos/nickname.\n"
                "Peça a um admin para verificar minhas permissões."
            )
        except Exception as e:
            logger.error(f"Erro ao aplicar aliança: {e}")
            await interaction.followup.send(
                f"❌ Erro ao atualizar: {e}"
            )

async def setup(bot):
    await bot.add_cog(AliancaCog(bot))