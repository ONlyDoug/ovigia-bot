import discord
from discord.ext import commands
from discord import app_commands
import logging
from utils.permissions import has_permission 
from cogs.recrutamento_cog import log_to_channel

class SuporteCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # --- Grupo de Comandos ---
    suporte = app_commands.Group(name="suporte", description="Comandos para a equipa de Suporte/Recrutamento.")

    @suporte.command(name="pendentes", description="Mostra todos os membros que aguardam verificação.")
    @has_permission(1) # Nível 1 (Suporte) ou superior
    async def pendentes(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        pending_list = await self.bot.db_manager.execute_query(
            "SELECT discord_id, albion_nick, created_at FROM guild_members WHERE server_id = $1 AND status = 'pending' ORDER BY created_at ASC",
            interaction.guild.id, fetch="all"
        )
        
        if not pending_list:
            return await interaction.followup.send("Não há aplicações pendentes na fila.")
            
        embed = discord.Embed(title=f"⏳ Fila de Aprovação ({len(pending_list)})", color=discord.Color.orange())
        
        descricao = ""
        for item in pending_list:
            membro = interaction.guild.get_member(item['discord_id'])
            timestamp = f"<t:{int(item['created_at'].timestamp())}:R>"
            descricao += f"• {membro.mention if membro else f'ID: {item['discord_id']}'} - `{item['albion_nick']}` (Registado {timestamp})\n"
            
        embed.description = descricao
        await interaction.followup.send(embed=embed)

            
    @suporte.command(name="rejeitar", description="Rejeita um membro pendente e remove-o da fila.")
    @has_permission(1) # Nível 1 (Suporte) ou superior
    @app_commands.describe(membro="O membro no Discord a ser rejeitado.", motivo="O motivo da rejeição (será enviado por DM).")
    async def rejeitar(self, interaction: discord.Interaction, membro: discord.Member, motivo: str):
        await interaction.response.defer(ephemeral=True)
        
        resultado = await self.bot.db_manager.execute_query(
            "DELETE FROM guild_members WHERE discord_id = $1 AND server_id = $2 RETURNING albion_nick",
            membro.id, interaction.guild.id, fetch="one"
        )
        
        if not resultado:
            return await interaction.followup.send(f"❌ O membro {membro.mention} não estava na fila de verificação.")
            
        nick_albion = resultado['albion_nick']
        
        await log_to_channel(self.bot, interaction.guild.id,
            f"❌ **Registo Rejeitado Manualmente**\n"
            f"**Staff:** {interaction.user.mention}\n"
            f"**Membro:** {membro.mention} (`{nick_albion}`)\n"
            f"**Motivo:** {motivo}",
            discord.Color.red()
        )
        
        await self.bot.db_manager.execute_query(
            "INSERT INTO recruitment_log (server_id, discord_id, albion_nick, action, admin_id) VALUES ($1, $2, $3, 'rejected_manual', $4)",
            interaction.guild.id, membro.id, nick_albion, interaction.user.id
        )
        
        try:
            await membro.send(f"Olá! O seu registo para a guilda foi revisto por um staff e **rejeitado**. Motivo: *{motivo}*")
        except discord.Forbidden:
            pass 
            
        await interaction.followup.send(f"✅ O registo de {membro.mention} (`{nick_albion}`) foi rejeitado e removido da fila.")

async def setup(bot):
    await bot.add_cog(SuporteCog(bot))