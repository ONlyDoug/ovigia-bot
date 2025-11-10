import discord
from discord.ext import tasks
import aiohttp  
import json     
import random   
import string   
import os # <- NOVO: Importa o módulo "Operating System"

# --- Configuração ---
# O bot vai agora ler as "Environment Variables" da Discloud
# Estas são as chaves que terá de configurar na Discloud:
try:
    TOKEN = os.environ.get("DISCORD_TOKEN")
    CANAL_ID = int(os.environ.get("CANAL_REGISTO_ID"))
    SERVER_ID = int(os.environ.get("SERVER_GUILD_ID"))
    GUILD_NAME = os.environ.get("GUILD_NAME")
    ROLE_ID = int(os.environ.get("CARGO_MEMBRO_ID"))
    
    # Verifica se alguma variável está em falta
    if not all([TOKEN, CANAL_ID, SERVER_ID, GUILD_NAME, ROLE_ID]):
        print("ERRO CRÍTICO: Uma ou mais variáveis de ambiente não foram definidas!")
        print("Verifique na Discloud se as seguintes variáveis existem:")
        print("DISCORD_TOKEN, CANAL_REGISTO_ID, SERVER_GUILD_ID, GUILD_NAME, CARGO_MEMBRO_ID")
        exit()

except ValueError:
    print("ERRO: O ID do canal, servidor ou cargo não é um número. Verifique as variáveis de ambiente.")
    exit()
except Exception as e:
    print(f"Erro ao carregar configuração: {e}")
    exit()


# --- API Endpoints do Albion ---
API_SEARCH_URL = "https://gameinfo.albiononline.com/api/gameinfo/search?q="
API_PLAYER_INFO_URL = "https://gameinfo.albiononline.com/api/gameinfo/players/"

# --- Variáveis Globais ---
pending_verification = {}

# --- Configuração dos Intents do Bot ---
intents = discord.Intents.default()
intents.message_content = True 
intents.members = True         
intents.guilds = True          

client = discord.Client(intents=intents)

# --- Funções Auxiliares (Sem alteração) ---

def gerar_codigo(tamanho=6):
    caracteres = string.ascii_uppercase + string.digits
    return ''.join(random.choice(caracteres) for _ in range(tamanho))

async def buscar_id_jogador_albion(nome_jogador):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_SEARCH_URL}{nome_jogador}") as resp:
            if resp.status != 200:
                print(f"API Search falhou: {resp.status}")
                return None
            data = await resp.json()
            for player in data.get('players', []):
                if player.get('Name').lower() == nome_jogador.lower():
                    return player.get('Id')
            return None

async def buscar_info_jogador_albion(player_id):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{API_PLAYER_INFO_URL}{player_id}") as resp:
            if resp.status != 200:
                print(f"API Info falhou: {resp.status}")
                return None
            return await resp.json()

# --- TAREFA AUTOMÁTICA EM SEGUNDO PLANO ---

