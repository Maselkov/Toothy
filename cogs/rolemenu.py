import datetime
import logging
import re
import discord
from discord import app_commands
from discord.ext import commands
from enum import Enum

log = logging.getLogger(__name__)


class Mode(Enum):
    single = 1
    multiple = 2
    single_removable = 3


MODE_CHOICES = [
    app_commands.Choice(
        name="Allow multiple roles to be selected and deselected freely",
        value=2),
    app_commands.Choice(
        name="Only allow one option to be selected at the time", value=1),
    app_commands.Choice(
        name="Only allow one option to be selected at the time, but make "
        "it removable too",
        value=3)
]


class RoleSelectError(Exception):
    pass


class EmojiNotFoundError(RoleSelectError):

    def __init__(self, menu, emoji):
        self.menu = menu
        self.emoji = emoji


class RoleNotFoundError(RoleSelectError):
    pass


class NoChannelError(Exception):
    pass


class RoleMenuDropdown(discord.ui.Select):

    def __init__(self,
                 options=[],
                 placeholder=None,
                 min_values=1,
                 max_values=1):
        super().__init__(options=options,
                         placeholder=placeholder,
                         custom_id="rolemenu:dropdown",
                         min_values=min_values,
                         max_values=max_values)

    # @classmethod
    # def create(cls, options, placeholder):
    #     super().__init__(cls, placeholder=placeholder, options=options)

    async def callback(self, interaction: discord.Interaction):
        menu: Menu = await self.view.cog.get_menu_by_message(
            interaction.message)
        if not menu:
            return await interaction.response.send_message(
                "This menu no longer appears to be valid.", ephemeral=True)
        if not interaction.guild.me.guild_permissions.manage_roles:
            await interaction.response.send_message(
                "I don't have the `Manage Roles` permission.", ephemeral=True)
        values = [int(value) for value in self.values]
        roles = [
            role_info["role"] for role_info in menu.roles
            if role_info["role"].id in values
        ]
        roles = [
            role for role in roles if role < interaction.guild.me.top_role
        ]
        roles_to_add = []
        roles_to_remove = []
        # await interaction.response.defer(ephemeral=True)
        print(menu.mode)
        if menu.mode == Mode.multiple:
            for role in roles:
                if role in interaction.user.roles:
                    pass
                    # roles_to_remove.append(role)
                else:
                    roles_to_add.append(role)
        else:
            if not roles:
                await interaction.response.send_message(
                    "You need to select a role", ephemeral=True)
            role = roles[0]
            if role in interaction.user.roles:
                return await interaction.response.send_message(
                    "You already have this role", ephemeral=True)
            roles_to_add.append(role)
            roles_to_remove = [
                role_doc["role"] for role_doc in menu.roles
                if role_doc["role"] in interaction.user.roles
                and role_doc["role"] != role
            ]
        if not roles_to_add and not roles_to_remove:
            return await interaction.response.send_message(
                "No change in roles.", ephemeral=True)
        embed = discord.Embed(title=menu.name, color=menu.color)
        if roles_to_add:
            await interaction.user.add_roles(*roles_to_add,
                                             reason=f"Role menu - {menu.name}")
            embed.add_field(name="Added",
                            value=", ".join(
                                [role.mention for role in roles_to_add]),
                            inline=True)
        if roles_to_remove:
            await interaction.user.remove_roles(
                *roles_to_remove, reason=f"Role menu - {menu.name}")
            embed.add_field(name="Removed",
                            value=", ".join(
                                [role.mention for role in roles_to_remove]),
                            inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class RoleMenuSelectRolesForRemovalDropdown(discord.ui.Select):

    def __init__(self, user, menu, options) -> None:
        self.user = user
        self.menu = menu
        super().__init__(placeholder="Select roles that you want to remove...",
                         options=options,
                         min_values=1,
                         max_values=len(options))

    async def callback(self, interaction: discord.Interaction):
        options = [int(value) for value in self.values]
        roles = [
            role["role"] for role in self.menu.roles
            if role["role"].id in options
        ]
        roles = [
            role for role in roles
            if role.position < interaction.guild.me.top_role.position
            and role in interaction.user.roles
        ]
        if not interaction.guild.me.guild_permissions.manage_roles:
            return await interaction.response.edit_message(
                content="I don't have permission to manage roles.")

        embed = discord.Embed(title=self.menu.name, color=self.menu.color)
        if roles:
            await interaction.user.remove_roles(
                *roles,
                reason=f"Role menu - {self.menu.name} - Remove select roles")
            embed.add_field(name="Removed",
                            value=", ".join([role.mention for role in roles]),
                            inline=False)
        await interaction.response.edit_message(content=None,
                                                embed=embed,
                                                view=None)


class RoleMenuSelectRolesForRemovalView(discord.ui.View):

    def __init__(self, user, menu, options):
        super().__init__(timeout=180)
        self.user = user

        self.add_item(
            RoleMenuSelectRolesForRemovalDropdown(user, menu, options))
        self.out = None

    # async def on_timeout(self) -> None:
    #     await self.out.message.dele

    async def interaction_check(self, interaction) -> bool:
        return interaction.user == self.user


class RoleMenuView(discord.ui.View):

    def __init__(self, cog, items=[]):
        super().__init__(timeout=None)
        self.cog = cog
        if items:
            for item in items:
                self.add_item(item)
        else:
            self.add_item(RoleMenuDropdown())

    @classmethod
    def from_menu(cls, menu):
        options = []
        for role_doc in menu.roles:
            role = role_doc["role"]
            options.append(
                discord.SelectOption(label="@" + role.name,
                                     value=role.id,
                                     emoji=role_doc["emoji"],
                                     description=role_doc["description"]))
        min_values = 1
        max_values = len(menu.roles) if menu.mode == Mode.multiple else 1
        return cls(cog=menu.cog,
                   items=[
                       RoleMenuDropdown(options,
                                        placeholder=menu.placeholder,
                                        min_values=min_values,
                                        max_values=max_values)
                   ])

    async def change_roles(self, interaction, to_add, to_remove):
        pass

    @discord.ui.button(custom_id="rolemenu:clear_roles",
                       label="Clear all roles",
                       emoji="🗑",
                       row=4)
    async def clear_roles(self, interaction: discord.Interaction,
                          button: discord.Button):
        menu = await self.cog.get_menu_by_message(interaction.message)
        if not menu:
            await interaction.response.send_message(
                "This menu no longer appears to be valid.", ephemeral=True)
        if not interaction.guild.me.guild_permissions.manage_roles:
            return await interaction.response.send_message(
                "I don't have permission to manage roles.", ephemeral=True)
        highest_role = interaction.guild.me.top_role
        to_remove = list(role_doc["role"] for role_doc in menu.roles
                         if role_doc["role"] in interaction.user.roles
                         and role_doc["role"] < highest_role)
        if not to_remove:
            return await interaction.response.send_message(
                "You don't have any roles to remove.", ephemeral=True)
        embed = discord.Embed(title=menu.name, color=menu.color)
        embed.set_footer(text="Cleared all roles")
        if to_remove:
            await interaction.user.remove_roles(
                *to_remove, reason=f"Role menu - {menu.name} - clear roles")
            embed.add_field(name="Removed",
                            value=", ".join(
                                [role.mention for role in to_remove]),
                            inline=False)
            await interaction.response.send_message(embed=embed,
                                                    ephemeral=True)
        else:
            return await interaction.response.send_message(
                "No change in roles.", ephemeral=True)

    @discord.ui.button(custom_id="rolemenu:remove_selected_roles",
                       label="Remove specific roles...",
                       emoji="📃",
                       row=4)
    async def remove_selected_roles(self, interaction: discord.Interaction,
                                    button: discord.Button):
        menu = await self.cog.get_menu_by_message(interaction.message)
        if not menu:
            await interaction.response.send_message(
                "This menu no longer appears to be valid.", ephemeral=True)
        if not interaction.guild.me.guild_permissions.manage_roles:
            return await interaction.response.send_message(
                "I don't have permission to manage roles.", ephemeral=True)
        options = []
        current = []
        for role in menu.roles:
            if role["role"] in interaction.user.roles:
                current.append(role["role"].mention)
                options.append(
                    discord.SelectOption(label="@" + role["role"].name,
                                         value=str(role["role"].id),
                                         emoji=role["emoji"],
                                         description=role["description"]))
        if not options:
            return await interaction.response.send_message(
                "You don't have any roles to remove.", ephemeral=True)
        embed = discord.Embed(color=menu.color,
                              title="Current roles",
                              description=", ".join(current))
        view = RoleMenuSelectRolesForRemovalView(interaction.user, menu,
                                                 options)
        view.out = await interaction.response.send_message(embed=embed,
                                                           view=view,
                                                           ephemeral=True)


class Menu():

    def __init__(self, cog, guild, doc) -> None:
        self.id = doc["_id"]
        self.cog = cog
        self.name = doc["name"]
        self.mode = Mode(doc["mode"])
        self.message_id = doc["message_id"]
        self.channel = guild.get_channel(doc["channel_id"])
        self.guild = guild
        self.color = doc["color"]
        self.roles = []
        self.placeholder = doc["placeholder"]
        self.description = doc["description"]

        for role_doc in doc["roles"]:
            role = guild.get_role(role_doc["id"])
            if not role:
                continue
            emoji = role_doc["emoji"]
            if emoji:
                if isinstance(emoji, int):
                    emoji = cog.bot.get_emoji(emoji)
            self.roles.append({
                "role": role,
                "emoji": emoji,
                "description": role_doc["description"]
            })
        self.roles = sorted(self.roles, key=lambda x: x["role"].name)

    async def update(self):
        if not self.channel:
            raise NoChannelError
        if not self.roles:
            if self.message_id:
                try:
                    message = await self.channel.fetch_message(self.message_id)
                    await message.delete()
                except discord.HTTPException:
                    pass
                finally:
                    return
        message = None
        if self.message_id:
            try:
                message = await self.channel.fetch_message(self.message_id)
            except discord.HTTPException:
                pass
        view = RoleMenuView.from_menu(self)
        if self.mode == Mode.single or self.mode == Mode.single_removable:
            for item in view.children:
                if isinstance(item, discord.ui.Button):
                    if (item.label == "Clear all roles"
                            and self.mode == Mode.single_removable):
                        item.label = "Remove role"
                        continue
                    view.remove_item(item)
        embed = discord.Embed(title=self.name,
                              description=self.description,
                              color=self.color)
        if not message:
            message = await self.channel.send(embed=embed, view=view)
            self.message_id = message.id
            await self.cog.db.update_one(
                {"_id": self.id}, {"$set": {
                    "message_id": self.message_id
                }})
        else:
            await message.edit(embed=embed, view=view)


class RoleMenu(commands.Cog):
    """Role selection menu"""

    rolemenu_group = app_commands.Group(
        name="rolemenu",
        description="Rolemenu management commands",
        guild_only=True)

    def __init__(self, bot):
        self.bot: commands.AutoShardedBot = bot
        self.listening_to = {}
        self.db = bot.database.db.rolemenus

    async def rolemenu_name_autocomplete(self,
                                         interaction: discord.Interaction,
                                         current: str):
        sanitized = re.escape(current)
        pattern = re.compile(sanitized + ".*", re.IGNORECASE)
        query = {"name": pattern, "guild_id": interaction.guild.id}
        cursor = self.db.find(query).limit(25)
        # todo unique per channel
        return [
            app_commands.Choice(name=doc["name"], value=doc["name"])
            async for doc in cursor
        ]

    async def role_remove_autocomplete(self, interaction: discord.Interaction,
                                       current: str):
        if not interaction.namespace.name:
            return []
        query = {
            "name": interaction.namespace.name,
            "guild_id": interaction.guild.id
        }
        menu_doc = await self.db.find_one(query)
        menu = Menu(self, interaction.guild, menu_doc)
        options = []
        current = current.lstrip("@")
        for role in menu.roles:
            if current in role["role"].name.lower():
                options.append(
                    app_commands.Choice(name=role["role"].name,
                                        value=str(role["role"].id)))
        return options

    async def update_all_menus(self):
        cursor = self.db.find({"guild_id": {"$exists": True}})
        async for doc in cursor:
            try:
                menu = Menu(self, self.bot.get_guild(doc["guild_id"]), doc)
                await menu.update()
            except Exception:
                pass

    async def cog_load(self) -> None:
        await self.update_all_menus()
        self.bot.add_view(RoleMenuView(self))

    async def cog_unload(self) -> None:
        pass

    async def get_menu_by_message(self, message):
        doc = await self.db.find_one({"message_id": message.id})
        return Menu(self, message.guild, doc) if doc else None

    @app_commands.checks.has_permissions(manage_roles=True, manage_guild=True)
    @app_commands.default_permissions(manage_roles=True, manage_guild=True)
    @app_commands.describe(
        name="A unique name identifying this role menu.",
        channel="The channel in which the menu will be posted in",
        mode="Rolemenu's behavior",
        color="Color that the menu "
        "will have. Standard hex format, e.g. #ffffff",
        placeholder="The text that will appear in the "
        "dropdown. E.g. \"Select the roles you want\"")
    @app_commands.choices(mode=MODE_CHOICES)
    @rolemenu_group.command(name="create")
    async def rolemenu_create(self,
                              interaction: discord.Interaction,
                              name: str,
                              channel: discord.TextChannel,
                              mode: int,
                              color: str,
                              placeholder: str,
                              description: str = None):
        """Role selection menu setup"""
        doc = await self.db.find_one({
            "guild_id": interaction.guild.id,
            "name": name
        })
        if doc:
            return await interaction.response.send_message(
                "Role menu with that name exists.", ephemeral=True)
        if channel.guild != interaction.guild:
            return await interaction.response.send_message(
                "This channel is not in this server.")
        if not channel.permissions_for(interaction.guild.me).send_messages:
            return await interaction.response.send_message(
                "I don't have permission to send messages in this channel.")
        try:
            color = discord.Color.from_str(color)
        except ValueError:
            return await interaction.response.send_message("Invalid color.")
        await self.db.insert_one({
            "message_id": None,
            "name": name,
            "mode": mode,
            "channel_id": channel.id,
            "roles": [],
            "guild_id": interaction.guild.id,
            "color": color.value,
            "placeholder": placeholder,
            "description": description
        })
        await interaction.response.send_message(
            "Role menu created. It is currently empty, however, and "
            "you'll need to add roles with `/rolemenu role add.`",
            ephemeral=True)

    @app_commands.checks.has_permissions(manage_roles=True, manage_guild=True)
    @app_commands.default_permissions(manage_roles=True, manage_guild=True)
    @app_commands.autocomplete(name=rolemenu_name_autocomplete)
    @app_commands.describe(
        name="A unique name identifying this role menu.",
        channel="The channel in which the menu will be posted in",
        mode="Rolemenu's behavior",
        color="Color that the menu "
        "will have. Standard hex format, e.g. #ffffff",
        placeholder="The text that will appear in the "
        "dropdown. E.g. \"Select the roles you want\"")
    @app_commands.choices(mode=MODE_CHOICES)
    @rolemenu_group.command(name="edit")
    async def rolemenu_edit(self,
                            interaction: discord.Interaction,
                            name: str,
                            channel: discord.TextChannel = None,
                            mode: int = None,
                            color: str = None,
                            placeholder: str = None,
                            description: str = None):
        """Edit any parameter of a previosuly created rolemenu"""
        doc = await self.db.find_one({
            "guild_id": interaction.guild.id,
            "name": name
        })
        if not doc:
            return await interaction.response.send_message(
                "Role menu with that name does not exist.", ephemeral=True)
        modifications = {}
        if channel:
            if channel.guild != interaction.guild:
                return await interaction.response.send_message(
                    "This channel is not in this server.")
            if not channel.permissions_for(interaction.guild.me).send_messages:
                return await interaction.response.send_message(
                    "I don't have permission to send messages in this channel."
                )
            modifications["channel_id"] = channel.id
        if mode:
            modifications["mode"] = mode
        if color:
            try:
                color = discord.Color.from_str(color)
            except ValueError:
                return await interaction.response.send_message("Invalid color."
                                                               )
            modifications["color"] = color.value
        if placeholder:
            modifications["placeholder"] = placeholder
        if description:
            modifications["description"] = description
        await interaction.response.defer(ephemeral=True)
        await self.db.update_one({"_id": doc["_id"]}, {"$set": modifications})
        doc = await self.db.find_one({"_id": doc["_id"]})
        await interaction.followup.send("added thing")
        menu = Menu(self, interaction.guild, doc)
        await menu.update()
        await interaction.followup.send("Role menu updated.", ephemeral=True)

    @app_commands.checks.has_permissions(manage_roles=True, manage_guild=True)
    @app_commands.default_permissions(manage_roles=True, manage_guild=True)
    @app_commands.autocomplete(name=rolemenu_name_autocomplete)
    @app_commands.describe(name="A unique name identifying this role menu.")
    @rolemenu_group.command(name="delete")
    async def rolemenu_delete(self, interaction: discord.Interaction,
                              name: str):
        """Delete a previously created rolemenu"""
        doc = await self.db.find_one({
            "guild_id": interaction.guild.id,
            "name": name
        })
        if not doc:
            return await interaction.response.send_message(
                "Role menu with that name does not exist.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        await self.db.delete_one({"_id": doc["_id"]})
        await interaction.followup.send("Role menu removed.", ephemeral=True)

    role_manipulation_group = app_commands.Group(
        name="role",
        parent=rolemenu_group,
        description="Adding and removing roles from the role menu")

    @app_commands.checks.has_permissions(manage_roles=True, manage_guild=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True,
                                             add_reactions=True)
    @app_commands.default_permissions(manage_roles=True, manage_guild=True)
    @app_commands.describe(
        name="A unique name identifying this role menu.",
        role="A role to add to the role menu",
        emoji="The emoji that will be displayed next to the role. Make sure "
        "the bot has access to the server the emoji is on.",
        description="The description that will appear under the role")
    @app_commands.autocomplete(name=rolemenu_name_autocomplete)
    @role_manipulation_group.command(name="add")
    async def rolemenu_add_role(self,
                                interaction: discord.Interaction,
                                name: str,
                                role: discord.Role,
                                emoji: str = None,
                                description: str = None):
        """Role selection menu setup"""
        doc = await self.db.find_one({
            "guild_id": interaction.guild.id,
            "name": name
        })
        if not doc:
            return await interaction.response.send_message(
                "No role menu with that name exists.", ephemeral=True)
        for role_doc in doc["roles"]:
            if role_doc["id"] == role.id:
                return await interaction.followup.send(
                    "Role is already in the menu.", ephemeral=True)
        if len(doc["roles"]) >= 25:
            return await interaction.response.send_message(
                "This role menu is full.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        if role.guild != interaction.guild:
            return await interaction.response.send_message(
                "This role is not in this server.")
        if emoji:
            if emoji.startswith("<") and emoji.endswith(">"):
                try:
                    emoji = int(emoji[1:-1].split(":")[2])
                except ValueError:
                    return await interaction.followup.send("Invalid emoji.")
            else:
                try:
                    message = await interaction.original_message()
                    await message.add_reaction(emoji)
                except discord.HTTPException:
                    return await interaction.followup.send("Invalid emoji.")
        await self.db.update_one({"_id": doc["_id"]}, {
            "$push": {
                "roles": {
                    "description": description,
                    "id": role.id,
                    "emoji": emoji,
                    "date_added": datetime.datetime.now(datetime.datetime.u)
                }
            }
        })
        doc = await self.db.find_one({"_id": doc["_id"]})
        await interaction.followup.send(f"Added {role.mention} to the menu.")
        menu = Menu(self, interaction.guild, doc)
        await menu.update()

    @app_commands.checks.has_permissions(manage_roles=True, manage_guild=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True,
                                             add_reactions=True)
    @app_commands.default_permissions(manage_roles=True, manage_guild=True)
    @app_commands.describe(name="A unique name identifying this role menu.")
    @app_commands.autocomplete(name=rolemenu_name_autocomplete,
                               role=role_remove_autocomplete)
    @role_manipulation_group.command(name="remove")
    async def rolemenu_remove_role(self, interaction: discord.Interaction,
                                   name: str, role: str):
        """Remove a role from a menu"""
        try:
            role_id = int(role)
        except ValueError:
            return await interaction.response.send_message(
                "The role provided "
                "is not valid. Make sure that you either select one from the "
                "options that the autocomplete provides, or that you "
                "provide the role's ID",
                ephemeral=True)
        doc = await self.db.find_one({
            "guild_id": interaction.guild.id,
            "name": name
        })
        if not doc:
            return await interaction.response.send_message(
                "No role menu with that name exists.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        for role_doc in doc["roles"]:
            if role_doc["id"] == role_id:
                break
        else:
            return await interaction.followup.send(
                "Role not found in that menu")
        await self.db.update_one({"_id": doc["_id"]},
                                 {"$pull": {
                                     "roles": role_doc
                                 }})
        doc = await self.db.find_one({"_id": doc["_id"]})
        await interaction.followup.send("Role removed from the menu.")
        menu = Menu(self, interaction.guild, doc)
        await menu.update()

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        guild = after.guild
        if before.name == after.name:
            return
        # Find all role menus that have the role
        cursor = self.db.find({"guild_id": guild.id, "roles.id": after.id})
        async for doc in cursor:
            menu = Menu(self, guild, doc)
            await menu.update()


async def setup(bot):
    cog = RoleMenu(bot)
    await bot.add_cog(cog)
