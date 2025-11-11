import discord
from discord.ext import commands, tasks
import logging
# Importamos a função de log do outro cog para manter o padrão
from cogs.recrutamento_cog import log_to_channel 

class SyncCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.limpeza_automatica.start() # Inicia o loop de limpeza

    # --- Loop de Limpeza (Sincronização) ---
    @tasks.loop(minutes=30) # Corre a cada 30 minutos
    async def limpeza_automatica(self):
        # 1. Obter todos os membros VERIFICADOS
        verified_list = await self.bot.db_manager.execute_query(
            "SELECT * FROM guild_members WHERE status = 'verified'", fetch="all"
        )
        
        if not verified_list:
            logging.info("[Loop de Limpeza] Nenhum membro verificado para sincronizar.")
            return

        logging.info(f"[Loop de Limpeza] A sincronizar {len(verified_list)} membros...")

        for user_data in verified_list:
            user_id = user_data['discord_id']
            server_id = user_data['server_id']
            albion_nick = user_data['albion_nick']
            
            # 2. Obter config, guild e membro
            config_data = await self.bot.db_manager.execute_query(
                "SELECT * FROM server_config WHERE server_id = $1", server_id, fetch="one"
            )
            guild = self.bot.get_guild(server_id)
            
            if not guild or not config_data:
                logging.warning(f"Servidor {server_id} ou config não encontrados. A remover user {user_id}.")
                await self.bot.db_manager.execute_query(
                    "DELETE FROM guild_members WHERE discord_id = $1", user_id
                )
                continue
                
            membro = guild.get_member(user_id)
            if not membro:
                logging.warning(f"Utilizador {user_id} (verificado) saiu do servidor {guild.name}. A remover.")
                await self.bot.db_manager.execute_query("DELETE FROM guild_members WHERE discord_id = $1", user_id)
                continue

            if not config_data.get('guild_name'):
                continue # Pula se a config estiver incompleta

            # 3. Verificar API do Albion
            player_info = await self.bot.albion_client.get_player_info(
                await self.bot.albion_client.search_player(albion_nick)
            )
            
            player_guild = ""
            if player_info:
                player_guild = player_info.get('GuildName', '')

            # 4. A Lógica de Expulsão
            # Se o jogador não foi encontrado (conta apagada?) OU
            # Se o nome da guilda dele for diferente da nossa
            if not player_info or player_guild.lower() != config_data['guild_name'].lower():
                logging.info(f"REMOÇÃO: {membro.name} ({albion_nick}) não está mais na guilda. Expulsando.")
                
                try:
                    # Envia log PRIMEIRO
                    await log_to_channel(self.bot, guild.id,
                        f"🔄 **Sincronização:** {membro.mention} (`{albion_nick}`) não foi encontrado na guilda do Albion. "
                        f"A remover cargo e expulsar do Discord.",
                        discord.Color.orange()
                    )
                    
                    # Expulsa o membro do Discord
                    # (Tenta remover o cargo primeiro, mas expulsar já resolve)
                    await membro.kick(reason="Sincronização: Não faz mais parte da guilda no Albion Online.")
                    
                    # Remove da nossa base de dados
                    await self.bot.db_manager.execute_query(
                        "DELETE FROM guild_members WHERE discord_id = $1", user_id
                    )

                except discord.Forbidden:
                    await log_to_channel(self.bot, guild.id, f"❌ ERRO ADMIN: Tentei expulsar {membro.mention}, mas não tenho permissão de 'Expulsar Membros'.", discord.Color.dark_red())
                except Exception as e:
                    logging.error(f"Erro ao expulsar {membro.name}: {e}")
            else:
                # Tudo OK, o membro continua na guilda
                logging.info(f"[Loop de Limpeza] {membro.name} ({albion_nick}) ainda está na guilda.")

    @limpeza_automatica.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready() # Espera o bot estar 100% ligado

# Obrigatório para carregar o Cog
async def setup(bot):
    await bot.add_cog(SyncCog(bot))