@tasks.loop(minutes=3)
async def verificacao_automatica():
    print(f"[Loop] A iniciar verificação automática para {len(pending_verification)} utilizadores pendentes...")

    utilizadores_pendentes = list(pending_verification.keys())
    
    if not utilizadores_pendentes:
        print("[Loop] Nenhum utilizador para verificar.")
        return

    discord_server = client.get_guild(SERVER_ID)
    if not discord_server:
        print(f"ERRO: Não consigo encontrar o servidor com ID {SERVER_ID}")
        return
        
    canal_registo = client.get_channel(CANAL_ID)
    if not canal_registo:
        print(f"ERRO: Não consigo encontrar o canal com ID {CANAL_ID}")
        return

    cargo_membro = discord_server.get_role(ROLE_ID) 
    if not cargo_membro:
        print(f"ERRO: Não consigo encontrar o cargo com ID '{ROLE_ID}'")
        return

    for user_id in utilizadores_pendentes:
        if user_id not in pending_verification:
            continue
            
        albion_nick, codigo_esperado = pending_verification[user_id]
        
        membro = discord_server.get_member(user_id)
        if not membro:
            print(f"[Loop] O utilizador {user_id} saiu do servidor. A remover.")
            del pending_verification[user_id]
            continue
            
        player_id = await buscar_id_jogador_albion(albion_nick)
        if not player_id:
            print(f"[Loop] Nick {albion_nick} (de {membro.name}) não encontrado na API.")
            continue
            
        player_info = await buscar_info_jogador_albion(player_id)
        if not player_info:
            print(f"[Loop] Falha ao obter info de {albion_nick}.")
            continue
            
        player_bio = player_info.get('About', '')
        player_guild = player_info.get('GuildName', '')

        bio_ok = codigo_esperado in player_bio
        guild_ok = player_guild.lower() == GUILD_NAME.lower()

        if bio_ok and guild_ok:
            print(f"[Loop] SUCESSO! {membro.name} ({albion_nick}) foi verificado.")
            try:
                await membro.edit(nick=albion_nick)
                await membro.add_roles(cargo_membro)
                
                await canal_registo.send(
                    f"**Bem-vindo à {GUILD_NAME}, {membro.mention}!** \n\n"
                    f"A sua conta **{albion_nick}** foi verificada automaticamente com sucesso.\n"
                    f"O seu nick foi atualizado e recebeu o cargo **{cargo_membro.name}**."
                )
                
                del pending_verification[user_id]

            except discord.Forbidden:
                await canal_registo.send(
                    f"Atenção, {membro.mention} foi verificado, mas não tenho permissão para alterar nicks ou cargos. "
                    "(Erro de hierarquia de cargos para o Admin)"
                )
            except Exception as e:
                print(f"Erro ao processar {membro.name}: {e}")
        else:
            print(f"[Loop] {membro.name} ({albion_nick}) ainda pendente (Bio: {bio_ok}, Guilda: {guild_ok})")

# --- Eventos do Bot ---

@client.event
async def on_ready():
    print(f'Bot ligado como {client.user}')
    print(f'A recrutar para: {GUILD_NAME}')
    print(f'A ouvir no canal ID: {CANAL_ID}')
    print(f'A atribuir cargo ID: {ROLE_ID}')
    verificacao_automatica.start()

@client.event
async def on_message(message):
    
    if message.author == client.user or message.channel.id != CANAL_ID:
        return

    if message.content.startswith('!registrar'):
        try:
            albion_nick = message.content.split(' ', 1)[1]
        except IndexError:
            await message.channel.send(
                f"Olá {message.author.mention}! "
                f"Formato incorreto. Use: `!registrar <OSeuNickNoAlbion>`"
            )
            return

        codigo = gerar_codigo()
        pending_verification[message.author.id] = (albion_nick, codigo)
        
        print(f"Novo registo: {message.author.name} -> {albion_nick} (Código: {codigo})")
        
        embed = discord.Embed(
            title="Registo Automático de Recrutamento",
            description=(
                f"Olá, {message.author.mention}! O seu pedido para **{albion_nick}** foi recebido.\n"
                "O nosso sistema é **automático**. Siga os passos abaixo e aguarde."
            ),
            color=discord.Color.green()
        )
        embed.add_field(
            name="Passo 1: Ações no Albion Online",
            value=(
                f"**1. Aplicar à Guilda:**\n"
                f"   - Aplique para a guilda: **{GUILD_NAME}**.\n\n"
                f"**2. Editar a sua 'Bio':**\n"
                f"   - No perfil do seu personagem, edite a 'Descrição' (About) e cole o seguinte código:\n"
                f"   **`{codigo}`**"
            ),
            inline=False
        )
        embed.add_field(
            name="Passo 2: Aguardar",
            value=(
                "**É tudo!** Não precisa de digitar mais nenhum comando.\n\n"
                "O bot vai verificar a sua conta a cada poucos minutos. "
                "Assim que for **aceite na guilda** e o **código estiver na sua bio**, "
                "será automaticamente promovido e receberá uma mensagem de boas-vindas aqui."
            ),
            inline=False
        )
        embed.set_footer(text="Se mudar de nick no Albion, use !registrar novamente.")
        
        await message.channel.send(embed=embed)

# --- Ligar o Bot ---
print("A ligar o bot...")
client.run(TOKEN)