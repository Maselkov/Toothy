import asyncio
import collections
import datetime
import itertools
import json
import logging
import os
import random
import time
import urllib.parse
from pathlib import Path

import aiocache
import async_timeout
import discord
import sponsorblock
import wavelink
from discord import ButtonStyle, InteractionResponse, app_commands
from discord.ext import commands, tasks
from wavelink.ext import spotify
from yt_dlp import YoutubeDL
from yt_dlp.utils import YoutubeDLError

log = logging.getLogger(__name__)

LYRICS_URL = "https://some-random-api.ml/lyrics?title={}"
EMBED_COLORS = {"youtube": discord.Color(0xFF0000)}

PROGRESS_BAR_PART_1 = "<:light:993605820304609280>"  # red line
PROGRESS_BAR_PART_2 = "<:middle:993605813685977340>"  # red dot
PROGRESS_BAR_PART_3 = "<:dark:993605816827531285>"  # grey line

PROGRESS_BAR_START = "<:start:993605815225299004>"  # start
PROGRESS_BAR_END = "<:end:993605818115170379>"  # end
BASE_PATH = Path.cwd() / "music"

with open("settings/music-config.json", encoding="utf-8") as f:
    CONFIG = json.load(f)


async def download_track(track: wavelink.Track):
    if not track.uri.startswith("https://www.youtube.com/watch"):
        raise ValueError
    save_path = BASE_PATH / "cache" / (track.identifier + ".ogg")
    if save_path.exists():
        return save_path

    def wrapped():

        def check(info, *, incomplete):
            duration = info.get('duration')
            if duration and duration > 1200:
                return 'The video is too long'

        ydl_opts = {
            "quiet":
            True,
            "format":
            "m4a/bestaudio/best",
            # "postprocessors": [
            #     'key': 'FFmpegExtractAudio',
            #     'preferredcodec': 'vorbis',
            #     "preferredquality": 10.0
            # }],
            "match_filter":
            check,
            "postprocessors": [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'vorbis',
                "preferredquality": 10.0
            }, {
                'key': 'SponsorBlock'
            }, {
                'key': 'ModifyChapters',
                'remove_sponsor_segments': ["music_offtopic"]
            }],
            "break_on_reject":
            True,
            "outtmpl":
            str(save_path),
            "ffmpeg_location":
            CONFIG["ffmpeg_location"],
        }
        with YoutubeDL(ydl_opts) as ydl:
            return ydl.download([track.uri])

    code = await asyncio.get_event_loop().run_in_executor(None, wrapped)
    if code == 0:
        os.utime(save_path)
        return save_path
    else:
        raise ValueError


class LockedMenuPermissionsError:
    pass


class UserNotInVoiceChannelError(Exception):
    """The user is not in a voice channel."""
    pass


def round_to_base(x, prec=2, base=.05):
    return round(base * round(float(x) / base), prec)


def user_in_voice_channel(interaction: discord.Interaction) -> bool:
    return interaction.user.voice is not None


def get_track_choice_name(track: wavelink.Track):
    if hasattr(track, "duration"):
        duration = track.duration
    elif hasattr(track, "tracks"):
        duration = sum(t.duration for t in track.tracks)
    if hasattr(track, "title"):
        title = track.title
    elif hasattr(track, "name"):
        title = track.name
    minutes, seconds = divmod(int(duration), 60)
    hours, minutes = divmod(minutes, 60)
    h_str = "h"
    m_str = "m"
    if hours:
        duration = "{}{} {}{} {}s".format(hours, h_str, minutes, m_str,
                                          seconds)
    elif minutes:
        duration = "{}{} {}s".format(minutes, m_str, seconds)
    else:
        duration = "{}s".format(seconds)
    if len(title) > 83:
        title = title[:83] + "..."
    return f"{title} - {duration}"


def generate_progress_bar(percent, length=9):

    def map(value, fromLow, fromHigh, toLow, toHigh):
        return (value - fromLow) * (toHigh - toLow) / (fromHigh -
                                                       fromLow) + toLow

    val = int(map(percent, 0, 100, 0, length))
    result_str = ''

    result_str += PROGRESS_BAR_START

    for i in range(0, val - 1):
        result_str += PROGRESS_BAR_PART_1

    result_str += PROGRESS_BAR_PART_2

    for i in range(val, length - 1):
        result_str += PROGRESS_BAR_PART_3

    result_str += PROGRESS_BAR_END

    return result_str


# usage


