import asyncio
import datetime
import itertools
import logging
import math
import random

import discord
import youtube_dl
import youtube_dl.utils
from discord.ext import commands
from discord_slash import cog_ext
from discord_slash.model import SlashCommandOptionType

log = logging.getLogger(__name__)

ytdl_format_options = {
    'format': 'bestaudio/best',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

ffmpeg_options = {'before_options': '-nostdin', 'options': '-vn'}

ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class NoJoinError(Exception):
    pass


class VoiceState:
    def __init__(self, ctx, volume, repeat=False):
        self.current = None
        self.player = None
        self.guild = ctx.guild
        self.voice = None
        self.bot = ctx.bot
        self.cog = ctx.cog
        self.next = asyncio.Event()
        self.queue = asyncio.Queue()
        self.skip_votes = set()
        self.volume = volume
        self.repeat = repeat
        self.time_started_playing = None
        self.audio_player = self.bot.loop.create_task(self.audio_player_task())

    def is_playing(self):
        return bool(self.current)

    def update_volume(self, value):
        self.volume = value
        if self.is_playing():
            self.player.volume = self.volume

    @property
    def time_elapsed(self):
        if not self.time_started_playing:
            return 0
        return (datetime.datetime.now() -
                self.time_started_playing).total_seconds()

    async def audio_player_task(self):
        def next_song(_):
            self.bot.loop.call_soon_threadsafe(self.next.set)

        while True:
            self.next.clear()
            try:
                self.current = await asyncio.wait_for(self.queue.get(),
                                                      timeout=300,
                                                      loop=self.bot.loop)
            except asyncio.TimeoutError:
                return await self.cog.stop_playing(self.guild)
            if self.repeat:
                await self.queue.put(self.current)
            self.player = await YTDLSource.from_url(self.current.url)
            self.player.volume = self.volume
            self.time_started_playing = datetime.datetime.now()
            self.current.voice_client.play(self.player, after=next_song)
            await self.next.wait()
            self.skip_votes.clear()
            self.player.cleanup()
            self.now_playing = None


class VoiceEntry:
    def __init__(self, ctx, url):
        self.bot = ctx.bot
        self.requester = ctx.author
        self.url = url
        self.voice_client = ctx.voice_client
        self.title = None
        self.description = None
        self.upload_date = None
        self.duration = None
        self.uploader = None
        self.uploader_url = None
        self.video_url = None
        self.view_count = None
        self.likes = None
        self.dislikes = None
        self.thumbnail = None

    async def get_info(self):
        data = await self.bot.loop.run_in_executor(
            None, lambda: ytdl.extract_info(self.url, download=False))
        if "entries" in data:
            data = data["entries"][0]
        self.title = data["title"]
        self.description = data.get("description")
        date = data.get("upload_date")
        if date:
            self.upload_date = datetime.datetime.strptime(
                date, '%Y%m%d').strftime('%y-%m-%d')
        else:
            self.upload_date = None
        self.duration = data.get("duration", 0)
        self.uploader = data["uploader"]
        self.uploader_url = data.get("uploader_url")
        self.video_url = data["webpage_url"]
        self.view_count = data.get("view_count")
        self.likes = data.get("like_count")
        self.dislikes = data.get("dislike_count")
        self.thumbnail = data["thumbnail"]


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.1):
        super().__init__(source, volume)

        self.data = data

        self.title = data.get('title')
        self.url = data.get('url')

    @classmethod
    async def from_url(cls, url, *, loop=None):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(
            None, lambda: ytdl.extract_info(url, download=False))
        if 'entries' in data:
            data = data['entries'][0]
        filename = data["url"]
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options),
                   data=data)


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.states = {}

    def __unload(self):
        for state in self.states.values():
            self.bot.loop.create_task(self.stop_playing(state.guild))

    @cog_ext.cog_slash(options=[{
        "name": "url",
        "description": "URL or search term",
        "type": SlashCommandOptionType.STRING,
        "required": True
    }])
    async def play(self, ctx, url: str):
        """Play a song. Can be YouTube or many different sites"""
        await self.enqueue(ctx, url)

    @cog_ext.cog_slash(name="queue")
    async def show_queue(self, ctx):
        """Show the current song queue"""
        if not self.is_connected(ctx):
            return await ctx.send("I am not currently playing anything")
        state = await self.get_state(ctx)
        if not state.is_playing():
            return await ctx.send("Not playing")
        await ctx.send(embed=self.queue_embed(state))

    @cog_ext.cog_slash(options=[{
        "name": "volume",
        "description": "Value between 0 and 100",
        "type": SlashCommandOptionType.INTEGER,
        "required": True
    }])
    async def volume(self, ctx, volume: int):
        """Changes the player's volume"""
        if not 0 <= volume <= 100:
            return await ctx.send("Value must be between 0 and 100")
        guild = ctx.guild
        volume = volume / 100
        await self.bot.database.set(guild, {"volume": volume}, self)
        if guild.id in self.states:
            self.states[guild.id].update_volume(volume)
        await ctx.send("Volume is now {:.0%}".format(volume))

    @cog_ext.cog_slash()
    async def repeat(self, ctx):
        """Toggle repeat mode"""
        guild = ctx.guild
        doc = await self.bot.database.get(guild, self)
        repeat = not doc.get("repeat", False)
        await self.bot.database.set(guild, {"repeat": repeat}, self)
        if guild.id in self.states:
            self.states[guild.id].repeat = repeat
        if repeat:
            await ctx.send("Repeat is now enabled")
        else:
            await ctx.send("Repeat is now disabled")

    @cog_ext.cog_slash()
    async def stop(self, ctx):
        """Stops and disconnects the bot from voice"""
        if not self.is_connected(ctx):
            return await ctx.send("I am not connected to a voice channel.")
        vc = ctx.me.voice.channel
        if not ctx.author.voice or not ctx.author.voice.channel == vc:
            return await ctx.send("You're not connected to my voice channel.")
        if len(vc.members) == 2 or vc.permissions_for(ctx.author).move_members:
            await ctx.send("Stopping playback...")
            return await self.stop_playing(ctx.guild)
        return await ctx.send(
            "There are other people in the channel, vote to skip instead")

    @cog_ext.cog_slash()
    async def skip(self, ctx):
        """Skip the current song"""
        if not self.is_connected(ctx):
            return await ctx.send("Not connected to a voice channel.")
        state = await self.get_state(ctx)
        if not state.is_playing():
            return await ctx.send("I am not currently playing anything.")
        user = ctx.author
        if not user.voice or not user.voice.channel == ctx.me.voice.channel:
            return await ctx.send("You're not connected to voice.")
        if user.permissions_in(ctx.me.voice.channel).mute_members:
            await ctx.send("Force skipping.")
            return ctx.voice_client.stop()
        if user.id in state.skip_votes:
            return await ctx.send(
                "{.mention}, you've already voted.".format(user))
        state.skip_votes.add(user.id)
        total_skip_votes = len(state.skip_votes)
        voice_members = len(ctx.me.voice.channel.members) - 1
        votes_needed = math.ceil(voice_members / 2)
        if voice_members % 2 == 0:
            votes_needed += 1
        if total_skip_votes >= votes_needed:
            await ctx.send("Vote skip passed!")
            return ctx.voice_client.stop()
        suffix = "s" if len(state.skip_votes) > 1 else ""
        await ctx.send("Voted to skip {}.\n{} vote{}, {} needed".format(
            state.current.title, len(state.skip_votes), suffix, votes_needed))

    @cog_ext.cog_slash()
    async def song(self, ctx):
        """Info about currently playing song"""
        state = self.states.get(ctx.guild.id)
        if not state or not state.current:
            return await ctx.send("Not playing")
        embed = self.song_embed(state)
        await ctx.send(embed=embed)

    # @commands.guild_only()
    # @commands.group(name="playlist")
    # async def playlist(self, ctx):
    #     """Manage playlists"""
    #     if ctx.invoked_subcommand is None:
    #         await self.bot.send_cmd_help(ctx)

    # @playlist.command(name="add")
    # async def playlist_add(self, ctx, name, url):
    #     """Add a new playlist"""
    #     guild = ctx.guild
    #     if "playlist?list=" not in url.lower():
    #         await ctx.send("Error, playlist URL is not a valid youtube URL")
    #         return
    #     doc = await self.bot.database.get(guild, self)
    #     current_playlists = doc.get("playlists")
    #     if current_playlists:
    #         for pl in current_playlists:
    #             if url == pl["url"]:
    #                 return await ctx.send(
    #                     f"Playlist already exists in this server with the name {pl['name']}."
    #                 )
    #             if name == pl["name"]:
    #                 return await ctx.send("Playlist name already exists")
    #     playlist = {
    #         "name": name,
    #         "url": url.replace("https://www.youtube.com/playlist?list=", "")
    #     }
    #     await self.bot.database.set(guild, {"playlists": playlist},
    #                                 self,
    #                                 operator="$push")
    #     await ctx.send("Playlist created with name {0}".format(name) +
    #                    " and playlist URL {0}".format(url))

    # @playlist.command(name="remove")
    # async def playlist_remove(self, ctx, name):
    #     """Remove a playlist"""
    #     guild = ctx.guild
    #     doc = await self.bot.database.get(guild, self)
    #     current_playlists = doc.get("playlists")
    #     playlist = self.find_playlist(name, current_playlists)
    #     if not playlist:
    #         return await ctx.send("That playlist does not exist.")
    #     await self.bot.database.set(guild, {"playlists": playlist},
    #                                 self,
    #                                 operator="$pull")
    #     await ctx.send("Playlist has been removed!")

    # @playlist.command(name="show")
    # async def playlist_show(self, ctx):
    #     """Show all currently existing playlists."""
    #     guild = ctx.guild
    #     doc = await self.bot.database.get(guild, self)
    #     current_playlists = doc.get("playlists")
    #     if not current_playlists:
    #         return await ctx.send("There are no playlists.")
    #     playlist_names = []
    #     for playlist in current_playlists:
    #         playlist_names.append(playlist.get('name'))
    #     pl = ", ".join(playlist_names)
    #     await ctx.send("The current playlists are: {0}".format(pl))

    # @playlist.command(name="play")
    # async def playlist_play(self, ctx, name):
    #     """Queue a playlist"""
    #     guild = ctx.guild
    #     if not name:
    #         await self.bot.send_cmd_help(ctx)
    #         return
    #     doc = await self.bot.database.get(guild, self)
    #     playlists = doc.get("playlists")
    #     playlist = self.find_playlist(name, playlists)
    #     await self.enqueue(
    #         ctx, "https://www.youtube.com/playlist?list=" + playlist["url"])

    # @playlist.command(name="mix")
    # async def playlist_mix(self, ctx, name):
    #     """Queue a playlist and shuffles it"""
    #     guild = ctx.guild
    #     doc = await self.bot.database.get(guild, self)
    #     playlists = doc.get("playlists")
    #     playlist = self.find_playlist(name, playlists)
    #     await self.enqueue(ctx,
    #                        "https://www.youtube.com/playlist?list=" +
    #                        playlist["url"],
    #                        shuffle=True)

    # def find_playlist(self, name, playlists):
    #     for playlist in playlists:
    #         if playlist["name"].lower() == name.lower():
    #             return playlist
    #     return None

    async def get_state(self, ctx):
        guild = ctx.guild
        state = self.states.get(guild.id)
        if not state:
            doc = await self.bot.database.get(guild, self)
            volume = doc.get("volume", 1)
            repeat = doc.get("repeat", False)
            state = VoiceState(ctx, volume, repeat)
            self.states[guild.id] = state
        return state

    async def enqueue(self, ctx, url, *, shuffle=False):
        try:
            await self.join(ctx)
        except NoJoinError:
            return
        state = await self.get_state(ctx)

        async def process_entry(song_url):
            entry = VoiceEntry(ctx, song_url)
            try:
                await entry.get_info()
            except youtube_dl.utils.DownloadError:
                return
            await state.queue.put(entry)
            return entry

        if self.is_playlist(url):
            data = await self.bot.loop.run_in_executor(
                None,
                lambda: ytdl.extract_info(url, download=False, process=False))
            songs = list(data["entries"])
            if shuffle:
                random.shuffle(songs)
            await ctx.send("Added {} songs to the queue".format(len(songs)))
            for song in songs:
                await process_entry("https://youtube.com/watch?v={}".format(
                    song["url"]))
            return
        entry = await process_entry(url)
        if entry:
            return await ctx.send("Queued: {} by {}".format(
                entry.title, entry.uploader))
        await ctx.send("Encountered an error while trying to enqueue your song"
                       )

    async def join(self, ctx):
        user = ctx.author
        if not user.voice or not user.voice.channel:
            await ctx.send("You are not in a voice channel")
            raise NoJoinError
        channel = user.voice.channel
        if ctx.voice_client:
            if ctx.me.voice.channel == channel:
                return
            if not user.guild_permissions.move_members:
                await ctx.send("I am already in a voice channel!")
                raise NoJoinError
            else:
                if channel:
                    await ctx.send(
                        "{.name} moved me to another voice channel!".format(
                            user))
                    return await ctx.voice_client.move_to(channel)
        await channel.connect()

    def is_connected(self, ctx):
        return ctx.voice_client and ctx.voice_client.is_connected()

    def is_playlist(self, url):
        return "http" in url and "playlist" in url

    async def stop_playing(self, guild):
        vc = guild.voice_client
        if guild.voice_client:
            await vc.disconnect()
        state = self.states.get(guild.id)
        if not state:
            return
        state.audio_player.cancel()
        del self.states[guild.id]

    def queue_embed(self, state):
        def song_line(entry, counter=0):
            requester = entry.requester.nick or entry.requester.name
            prefix = "{}. ".format(counter) if counter else ""
            line = prefix + "{} by {} ({})".format(entry.title, entry.uploader,
                                                   requester)
            return line

        queue = list(itertools.islice(state.queue._queue, 0, 5))
        upcoming = []
        counter = 1
        for entry in queue:
            upcoming.append(song_line(entry, counter))
            counter += 1
        embed = discord.Embed(title="🎵 Queue 🎵", color=self.bot.color)
        if state.is_playing():
            embed.add_field(name="Current",
                            value=song_line(state.current),
                            inline=False)
        if not queue:
            embed.add_field(name="Upcoming",
                            value="No songs are in the queue",
                            inline=False)
        else:
            embed.add_field(name="Upcoming",
                            value="\n".join(upcoming),
                            inline=False)
        embed.set_footer(
            text="{} songs are in the queue.".format(len(state.queue._queue)))
        return embed

    def song_embed(self, state):
        def format_number(number):
            magnitude = 0
            while abs(number) >= 1000:
                magnitude += 1
                number /= 1000.0
            suffix = ['', 'K', 'M', 'G', 'T', 'P'][magnitude]
            if number != int(number):
                number = "{:.2f}".format(number)
            else:
                number = str(number)
            return number + suffix

        def diagram(percentage):
            output = ""
            bar_count = round(percentage / 5)
            for emoji in range(bar_count):
                output += "▓"
            tab_count = 20 - bar_count
            for tab in range(tab_count):
                output += "░"

            return output + ""

        entry = state.current
        embed = discord.Embed(title=entry.title,
                              url=entry.video_url,
                              color=0xFE0000)
        uploader_url = entry.uploader_url or discord.Embed.Empty
        embed.set_author(name=entry.uploader, url=uploader_url)
        embed.set_thumbnail(url=entry.thumbnail)
        if entry.description:
            if len(entry.description) > 500:
                entry.description = entry.description[:500] + "..."
            embed.add_field(name="Video Description",
                            value=entry.description,
                            inline=False)
        if entry.likes is not None and entry.dislikes is not None:
            likes = format_number(entry.likes)
            dislikes = format_number(entry.dislikes)
            embed.add_field(name="Likes | Dislikes",
                            value="\\👍 {} | {} \\👎".format(likes, dislikes),
                            inline=True)
        if entry.view_count is not None:
            view_count = format_number(entry.view_count)
            embed.add_field(name="View Count",
                            value="\\📺 {}".format(view_count),
                            inline=True)
        if entry.duration:
            duration_percentage = (state.time_elapsed / entry.duration) * 100
            graph = diagram(duration_percentage)
            embed.add_field(name="Duration",
                            value="|" + graph + "|" +
                            "  {0[0]}:{0[1]:02d}/{1[0]}:{1[1]:02d}".format(
                                divmod(math.floor(state.time_elapsed), 60),
                                divmod(entry.duration, 60)),
                            inline=False)
        return embed


def setup(bot):
    cog = Music(bot)
    bot.add_cog(cog)
