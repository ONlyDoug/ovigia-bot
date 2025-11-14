import discord
from discord.ext import commands, tasks
import database as db
import logging
from cogs.recrutamento_cog import log_to_channel # Reutilizamos a função de log

class SyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.limpeza_automatica.start()

    # --- Loop de Limpeza (Sincronização) (ATUALIZADO) ---
    @tasks.loop(minutes=30)
    async def limpeza_automatica(self):
        verified_list = await self.bot.db_manager.execute_query("SELECT * FROM guild_members WHERE status = 'verified'", fetch="all")
        if not verified_list:
            logging.info("[Loop de Limpeza] Nenhum membro verificado para sincronizar.")
            return

        logging.info(f"[Loop de Limpeza] A sincronizar {len(verified_list)} membros...")

        for user_data in verified_list:
            user_id = user_data['discord_id']
            server_id = user_data['server_id']
            albion_nick = user_data['albion_nick']
            
            config_data = await self.bot.db_manager.execute_query("SELECT * FROM server_config WHERE server_id = $1", server_id, fetch="one")
            guild = self.bot.get_guild(server_id)
            
            if not guild or not config_data:
                await self.bot.db_manager.execute_query("DELETE FROM guild_members WHERE discord_id = $1", user_id)
                continue
            membro = guild.get_member(user_id)
            if not membro:
                await self.bot.db_manager.execute_query("DELETE FROM guild_members WHERE discord_id = $1", user_id)
                continue
            
            modo = config_data.get('mode', 'guild')
            target_name = config_data.get('alliance_name') if modo == 'alliance' else config_data.get('guild_name')
            
            if not target_name: # Se nem guilda nem aliança estiverem definidos
                continue

            # API Check
            player_info = await self.bot.albion_client.get_player_info(await self.bot.albion_client.search_player(albion_nick))
            
            player_tag = ""
            if player_info:
                player_tag = player_info.get('AllianceName', '') if modo == 'alliance' else player_info.get('GuildName', '')

            # A Lógica de Expulsão (Agora verifica Guilda ou Aliança)
            if not player_info or player_tag.lower() != target_name.lower():
                logging.info(f"REMOÇÃO: {membro.name} ({albion_nick}) não está mais na {modo} '{target_name}'. Expulsando.")
                
                try:
                    await log_to_channel(self.bot, guild.id,
                        f"🔄 **Sincronização:** {membro.mention} (`{albion_nick}`) não foi encontrado na {modo} **{target_name}**.\n"
                        f"A remover cargos e expulsar do Discord.",
                        discord.Color.orange()
                    )
                    
                    await self.bot.db_manager.execute_query("INSERT INTO recruitment_log (server_id, discord_id, albion_nick, action) VALUES ($1, $2, $3, 'kicked_auto')", guild.id, membro.id, albion_nick)
                    
                    await membro.kick(reason=f"Sincronização: Não faz mais parte da {modo} {target_name} no Albion.")
                    
                    await self.bot.db_manager.execute_query("DELETE FROM guild_members WHERE discord_id = $1", user_id)

                except discord.Forbidden:
                    await log_to_channel(self.bot, guild.id, f"❌ ERRO ADMIN: Tentei expulsar {membro.mention}, mas não tenho permissão de 'Expulsar Membros'.", discord.Color.dark_red())
                except Exception as e:
                    logging.error(f"Erro ao expulsar {membro.name}: {e}")
            else:
                logging.info(f"[Loop de Limpeza] {membro.name} ({albion_nick}) ainda está na {modo}.")

    @limpeza_automatica.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot):
    await bot.add_cog(SyncCog(bot))