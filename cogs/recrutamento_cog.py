import discord
from discord.ext import commands, tasks
from discord import app_commands
import database as db
import random
import string
import logging

# --- Função de Log (Auxiliar) ---
async def log_to_channel(bot, guild_id, message, color=None):
    """Envia uma mensagem de log para o canal de logs configurado."""
    try:
        config_data = await db.get_config(guild_id)
        if not config_data or not config_data.get('canal_logs_id'):
            print(f"Log falhou: Canal de logs não configurado para {guild_id}")
            return

        log_channel = bot.get_channel(config_data['canal_logs_id'])
        if log_channel:
            if color:
                embed = discord.Embed(description=message, color=color)
                await log_channel.send(embed=embed)
            else:
                await log_channel.send(message)
    except Exception as e:
        print(f"Erro ao enviar log para o canal: {e}")

# --- Função de Gerar Código (Auxiliar) ---
def gerar_codigo(tamanho=6):
    caracteres = string.ascii_uppercase + string.digits
    return ''.join(random.choice(caracteres) for _ in range(tamanho))

class RecrutamentoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.verificacao_automatica.start() # Inicia o loop de registo

    # --- Comando /registrar (com filtro) ---
    @app_commands.command(name="registrar", description="Inicia o seu processo de registo na guilda.")
    @app_commands.describe(nick="O seu nick exato no Albion Online.")
    async def registrar(self, interaction: discord.Interaction, nick: str):
        config_data = await db.get_config(interaction.guild.id)
        
        # 1. Verifica se o setup está completo
        if not all([
            config_data, config_data.get('canal_registo_id'),
            config_data.get('guild_name'), config_data.get('role_id'),
            config_data.get('fame_total') is not None, # Permite 0
            config_data.get('fame_pvp') is not None  # Permite 0
        ]):
            return await interaction.response.send_message(
                "O bot ainda não foi totalmente configurado por um admin.", ephemeral=True
            )
        
        # 2. Verifica se está no canal certo
        if interaction.channel.id != config_data['canal_registo_id']:
            canal_correto = interaction.guild.get_channel(config_data['canal_registo_id'])
            return await interaction.response.send_message(
                f"Por favor, use este comando no canal {canal_correto.mention}.", ephemeral=True
            )

        await interaction.response.defer(ephemeral=True) # Pensa...
        
        # 3. API Check (Filtro)
        player_info = await self.bot.albion_client.get_player_info(
            await self.bot.albion_client.search_player(nick)
        )

        if not player_info:
            await log_to_channel(self.bot, interaction.guild.id, f"⚠️ Tentativa de registo falhou: Nick `{nick}` não encontrado (Utilizador: {interaction.user.mention}).")
            await interaction.followup.send(
                f"Não encontrei o jogador **{nick}**. Verifique o nome (maiúsculas/minúsculas) e tente novamente."
            )
            return

        # 4. Verificação de Requisitos
        total_fame = player_info.get('TotalFame', 0)
        kill_fame = player_info.get('KillFame', 0)
        
        req_total_fame = config_data.get('fame_total', 0)
        req_kill_fame = config_data.get('fame_pvp', 0)

        if total_fame < req_total_fame or kill_fame < req_kill_fame:
            # Falhou no filtro
            log_msg = (
                f"❌ **Filtro Falhou**\n"
                f"Utilizador: {interaction.user.mention} (`{nick}`)\n"
                f"Fama Total: `{total_fame:,}` (Req: `{req_total_fame:,}`)\n"
                f"Fama PvP: `{kill_fame:,}` (Req: `{req_kill_fame:,}`)"
            )
            await log_to_channel(self.bot, interaction.guild.id, log_msg, discord.Color.red())
            
            await interaction.followup.send(
                f"Olá, {interaction.user.mention}! Vimos que não cumpre todos os requisitos mínimos:\n\n"
                f"**Sua Fama Total:** `{total_fame:,}` (Mínimo: `{req_total_fame:,}`)\n"
                f"**Sua Fama PvP:** `{kill_fame:,}` (Mínimo: `{req_kill_fame:,}`)\n\n"
                "Continue a jogar e volte a tentar quando atingir os objetivos!"
            )
            return

        # 5. Sucesso no Filtro - Gerar código e guardar
        codigo = gerar_codigo()
        await db.add_pending_user(interaction.user.id, interaction.guild.id, nick, codigo)
        
        log_msg = (
            f"📝 **Novo Registo Aceite**\n"
            f"Utilizador: {interaction.user.mention} (`{nick}`)\n"
            f"Requisitos: OK\n"
            f"Código Gerado: `{codigo}`"
        )
        await log_to_channel(self.bot, interaction.guild.id, log_msg, discord.Color.blue())

        # 6. Enviar instruções
        embed = discord.Embed(
            title="✅ Requisitos Atingidos!",
            description=f"Parabéns, {interaction.user.mention}! O seu registo para **{nick}** foi aceite. Siga os passos finais:",
            color=discord.Color.green()
        )
        embed.add_field(name="Passo 1: No Albion", value=(
            f"1. Aplique para: **{config_data['guild_name']}**\n"
            f"2. Cole na sua 'Bio' o código: **`{codigo}`**"
        ), inline=False)
        embed.add_field(name="Passo 2: Aguardar", value=(
            "É tudo! O bot irá verificar automaticamente. "
            "Quando for aceite E o código estiver na bio, será promovido."
        ), inline=False)
        
        await interaction.followup.send(embed=embed)

    # --- Loop de Verificação (Registo) ---
    @tasks.loop(minutes=3) # Corre a cada 3 minutos
    async def verificacao_automatica(self):
        pending_list = await db.get_pending_users()
        if not pending_list:
            logging.info("[Loop de Registo] Nenhum utilizador para verificar.")
            return

        logging.info(f"[Loop de Registo] A verificar {len(pending_list)} utilizadores...")
        
        for user_data in pending_list:
            user_id = user_data['discord_id']
            server_id = user_data['server_id']
            albion_nick = user_data['albion_nick']
            codigo_esperado = user_data['verification_code']
            
            config_data = await db.get_config(server_id)
            guild = self.bot.get_guild(server_id)
            
            if not guild or not config_data:
                logging.warning(f"Servidor {server_id} ou config não encontrados. A remover user {user_id}.")
                await db.remove_guild_member(user_id) # Limpa DB
                continue
                
            membro = guild.get_member(user_id)
            if not membro:
                logging.warning(f"Utilizador {user_id} saiu do servidor {guild.name}. A remover.")
                await db.remove_guild_member(user_id) # Limpa DB
                continue
            
            if not all([config_data.get('guild_name'), config_data.get('role_id')]):
                logging.error(f"Configuração incompleta para o servidor {guild.name}. A ignorar.")
                continue

            # API Check
            player_info = await self.bot.albion_client.get_player_info(
                await self.bot.albion_client.search_player(albion_nick)
            )
            
            if not player_info:
                logging.warning(f"[Loop de Registo] Falha ao obter info de {albion_nick}.")
                continue
                
            player_bio = player_info.get('About', '')
            player_guild = player_info.get('GuildName', '')

            bio_ok = codigo_esperado in player_bio
            guild_ok = player_guild.lower() == config_data['guild_name'].lower()

            if bio_ok and guild_ok:
                # SUCESSO!
                logging.info(f"SUCESSO: {membro.name} ({albion_nick}) verificado.")
                try:
                    cargo = guild.get_role(config_data['role_id'])
                    if not cargo:
                        await log_to_channel(self.bot, guild.id, f"❌ ERRO ADMIN: Cargo ID `{config_data['role_id']}` não encontrado.", discord.Color.dark_red())
                        continue
                        
                    await membro.edit(nick=albion_nick)
                    await membro.add_roles(cargo)
                    
                    await log_to_channel(self.bot, guild.id,
                        f"✅ **Verificado!** {membro.mention} (`{albion_nick}`) foi promovido e recebeu o cargo {cargo.mention}.",
                        discord.Color.green()
                    )
                    
                    # Atualiza o status na DB de 'pending' para 'verified'
                    await db.set_user_verified(user_id)

                except discord.Forbidden:
                    await log_to_channel(self.bot, guild.id, f"❌ ERRO ADMIN: Não tenho permissão para dar o cargo ou mudar o nick de {membro.mention}. (Verifique a hierarquia de cargos).", discord.Color.dark_red())
                except Exception as e:
                    logging.error(f"Erro ao promover {membro.name}: {e}")
            else:
                logging.info(f"[Loop de Registo] {membro.name} ({albion_nick}) pendente (Bio: {bio_ok}, Guilda: {guild_ok})")

    @verificacao_automatica.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready() # Espera o bot estar 100% ligado

async def setup(bot):
    await bot.add_cog(RecrutamentoCog(bot))