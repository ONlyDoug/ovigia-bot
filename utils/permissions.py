import discord

def is_admin():
    def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator
    return discord.app_commands.check(predicate)

def is_officer():
    # Placeholder for officer check - currently checks for admin or specific role if needed
    # You can expand this to check for specific role IDs from the database
    def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.manage_guild
    return discord.app_commands.check(predicate)