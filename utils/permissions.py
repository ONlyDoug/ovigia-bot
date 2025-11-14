import discord
from discord.ext import commands
from discord import app_commands

async def check_permission_level(interaction: discord.Interaction, level: int) -> bool:
    """Verifica se o utilizador tem o nível de permissão necessário."""
    user = interaction.user
    bot = interaction.client

    # Admin do Servidor tem permissão máxima
    if user.guild_permissions.administrator:
        return True
    
    author_roles_ids = {str(role.id) for role in user.roles}
    db_manager = bot.db_manager

    # Verifica o nível do utilizador e todos os níveis acima
    for i in range(level, 5): # Nível 4 é o mais alto
        perm_key = f'perm_nivel_{i}'
        
        config_data = await db_manager.execute_query(
            "SELECT valor FROM server_config_permissoes WHERE server_id = $1 AND chave = $2",
            interaction.guild.id, perm_key, fetch="one"
        )
        
        if config_data and config_data.get('valor'):
            allowed_role_ids = set(config_data.get('valor').split(','))
            # Se qualquer um dos cargos do autor estiver na lista de permissões, retorna True
            if not author_roles_ids.isdisjoint(allowed_role_ids):
                return True
    
    # Se falhar
    await interaction.response.send_message("Você não tem permissão para usar este comando.", ephemeral=True, delete_after=10)
    return False

# Decorador para Comandos de Barra (/)
def has_permission(level: int):
    async def predicate(interaction: discord.Interaction) -> bool:
        return await check_permission_level(interaction, level)
    return app_commands.check(predicate)

# Verificador de permissões para Comandos de Prefixo (!)
def check_admin_prefix():
    async def predicate(ctx):
        if ctx.author.guild_permissions.administrator: return True
        # Verifica Nível 4 (Admin Total) para o !sync
        config_data = await ctx.bot.db_manager.execute_query("SELECT valor FROM server_config_permissoes WHERE server_id = $1 AND chave = 'perm_nivel_4'", ctx.guild.id, fetch="one")
        if not config_data or not config_data.get('valor'): return False
        
        allowed_role_ids = set(config_data.get('valor').split(','))
        author_roles_ids = {str(role.id) for role in ctx.author.roles}
        
        if not author_roles_ids.isdisjoint(allowed_role_ids):
            return True
            
        return False
    return commands.check(predicate)