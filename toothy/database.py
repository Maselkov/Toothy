from motor.motor_asyncio import AsyncIOMotorClient


class MongoController:
    def __init__(self, host, port, credentials):
        def mongo_uri():
            uri = "mongodb://"
            if credentials["user"] and credentials["pass"]:
                uri += "{}:{}@".format(credentials["user"],
                                       credentials["pass"])
            return uri + "{}:{}".format(host, port)

        self.credentials = credentials
        self.client = AsyncIOMotorClient(mongo_uri())
        self.db = self.client.toothy
        self.users = self.db.users
        self.guilds = self.db.guilds
        self.channels = self.db.channels
        self.configs = self.db.configs

    async def get_prefixes(self, guild):
        if guild is None:
            return None
        doc = await self.guilds.find_one({"_id": guild.id}, {"prefixes": 1})
        if not doc:
            return None
        return doc.get("prefixes")

    async def get_user(self, user, cog=None):
        """Get user. Pass a cog instance in order to return
           cog specific settings"""
        doc = await self.users.find_one({"_id": user.id})
        if doc and cog:
            try:
                cog_doc = doc["cogs"][cog.__class__.__name__]
                cog_doc.update(_id=doc["_id"])
                return cog_doc
            except KeyError:
                return None
        return doc

    async def get_guild(self, guild, cog=None):
        """Get guild. Pass a cog instance in order to return
           cog specific settings"""
        doc = await self.guilds.find_one({"_id": guild.id})
        if doc and cog:
            try:
                cog_doc = doc["cogs"][cog.__class__.__name__]
                cog_doc.update(_id=doc["_id"])
                return cog_doc
            except KeyError:
                return None
        return doc

    async def get_channel(self, channel, cog=None):
        """Get channel. Pass a cog instance in order to return
           cog specific settings"""
        doc = await self.channels.find_one({"_id": channel.id})
        if doc and cog:
            try:
                cog_doc = doc["cogs"][cog.__class__.__name__]
                cog_doc.update(_id=doc["_id"])
                return cog_doc
            except KeyError:
                return None
        return doc

    async def get_cog_config(self, cog):
        name = cog.__class__.__name__
        return await self.configs.find_one({"cog_name": name})

    async def set_user(self,
                       user,
                       settings: dict,
                       cog=None,
                       *,
                       operator="$set"):
        """Use dot notation in settings. If cog is passed, the root will be the
        cog's embedded setting document"""
        if cog:
            settings = self.dot_notation(cog, settings)
        await self.users.update_one(
            {
                "_id": user.id
            }, {operator: settings}, upsert=True)

    async def set_guild(self,
                        guild,
                        settings: dict,
                        cog=None,
                        *,
                        operator="$set"):
        """Use dot notation in settings. If cog is passed, the root will be the
        cog's embedded setting document"""
        if cog:
            settings = self.dot_notation(cog, settings)
        await self.guilds.update_one(
            {
                "_id": guild.id
            }, {operator: settings}, upsert=True)

    async def set_channel(self,
                          channel,
                          settings: dict,
                          cog=None,
                          *,
                          operator="$set"):
        """Use dot notation in settings. If cog is passed, the root will be the
        cog's embedded setting document"""
        if cog:
            settings = self.dot_notation(cog, settings)
        await self.channels.update_one(
            {
                "_id": channel.id
            }, {operator: settings}, upsert=True)

    async def set_cog_config(self, cog, settings, *, operator="$set"):
        await self.configs.update_one({
            "cog_name": cog.__class__.__name__
        }, {operator: settings})

    def get_users_cursor(self, search: dict, cog=None):
        if cog:
            search = self.dot_notation(cog, search)
        return self.users.find(search, modifiers={"$snapshot": True})

    def get_guilds_cursor(self, search: dict, cog=None):
        if cog:
            search = self.dot_notation(cog, search)
        return self.guilds.find(search, modifiers={"$snapshot": True})

    def get_channels_cursor(self, search: dict, cog=None):
        if cog:
            search = self.dot_notation(cog, search)
        return self.channels.find(search, modifiers={"$snapshot": True})

    async def setup_cog(self, cog, default_settings):
        name = cog.__class__.__name__
        doc = await self.configs.find_one({"cog_name": name})
        if not doc:
            default_settings.update(cog_name=name)
            await self.configs.insert_one(default_settings)
            return
        new_keys = 0
        for k, v in default_settings.items():
            if k not in doc:
                new_keys += 1
                doc[k] = v
        if new_keys:
            await self.configs.replace_one({"cog_name": name}, {doc})
            print("{} new settings in {}".format(new_keys, name))

    def dot_notation(self, cog, settings):
        d = {}
        for k, v in settings.items():
            d["cogs.{}.{}".format(cog.__class__.__name__, k)] = v
        return d