class SongInputModal(discord.ui.Modal, title='Search song'):

    def __init__(self, controller, **kwargs):
        super().__init__(**kwargs)
        self.controller: MusicController = controller

    query = discord.ui.TextInput(label='Track to search for')
    platform = discord.ui.Select(placeholder='Platform',
                                 options=[
                                     discord.SelectOption(value='youtube',
                                                          label='YouTube'),
                                     discord.SelectOption(value='soundcloud',
                                                          label='SoundCloud'),
                                     discord.SelectOption(value='spotify',
                                                          label='Spotify')
                                 ])

    async def on_submit(self, interaction: discord.Interaction):
        # await interaction.response.send_message(f'Thanks for your response',
        #                                         ephemeral=True)
        if self.platform.values[0] != 'youtube':
            return await interaction.response.send_message(
                "Sorry, only YouTube supported here for now. Use "
                "the / commands for other platforms. TODO")
        await interaction.response.defer()
        results = await wavelink.YouTubeTrack.search(self.query.value)
        if not results:
            return await interaction.followup.send(
                "No results found for `{}`".format(self.query.value))
        if not isinstance(results, wavelink.YouTubePlaylist):
            results = results[0]
        await self.controller.cog.add_song_via_command(interaction, results)


class MusicControllerView(discord.ui.View):

    def __init__(self, guild: discord.Guild, controller):
        super().__init__(timeout=1200.0)
        self.guild = guild
        self.controller: MusicController = controller

    async def on_error(self, interaction: discord.Interaction,
                       error: Exception, item) -> None:
        message = "An unknown error occured"
        if isinstance(error, UserNotInVoiceChannelError):
            message = "You're not in the voice channel."
        if isinstance(error, LockedMenuPermissionsError):
            message = ("The player is currently locked. Only moderators "
                       "and the DJ can use it.")
        if not interaction.response.is_done():
            await interaction.response.send_message(message, ephemeral=True)
        else:
            await interaction.followup.send(message)
        log.exception("Error in player", exc_info=error)

    async def interaction_check(self,
                                interaction: discord.Interaction) -> bool:
        if not user_in_voice_channel(interaction):
            raise UserNotInVoiceChannelError
        player = self.guild.voice_client
        if interaction.user.voice.channel != player.channel:
            raise UserNotInVoiceChannelError
        if self.controller.locked:
            if interaction.user != player.dj:
                if not player.channel.permissions_for(
                        interaction.user).mute_members:
                    raise LockedMenuPermissionsError
        return True

    def embed(self):
        guild: discord.Guild = self.controller.guild
        player = guild.voice_client
        track = player.source
        if not track:
            return discord.Embed(title='No track playing',
                                 color=discord.Color.red())
        embed = discord.Embed(title=f'Now Playing: {track.title}')
        embed.color = EMBED_COLORS.get("weh", discord.Color.red())
        if hasattr(track, 'thumbnail'):
            embed.set_thumbnail(url=track.thumbnail)
        if not self.controller.shuffle:
            upcoming = self.controller.queue[:5]
            fmt = '\n'.join(f'**`{str(song)}`**' for song in upcoming)
            if fmt:
                embed.add_field(name='Upcoming', value=fmt, inline=False)

    #    end_time = self.controller.song_start_time + track.duration
        runtime = time.time() - self.controller.song_start_time
        percentage = int(runtime / track.duration * 100)
        duration_bar = generate_progress_bar(percentage, length=6)
        start_time = time.time() - player.position
        end_time = start_time + track.duration
        start_timestamp = f"<t:{int(start_time)}:R>"
        end_timestamp = f"<t:{int(end_time)}:R>"
        duration_bar = f"{start_timestamp} {duration_bar} {end_timestamp}"
        if player.is_paused():
            embed.add_field(name='Progress', value='Paused', inline=False)
        else:
            embed.add_field(name='Progress', value=duration_bar, inline=False)
        if self.controller.locked:
            embed.add_field(name='Locked',
                            value="Only moderator and DJ can "
                            "control the player. Click the padlock button to "
                            "disengage.",
                            inline=False)
        embed.set_footer(text=f"Volume: {int(self.controller.volume*100)}%")
        embed.set_author(name="Requested by " +
                         track.info["requester"].display_name,
                         icon_url=track.info["requester"].display_avatar.url)
        embed.url = track.uri
        return embed

    @discord.ui.button(emoji="⏪", custom_id="prev", row=1)
    async def previous(self, interaction: discord.Interaction,
                       button: discord.ui.Button):
        try:
            await self.controller.previous(response=interaction.response)
        except Exception:
            return await interaction.response.send_message("No previous song",
                                                           ephemeral=True)

    @discord.ui.button(emoji="⬅️", custom_id="seek_back", row=2)
    async def seek_back(self, interaction: discord.Interaction,
                        button: discord.ui.Button):
        player = interaction.guild.voice_client
        if not player or not player.source:
            return await interaction.response.send_message(
                'I am not currently playing anything!', ephemeral=True)
        track = player.source
        new_position = max(min(player.position - 10, track.duration), 0)
        await player.seek(int(new_position * 1000))
        self.controller.song_start_time -= player.position - new_position
        await self.controller.update_menu(response=interaction.response)

    @discord.ui.button(emoji="⏸️", custom_id="pause_resume", row=1)
    async def pause(self, interaction: discord.Interaction,
                    button: discord.ui.Button):
        player = interaction.guild.voice_client
        if not player or not player.source:
            return await interaction.response.send_message(
                'I am not currently playing anything!', ephemeral=True)
        if player.is_paused():
            await player.resume()
        else:
            await player.pause()
        await self.controller.update_menu(response=interaction.response)

    @discord.ui.button(emoji="➡️", custom_id="seek_forward", row=2)
    async def forward(self, interaction: discord.Interaction,
                      button: discord.ui.Button):
        player = interaction.guild.voice_client
        if not player or not player.source:
            return await interaction.response.send_message(
                'I am not currently playing anything!', ephemeral=True)
        track = player.source
        new_position = max(min(player.position + 10, track.duration), 0)
        await player.seek(int(new_position * 1000))
        self.controller.song_start_time += new_position - player.position
        self.controller.response = None
        await self.controller.update_menu(response=interaction.response)

    @discord.ui.button(emoji="⏩", custom_id="next", row=1)
    async def next(self, interaction: discord.Interaction,
                   button: discord.ui.Button):
        player = interaction.guild.voice_client
        if not player or not player.source:
            return await interaction.response.send_message(
                'I am not currently playing anything!', ephemeral=True)
        self.controller.response = interaction.response
        await player.stop()

    #    await self.controller.update_menu(response=interaction.response)

    @discord.ui.button(emoji="🔈", custom_id="voldown", row=3)
    async def voldown(self, interaction: discord.Interaction,
                      button: discord.ui.Button):
        if self.controller.volume > 0.05:
            new_volume = round_to_base(self.controller.volume - 0.05,
                                       base=0.05)
        else:
            new_volume = self.controller.volume - 0.01
        await self.controller.adjust_volume(new_volume)
        await self.controller.update_menu(response=interaction.response)

    @discord.ui.button(emoji="🔊", custom_id="volup", row=3)
    async def volup(self, interaction: discord.Interaction,
                    button: discord.ui.Button):
        if self.controller.volume >= 0.05:
            new_volume = round_to_base(self.controller.volume + 0.05,
                                       base=0.05)
        else:
            new_volume = self.controller.volume + 0.01
        await self.controller.adjust_volume(new_volume)
        await self.controller.update_menu(response=interaction.response)

    @discord.ui.button(emoji="⏹️",
                       custom_id="stop",
                       style=discord.ButtonStyle.red,
                       row=1)
    async def stop(self, interaction: discord.Interaction,
                   button: discord.ui.Button):
        new_volume = self.controller.volume + 0.05
        await self.controller.adjust_volume(new_volume)
        await interaction.response.send_message(
            f"Playback stopped by {interaction.user.mention}...",
            ephemeral=True)
        await self.controller.stop()
        self.stop()

    @discord.ui.button(emoji="🔀",
                       custom_id="shuffle",
                       style=discord.ButtonStyle.gray,
                       row=3)
    async def shuffle(self, interaction: discord.Interaction,
                      button: discord.ui.Button):
        self.controller.shuffle = not self.controller.shuffle
        await self.controller.bot.database.set(
            self.guild, {"shuffle": self.controller.shuffle},
            self.controller.cog)
        await self.controller.update_menu(response=interaction.response)

    @discord.ui.button(emoji="🔁",
                       custom_id="repeat",
                       style=discord.ButtonStyle.gray,
                       row=3)
    async def repeat(self, interaction: discord.Interaction,
                     button: discord.ui.Button):
        self.controller.repeat = not self.controller.repeat
        await self.controller.bot.database.set(
            self.guild, {"repeat": self.controller.repeat},
            self.controller.cog)
        await self.controller.update_menu(response=interaction.response)

    @discord.ui.button(emoji="🔓", custom_id="lock", row=4)
    async def lock(self, interaction: discord.Interaction,
                   button: discord.ui.Button):
        player = interaction.guild.voice_client
        if not player or not player.source:
            return await interaction.response.send_message(
                'I am not currently playing anything!', ephemeral=True)
        if interaction.user != player.dj:
            if not player.channel.permissions_for(
                    interaction.user).mute_members:
                return await interaction.response.send_message(
                    "Only the DJ and moderators can use this button.",
                    ephemeral=True)
        self.controller.locked = not self.controller.locked
        await self.controller.update_menu(response=interaction.response)

    @discord.ui.button(label="Add track...", emoji="🔎", row=4)
    async def add(self, interaction: discord.Interaction,
                  button: discord.ui.Button):
        modal = SongInputModal(self.controller)
        await interaction.response.send_modal(modal)
        await self.controller.update_menu(response=interaction.response)

    @discord.ui.button(label="Lyrics...", emoji="📃", row=4)
    async def lyrics(self, interaction: discord.Interaction,
                     button: discord.ui.Button):
        player = interaction.guild.voice_client
        if not player or not player.source:
            return await interaction.response.send_message(
                'I am not currently playing anything!', ephemeral=True)
        track = player.source
        lyrics = await self.controller.cog.get_lyrics(track)
        if lyrics:
            embed = discord.Embed(title=lyrics["title"])
            embed.set_author(name=lyrics["author"])
            embed.url = lyrics["links"]["genius"]
            embed.description = lyrics["lyrics"][:1024]
            await interaction.response.send_message(embed=embed,
                                                    ephemeral=True)
        else:
            await interaction.response.send_message(
                'Unable to find lyrics for this song', ephemeral=True)

    @discord.ui.button(label="Download track",
                       emoji="⏬",
                       row=4,
                       custom_id="download")
    async def download(self, interaction: discord.Interaction,
                       button: discord.ui.Button):
        player = interaction.guild.voice_client
        if not player or not player.source:
            return await interaction.response.send_message(
                'I am not currently playing anything!', ephemeral=True)
        track = player.source
        try:
            pass
        except ValueError:
            return await interaction.response.send_message(
                'This track is not from YouTube!', ephemeral=True)
        if track.identifier in self.controller.cog.download_tasks:
            return await interaction.response.send_message(
                # TODO add progress bar here
                "This track is currently being downloaded. Please wait!",
                ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            task = download_track(track)
            self.controller.cog.download_tasks[track.identifier] = task
            path = await asyncio.wait_for(task, timeout=60)
            del self.controller.cog.download_tasks[track.identifier]
        except YoutubeDLError as e:
            await interaction.followup.send(
                "The downloader encountered an error. Please try again later.",
                ephemeral=True)
            if track.identifier in self.controller.cog.download_tasks:
                del self.controller.cog.download_tasks[track.identifier]
            log.exception("Error while downloading track:", exc_info=e)
            return
        except ValueError:
            return await interaction.followup.send('Unable to download track',
                                                   ephemeral=True)
        except asyncio.TimeoutError:
            return await interaction.followup.send('Download timed out',
                                                   ephemeral=True)
        file = discord.File(path, filename=track.title + '.ogg')
        await interaction.followup.send("Your download is here.",
                                        file=file,
                                        ephemeral=True)

    # @discord.ui.button(labvel="Equalizer",
    #                    emoji="🔈",
    #                    custom_id="equalizer",
    #                    style=discord.ButtonStyle.gray,
    #                    row=3)
    async def equalizer(self, interaction: discord.Interaction,
                        button: discord.ui.Button):
        player = interaction.guild.voice_client
        if not player or not player.source:
            return await interaction.response.send_message(
                'I am not currently playing anything!', ephemeral=True)
        self.controller.equalizer_on = not self.controller.equalizer_on
        await self.controller.bot.database.set(
            self.guild, {"equalizer": self.controller.equalizer_on},
            self.controller.cog)
        await self.controller.update_menu(response=interaction.response)
        if self.controller.equalizer_on:
            filter = wavelink.filters.Equalizer.flat()
            await player.set_filter(filter)
        else:
            await player.set_filter(wavelink.filters.Filter())
        await self.controller.update_menu(response=interaction.response)


class SongQueue(asyncio.Queue):

    def __getitem__(self, item):
        if isinstance(item, slice):
            return list(
                itertools.islice(self._queue, item.start, item.stop,
                                 item.step))
        else:
            return self._queue[item]

    def __iter__(self):
        return self._queue.__iter__()

    def __len__(self):
        return self.qsize()

    def clear(self):
        self._queue.clear()

    def shuffle(self):
        random.shuffle(self._queue)

    def remove(self, index: int):
        del self._queue[index]

    def _insert(self, index: int, item) -> None:
        self._queue.insert(index, item)

    def put_at_index(self, index: int, item) -> None:
        """Put the given item into the queue at the specified index."""
        if self.is_full:
            raise asyncio.QueueFull(
                f"Queue max_size of {self.max_size} has been reached.")

        return self._insert(index, item)

    def appendleft(self, x):
        self._queue.appendleft(x)
        self._unfinished_tasks += 1
        self._finished.clear()
        self._wakeup_next(self._getters)

    def extend(self, iterable) -> None:
        for item in iterable:
            self.put_nowait(item)


class Player(wavelink.Player):

    def __init__(self, dj: discord.Member):
        super().__init__()
        self.dj = dj


class MusicController:

    def __init__(self, bot, cog, guild: discord.Guild):
        self.bot = bot
        self.cog: Music = cog
        self.guild = guild
        self.channel = None
        self.previous_songs = collections.deque(maxlen=100)
        self.next = asyncio.Event()
        self.added = asyncio.Event()
        self.queue = SongQueue(maxsize=1000)
        self.song_start_time = None
        self.volume = 0.15
        self.now_playing = None
        self.menu_message = None
        self.add_to_previous = True
        self.shuffle = False
        self.response: discord.InteractionResponse = None
        self.equalizer_on = False
        self.repeat = False
        self.locked = False
        self.bot.loop.create_task(self.controller_loop())

    async def adjust_volume(self, volume: float):
        volume = round(volume, 2)
        vol = max(min(volume, 5), 0.01)
        self.volume = vol
        await self.bot.database.set(self.guild, {"volume": vol}, self.cog)
        player = self.guild.voice_client
        if player:
            await player.set_volume(vol)
        return True

    async def stop(self):
        player: Player = self.guild.voice_client
        if player and player.is_connected():
            await player.disconnect()
        del self.cog.controllers[self.guild.id]
        if self.menu_message:
            await self.menu_message.delete()

    async def update_menu(self, *, response: InteractionResponse = None):
        player = self.guild.voice_client
        if not player and not len(self.queue) or not len(
                self.queue) and not player.source:
            embed = discord.Embed(title="Nothing currently playing. "
                                  "Disconnect in... <relative time stamp>")
            view = None
        else:
            view = MusicControllerView(self.guild, self)
            for item in view.children:
                if item.custom_id == 'next':
                    item.disabled = len(self.queue) == 0
                elif item.custom_id == "voldown":
                    item.disabled = self.volume == 0
                elif item.custom_id == "volup":
                    item.disabled = self.volume > 1
                elif item.custom_id == "shuffle":
                    if self.shuffle:
                        item.style = discord.ButtonStyle.green
                elif item.custom_id == "pause_resume":
                    if player.is_paused():
                        item.emoji = "▶️"
                        item.style = ButtonStyle.success
                    else:
                        item.emoji = "⏸️"
                        item.style = ButtonStyle.danger
                elif item.custom_id == "equalizer":
                    if self.equalizer_on:
                        item.style = discord.ButtonStyle.green
                    else:
                        item.style = discord.ButtonStyle.gray
                elif item.custom_id == "repeat":
                    if self.repeat:
                        item.style = discord.ButtonStyle.green
                    else:
                        item.style = discord.ButtonStyle.gray
                elif item.custom_id == "lock":
                    if self.locked:
                        item.style = discord.ButtonStyle.danger
                        item.emoji = "🔒"
                    else:
                        item.style = discord.ButtonStyle.gray
                        item.emoji = "🔓"
            embed = view.embed()
        if self.menu_message:
            if response and not response.is_done():
                await response.edit_message(embed=embed, view=view)
            else:
                await self.menu_message.edit(embed=embed, view=view)
        else:
            channel = self.guild.voice_client.channel
            self.menu_message = await channel.send(embed=embed, view=view)

    async def previous(self, *, response: InteractionResponse = None):
        player: Player = self.guild.voice_client
        runtime = time.time() - self.song_start_time
        if not self.previous_songs or (player.is_playing() and runtime > 8):
            await player.seek(0)
            if player.is_paused():
                await player.resume()
            self.song_start_time = time.time()
            await self.update_menu(response=response)
            self.response = None
            return
        song = self.previous_songs.pop()
        if not song:
            raise Exception('No song to play')
        if player.source:
            self.queue.appendleft(player.source)

        self.queue.appendleft(song)
        if player.is_playing():
            self.add_to_previous = False
            if response:
                self.response = response
            await player.stop()

    async def controller_loop(self):
        try:
            await self.bot.wait_until_ready()
            doc = await self.bot.database.get(self.guild, self.cog)
            self.shuffle = doc.get('shuffle', False)
            self.equalizer_on = doc.get('equalizer', False)
            self.repeat = doc.get('repeat', False)
            player: Player = self.guild.voice_client
            # if self.equalizer_on:
            #     filter = wavelink.filters.Equalizer.flat()
            #     await player.set_filter(
            #         wavelink.filters.Filter(wavelink.filters.Equalizer.flat()))
            # else:
            #     await player.set_filter(wavelink.filters.Filter())
            while True:
                try:
                    self.add_to_previous = True
                    self.next.clear()
                    self.added.clear()
                    async with async_timeout.timeout(30):
                        song = await self.queue.get()
                    await player.play(song)
                    await self.next.wait()
                    if self.add_to_previous:
                        self.previous_songs.append(song)
                        if self.shuffle:
                            self.queue.shuffle()
                    self.added.set()
                except (asyncio.exceptions.CancelledError,
                        asyncio.exceptions.TimeoutError) as e:
                    log.error("Error in inner loop", exc_info=e)
                    await self.stop()
                    break
        except Exception as e:
            log.error("Error in outer loop", exc_info=e)


class Music(commands.Cog):

    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot
        self.controllers = {}
        self.searches_collection = self.bot.database.db.searches
        self.sb = sponsorblock.Client()
        self.delete_old_downloads.start()
        self.download_tasks = {}

    async def cog_load(self):
        spotify_client = None
        if CONFIG["spotify"]["client_id"] and CONFIG["spotify"][
                "client_secret"]:
            spotify_client = spotify.SpotifyClient(**CONFIG["spotify"])
        for node in CONFIG["nodes"]:
            if spotify_client:
                node["spotify_client"] = spotify_client
            await wavelink.NodePool.create_node(bot=self.bot, **node)

    async def cog_unload(self):
        self.delete_old_downloads.cancel()
        for voice_state in self.bot.voice_clients:
            await voice_state.disconnect(force=True)

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        print(f'Node: <{node.identifier}> is ready!')

    async def get_skip_segments(self, url: str):

        def proxy_pass(url):
            return self.sb.get_skip_segments(url)

        return await self.bot.loop.run_in_executor(None, proxy_pass, url)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, player: wavelink.player,
                                      track: wavelink.Track):
        controller = self.get_controller(player.guild)
        controller.song_start_time = time.time()
        await controller.update_menu(response=controller.response)
        controller.response = None
        try:
            segments = await self.get_skip_segments(track.uri)
        except Exception:
            segments = []
        if segments:
            while True:
                if controller.guild.voice_client.source.id != track.id:
                    break
                position = player.position
                for segment in segments:
                    if position >= segment.start and position <= segment.end:
                        await player.seek(segment.end * 1000)
                await asyncio.sleep(0.5)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player, track, reason):
        controller = self.get_controller(player.guild)
        controller.next.set()
        await controller.added.wait()
        # Check if the track is the last in the queue
        if not controller.queue and not player.source:
            if controller.repeat:
                controller.queue.extend(controller.previous_songs)
                controller.previous_songs.clear()
            else:
                await controller.update_menu(response=controller.response)
                controller.response = None
                # await controller.stop()
                return

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, player: Player, track, error):
        controller = self.get_controller(player.guild)
        controller.next.set()

    def get_controller(self, guild: discord.Guild, *, create=False):
        try:
            controller = self.controllers[guild.id]
        except KeyError:
            if create:
                controller = MusicController(self.bot, self, guild)
                self.controllers[guild.id] = controller
            else:
                return None
        return controller

    async def connect(self, user: discord.Member,
                      channel: discord.VoiceChannel):
        if not user.guild.voice_client:
            player = Player(dj=user)
            player = await channel.connect(cls=player, self_deaf=True)
            doc = await self.bot.database.get(user.guild, self)
            controller = self.get_controller(user.guild, create=True)
            vol = doc.get('volume', 0.15)
            controller.volume = vol
            await player.set_volume(vol)
            return player

    async def get_tracks_by_query(self,
                                  query,
                                  *,
                                  search_type="song",
                                  platform="youtube"):
        if platform == "youtube":
            if search_type == "song":
                cls = wavelink.YouTubeTrack
            elif search_type == "playlist":
                return []
        elif platform == "spotify":
            return []
            cls = spotify.SpotifyTrack
        results = await cls.search(query)
        if not results:
            return []
        options = []
        tracks = []
        if hasattr(results, "tracks"):
            tracks = results.tracks
        else:
            tracks = results
        for track in tracks:
            name = get_track_choice_name(track)
            options.append(app_commands.Choice(name=name, value=track.uri))
        return options[:25]

    async def get_user_recent_searches(self,
                                       user: discord.User,
                                       search_type="song",
                                       platform="youtube"):
        cursor = self.searches_collection.find({
            "user_id": user.id,
            "search_type": search_type,
            "platform": platform
        }).sort("created_at").limit(25)
        return [
            app_commands.Choice(name=track["name"], value=track["uri"])
            async for track in cursor
        ]

    async def song_search_autocomplete(self, interaction: discord.Interaction,
                                       current):
        search = interaction.command.extras["search"]
        if not current:
            results = await self.get_user_recent_searches(
                interaction.user, **search)
            return list(reversed(results))
        return await self.get_tracks_by_query(current, **search)

    @aiocache.cached(ttl=600)
    async def get_lyrics(self, track: wavelink.Track):
        title = urllib.parse.quote(track.title)
        url = LYRICS_URL.format(title)
        async with self.bot.session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            if not data:
                return None
            return data

    async def add_song_via_command(self,
                                   interaction: discord.Interaction,
                                   track: wavelink.Track,
                                   url=None):
        if not track:
            return await interaction.followup.send(
                'Could not find any songs with that query.')
        is_list = isinstance(track, list)
        if interaction.command and not is_list:
            recent = await self.searches_collection.find({
                "user_id":
                interaction.user.id,
                **interaction.command.extras["search"]
            }).sort("created_at").to_list(length=25)
            to_update = None
            for recent in recent:
                if recent["uri"] == url:
                    to_update = recent["_id"]
                    break
            url = url
            if hasattr(track, "uri"):
                url = track.uri
            if not to_update:
                await self.searches_collection.insert_one({
                    "user_id":
                    interaction.user.id,
                    "name":
                    get_track_choice_name(track),
                    "uri":
                    url,
                    "created_at":
                    datetime.datetime.now(datetime.timezone.utc),
                    **interaction.command.extras["search"]
                })
            else:
                await self.searches_collection.update_one({"_id": to_update}, {
                    "$set": {
                        "created_at": datetime.datetime.now(
                            datetime.timezone.utc)
                    }
                },
                                                          upsert=False)
        channel = interaction.user.voice.channel
        await self.connect(interaction.user, channel)
        controller = self.get_controller(interaction.guild)
        unposted = controller.menu_message is None
        if interaction.channel != channel and unposted:
            extra = f"\nControl panel sent to {channel.mention} text channel."
        else:
            extra = ""
        iterable = None
        if is_list:
            iterable = track
        if hasattr(track, "tracks"):
            iterable = track.tracks
        if iterable:
            for t in iterable:
                t.info["requester"] = interaction.user
            try:
                controller.queue.extend(iterable)
                await interaction.followup.send(
                    "Added the playlist to queue." + extra)
            except asyncio.QueueFull:
                await interaction.followup.send(
                    "Some of the tracks haven't been aded as the queue is full"
                    + extra)
                return
            finally:
                if not unposted:
                    await controller.update_menu()
        else:
            track.info["requester"] = interaction.user
            await controller.queue.put(track)
            await interaction.followup.send("Added the song to queue." + extra)
        if not unposted:
            await controller.update_menu()

    @app_commands.command(
        extras={"search": {
            "search_type": "song",
            "platform": "youtube"
        }})
    @app_commands.guild_only()
    @app_commands.describe(
        query="The URL of the song to play, or a search term.")
    @app_commands.autocomplete(query=song_search_autocomplete)
    async def play(self, interaction: discord.Interaction, query: str):
        """Search for and add a song to the Queue."""
        if not interaction.user.voice:
            return await interaction.response.send_message(
                "You are not in a voice channel.")
        await interaction.response.defer()
        results = await wavelink.YouTubeTrack.search(query)
        if not isinstance(results, wavelink.YouTubePlaylist):
            results = results[0]
        await self.add_song_via_command(interaction, results, url=query)

    @app_commands.command(
        extras={"search": {
            "search_type": "song",
            "platform": "spotify"
        }})
    @app_commands.guild_only()
    @app_commands.describe(
        url="The URL of the song to play, or the Spotify ID.")
    @app_commands.autocomplete(url=song_search_autocomplete)
    async def play_spotify(self, interaction: discord.Interaction, url: str):
        """Search for and add a song to the Queue."""
        if not interaction.user.voice:
            return await interaction.response.send_message(
                "You are not in a voice channel.")
        await interaction.response.defer()
        if url.startswith("https://open.spotify.com/"):
            decoded = spotify.decode_url(url)
            if not decoded:
                return await interaction.response.send_message(
                    "Invalid Spotify URL.")
            track_id = decoded["id"]
            search_type = decoded["type"]
            if search_type == spotify.SpotifySearchType.unusable:
                return await interaction.response.send_message(
                    "Invalid Spotify URL.")
            results = await spotify.SpotifyTrack.search(track_id,
                                                        type=search_type)
        else:
            results = await wavelink.YouTubeTrack.search(url)
        if not results:
            return await interaction.followup.send(
                'Could not find any songs with that query.')
        await self.add_song_via_command(interaction, results, url=url)

    @app_commands.command(
        extras={"search": {
            "search_type": "playlist",
            "platform": "youtube"
        }})
    @app_commands.guild_only()
    @app_commands.describe(url="The URL of the playlist to play.")
    @app_commands.autocomplete(url=song_search_autocomplete)
    async def play_playlist(self, interaction: discord.Interaction, url: str):
        """Queue a playlist. """
        if not interaction.user.voice:
            return await interaction.response.send_message(
                "You are not in a voice channel.")
        await interaction.response.defer()
        result = await wavelink.YouTubePlaylist.search(url)
        if not result:
            return await interaction.response.send_message(
                'Could not find any playlists with that URL.', ephemeral=True)
        await self.add_song_via_command(interaction, result, url)

    async def pause_playback(self, guild: discord.Guild):
        player = guild.voice_client
        if not player.is_playing():
            return False
        player.pause()
        return True

    @app_commands.command()
    @app_commands.guild_only()
    async def pause(self, interaction: discord.Interaction):
        """Pause the playback."""
        if not interaction.guild.voice_client:
            return await interaction.response.send_message(
                'Currently not playing.')
        player = interaction.guild.voice_client
        if player.is_paused():
            await player.resume()
            return await interaction.response.send_message(
                'Resumed the playback.')
        result = await self.pause_playback(interaction.guild)
        if result:
            await interaction.response.send_message('Paused the playback.')
        else:
            await interaction.response.send_message('Currently not playing.')

    @app_commands.command()
    @app_commands.guild_only()
    async def resume(self, interaction: discord.Interaction):
        """Resume the player from a paused state."""
        if not interaction.guild.voice_client:
            return await interaction.response.send_message(
                'Currently not playing.')
        player = interaction.guild.voice_client
        if player.is_paused():
            await player.resume()
            return await interaction.response.send_message(
                'Resumed the playback.')
        else:
            return await interaction.response.send_message(
                'Currently not paused.')

    @app_commands.command()
    @app_commands.guild_only()
    async def skip(self, interaction: discord.Interaction):
        """Skip the currently playing song."""
        player = interaction.guild.voice_client
        if not player or not player.source:
            return await interaction.response.send_message(
                'I am not currently playing anything!', ephemeral=True)

        await interaction.response.send_message('Skipping the song!')
        await player.stop()

    @app_commands.command()
    @app_commands.guild_only()
    @app_commands.describe(
        volume="The volume, between 0 and 100. Moderators can increase "
        "the volume up to 200.")
    async def volume(self, interaction,
                     volume: app_commands.transformers.Range[int, 0, 200]):
        """Set the player volume."""

        controller = self.get_controller(interaction.guild)
        vol = volume / 100
        controller.volume = vol
        await self.bot.database.set(interaction.guild, {"volume": vol}, self)
        await interaction.response.send_message(
            f'Setting the player volume to `{volume}`')
        player = interaction.guild.voice_client
        if player:
            await player.set_volume(vol)

    @app_commands.command()
    @app_commands.guild_only()
    async def song(self, interaction: discord.Interaction):
        """Retrieve the currently playing song."""
        player = interaction.guild.voice_client
        if not player or not player.source:
            return await interaction.response.send_message(
                'I am not currently playing anything!', ephemeral=True)

        await interaction.response.send_message(
            f'Now playing: `{player.source}`')

    @app_commands.command()
    @app_commands.guild_only()
    async def queue(self, interaction: discord.Interaction):
        """Retrieve information on the next 5 songs from the queue."""
        controller = self.get_controller(interaction.guild)
        player = interaction.guild.voice_client
        if not player or not player.source or not controller.queue._queue:
            return await interaction.response.send_message(
                'There are no songs currently in the queue.')
        upcoming = controller.queue[:6]

        fmt = '\n'.join(f'**`{str(song)}`**' for song in upcoming)
        embed = discord.Embed(title=f'Upcoming - Next {len(upcoming)}',
                              description=fmt)

        await interaction.response.send_message(embed=embed)

    @app_commands.command()
    @app_commands.guild_only()
    async def stop(self, interaction: discord.Interaction):
        """Stop and disconnect the player and controller."""
        controller = self.get_controller(interaction.guild)
        await controller.stop()
        await interaction.response.send(
            'Disconnected player and killed controller.')

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState,
                                    after: discord.VoiceState):
        if member == self.bot.user:
            if before.channel and not after.channel:
                controller = self.get_controller(member.guild)
                if controller:
                    await controller.stop()
        if member.bot:
            return
        controller = self.get_controller(member.guild)
        if after.channel:
            return
        player = member.guild.voice_client
        if not player:
            return
        if before.channel and before.channel == player.channel:
            members = [m for m in player.channel.members if not m.bot]
            if len(members) == 0:
                await controller.stop()
                return await before.channel.send(
                    "All users have left. Stopping playback.")

    @tasks.loop(minutes=1)
    async def delete_old_downloads(self):
        directory = BASE_PATH / "cache"
        for path in directory.glob("*.ogg"):
            if path.stat().st_mtime < time.time() - 60 * 60 * 24:
                path.unlink()


async def setup(bot):
    await bot.add_cog(Music(bot))
