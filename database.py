import config
from supabase import create_client, Client

supabase: Client = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)
print("[Base de Dados] Cliente Supabase inicializado.")

# --- FUNÇÃO DE INICIALIZAÇÃO ---
async def initialize_database():
    """Chama a função RPC no Supabase para criar/verificar as tabelas."""
    print("[Base de Dados] A verificar/criar tabelas no Supabase...")
    try:
        # Chama a função 'setup_database' que criámos no Supabase
        await supabase.rpc('setup_database', {}).execute()
        print("[Base de Dados] Tabelas verificadas/criadas com sucesso.")
    except Exception as e:
        print(f"Erro CRÍTICO ao inicializar a base de dados: {e}")
        print("Certifique-se de que executou o script SQL para criar a função 'setup_database' no Supabase.")
        raise e # Propaga o erro

# --- Funções de Configuração ---
async def get_config(server_id):
    """Busca a configuração de um servidor específico."""
    try:
        response = await supabase.table("server_config").select("*").eq("server_id", server_id).execute()
        if response.data:
            return response.data[0]
        return None
    except Exception as e:
        print(f"Erro ao buscar config do Supabase: {e}")
        return None

async def update_config(server_id, data):
    """Cria ou atualiza a configuração de um servidor."""
    try:
        await supabase.table("server_config").upsert({
            "server_id": server_id,
            **data
        }).execute()
        print(f"[Supabase] Config do servidor {server_id} atualizada.")
    except Exception as e:
        print(f"Erro ao atualizar config: {e}")

# --- Funções de Membros (para a tabela 'guild_members') ---

async def add_pending_user(discord_id, server_id, albion_nick, code):
    """Adiciona ou atualiza um utilizador com status 'pending'."""
    try:
        await supabase.table("guild_members").upsert({
            "discord_id": discord_id,
            "server_id": server_id,
            "albion_nick": albion_nick,
            "verification_code": code,
            "status": "pending" # Garante que é 'pending'
        }).execute()
    except Exception as e:
        print(f"Erro ao adicionar user pendente: {e}")

async def set_user_verified(discord_id):
    """Atualiza o status do utilizador para 'verified' e limpa o código."""
    try:
        await supabase.table("guild_members").update({
            "status": "verified",
            "verification_code": None
        }).eq("discord_id", discord_id).execute()
    except Exception as e:
        print(f"Erro ao definir user como verificado: {e}")

async def remove_guild_member(discord_id):
    """Remove um membro da base de dados (ex: foi expulso)."""
    try:
        await supabase.table("guild_members").delete().eq("discord_id", discord_id).execute()
    except Exception as e:
        print(f"Erro ao remover membro da DB: {e}")

async def get_pending_users():
    """Retorna todos os membros com status 'pending'."""
    try:
        response = await supabase.table("guild_members").select("*").eq("status", "pending").execute()
        return response.data
    except Exception as e:
        print(f"Erro ao buscar users pendentes: {e}")
        return []

async def get_verified_users():
    """Retorna todos os membros com status 'verified'."""
    try:
        response = await supabase.table("guild_members").select("*").eq("status", "verified").execute()
        return response.data
    except Exception as e:
        print(f"Erro ao buscar users verificados: {e}")
        return []

async def get_pending_user_count():
    """Retorna o número de utilizadores pendentes."""
    try:
        response = await supabase.table("guild_members").select("discord_id", count='exact').eq("status", "pending").execute()
        return response.count
    except Exception as e:
        print(f"Erro ao contar users pendentes: {e}")
        return 0