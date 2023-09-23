import time
from operations.action import ActionSuccess, ActionInput, BaseAction, ActionInputCollection
from toolkits import spotify
from utils.helpers import categorize_item


class PlayMusic(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='play some music')
        self.desc_prefix = 'requires me to'
        self.desc = 'Play music / resume playback where what to play is unspecified'

    def run_action(self):
        try:
            # if not spotify.has_active_device():
            #     open_action = Open_Websites()
            #     open_action.inputs.get(0).user_input = 'https://open.spotify.com/'
            #     open_action.run_action(assistant)
            #     time.sleep(9)
            #     toolkits.browser.send_keys(Keys.SPACE)
            #     time.sleep(2)

            if spotify.is_playing():
                yield ActionSuccess('[SAY] music is already playing.')

            spotify.play()
            yield ActionSuccess('[SAY] music is now playing')
        except Exception as e:
            if 'NO_ACTIVE_DEVICE' in str(e):
                yield ActionSuccess("[SAY]spotify isn't open on a device.")
            yield ActionSuccess("[SAY]there was an error playing music.")


class SearchPlayMusic(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='play the beatles')
        self.desc_prefix = 'requires me to'
        self.desc = 'Search and Play a specific song/album/artist/playlist/genre'
        self.inputs = ActionInputCollection([
            ActionInput('spotify_search_query',
                        examples=['drops of jupiter&&&your song&&&candle in the wind&&&fast car', 'blues'])
        ])

    def run_action(self):
        try:
            search_query = self.inputs.get(0).value
            cats = [
                'track',
                'artist',
                'album',
                'playlist',
                'genre',
            ]
            cat = categorize_item(cats, search_query)
            cat = cat.replace('song', 'track')
            cat = cat.replace('band', 'artist')
            cat = cat.replace('singer', 'artist')
            if cat not in cats:
                print("whyyyy3479")
            if cat == 'genre':
                results = spotify.sp().search(search_query, type='playlist', limit=1)
                uri = results['playlists']['items'][0]['uri']
#                 songs = llm.get_scalar(f"""
# List 5 of the best {search_query} song titles and their artist in the format '""" + "{title} by {artist}" + """'. Separate each by a newline
# Songs:
# """)
#                 songs = [s.strip() for s in songs.split('\n') if s.strip() != '' and ' by ' in s.lower()]
#                 for song in songs:
#                     r = spotify.sp.search(song, limit=1, type='track')
#                     uri = r['tracks']['items'][0]['uri']
            else:
                results = spotify.sp().search(search_query, limit=1, type=cat)  # , market=None)
                uri = results[cat + 's']['items'][0]['uri']

            if cat == 'track':
                spotify.sp().start_playback(device_id=spotify.device_id(), uris=[uri])
            else:

                spotify.sp().start_playback(device_id=spotify.device_id(), context_uri=uri)

            time.sleep(1)
            cur_track = spotify.get_current_track_name()
            if cur_track is None:
                cur_track = search_query

            yield ActionSuccess(f'[SAY] "Now playing" (track-name:{cur_track})')
        except Exception as e:
            if 'NO_ACTIVE_DEVICE' in str(e):
                yield ActionSuccess("[SAY]spotify isn't open on a device.")
            yield ActionSuccess("[SAY]there was an error playing the request.")


class PauseMusic(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='pause music')
        self.desc_prefix = 'requires me to'
        self.desc = 'Pause/Stop music'
        # self.inputs.add('url', example='google.com'))

    def run_action(self):
        try:
            # if not spotify.has_active_device():
            #     open_action = Open_Website()
            #     open_action.inputs.get(0).user_input = 'https://open.spotify.com/'
            #     open_action.run_action(agent)
            #     time.sleep(8)
            #     apps.browser.send_keys(Keys.SPACE)

            if not spotify.is_playing():
                yield ActionSuccess('[SAY] no music is playing.')

            spotify.pause()
            yield ActionSuccess('[SAY] music is now paused, in 1 sentence.')
        except Exception as e:
            if 'NO_ACTIVE_DEVICE' in str(e):
                yield ActionSuccess("[SAY]spotify isn't open on a device.")
            yield ActionSuccess("[SAY]there was an error pausing music.")


class NextTrack(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='play the next music track')
        self.desc_prefix = 'requires me to'
        self.desc = 'Skip to the next track'

    def run_action(self):
        try:
            # if not spotify.has_active_device():
            #     open_action = Open_Website()
            #     open_action.inputs.get(0).user_input = 'https://open.spotify.com/'
            #     open_action.run_action(agent)
            #     time.sleep(5)

            track_name = spotify.skip_track()
            yield ActionSuccess(f'[SAY] "The next track is now playing" (track-name:{track_name})')
        except Exception as e:
            if 'NO_ACTIVE_DEVICE' in str(e):
                yield ActionSuccess("[SAY]spotify isn't open on a device.")
            yield ActionSuccess("[SAY]there was an error playing the next track.")


class PreviousTrack(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='play the last track')
        self.desc_prefix = 'requires me to'
        self.desc = 'Play the previous track'

    def run_action(self):
        try:
            # if not spotify.has_active_device():
            #     open_action = Open_Website()
            #     open_action.inputs.get(0).user_input = 'https://open.spotify.com/'
            #     open_action.run_action(agent)
            #     time.sleep(5)

            spotify.previous_track()
            yield ActionSuccess('[SAY] the previous track is now playing.')
        except Exception as e:
            if 'NO_ACTIVE_DEVICE' in str(e):
                yield ActionSuccess("[SAY]spotify isn't open on a device.")
            yield ActionSuccess("[SAY]there was an error playing the previous track.")


class RepeatTrack(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='replay this track')
        self.desc_prefix = 'requires me to'
        self.desc = 'Replay the current track'

    def run_action(self):
        try:
            # if not spotify.has_active_device():
            #     open_action = Open_Website()
            #     open_action.inputs.get(0).user_input = 'https://open.spotify.com/'
            #     open_action.run_action(agent)
            #     time.sleep(5)

            spotify.restart_song()
            yield ActionSuccess('[SAY] the track is now replaying.')
        except Exception as e:
            if 'NO_ACTIVE_DEVICE' in str(e):
                yield ActionSuccess("[SAY]spotify isn't open on a device.")
            yield ActionSuccess("[SAY]there was an error replaying the track.")


class SwitchPlaybackToSmartphone(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='play music through my phone')
        self.desc_prefix = 'requires me to'
        self.desc = 'Switch music playback to smartphone for current music streaming'

    def run_action(self):
        try:
            spotify.switch_to_smartphone_device()
            spotify.play()
            yield ActionSuccess('[SAY] the playback is now playing through smartphone.')
        except Exception as e:
            if 'NO_ACTIVE_DEVICE' in str(e):
                yield ActionSuccess("[SAY]spotify isn't open on a device.")
            yield ActionSuccess("[SAY]there was an error switching playback device.")


class SwitchPlaybackToDesktop(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='play music through my pc')
        self.desc_prefix = 'requires me to'
        self.desc = 'Switch music playback to desktop for current music streaming'

    def run_action(self):
        try:
            spotify.switch_to_desktop_device()
            spotify.play()
            yield ActionSuccess('[SAY] the playback is now playing through desktop.')
        except Exception as e:
            if 'NO_ACTIVE_DEVICE' in str(e):
                yield ActionSuccess("[SAY]spotify isn't open on a device.")
            yield ActionSuccess("[SAY]there was an error switching playback device.")


class ToggleShuffle(BaseAction):
    def __init__(self, agent):
        super().__init__(agent, example='turn shuffle on')
        self.desc_prefix = 'requires me to'
        self.desc = 'Toggle shuffle mode for current music playback'
        self.inputs.add('new-shuffle-state-to-set-to', format='Boolean (True/False)', examples=['True'])

    def run_action(self):
        state = self.inputs.get('new-shuffle-state-to-set-to').value.lower().strip() == 'true'
        try:
            current_state = spotify.get_shuffle()
            if current_state == state and state:
                yield ActionSuccess('[SAY] shuffle is already on.')
            elif current_state == state and not state:
                yield ActionSuccess('[SAY] shuffle is already off.')
            spotify.set_shuffle(state)
            if state:
                yield ActionSuccess('[SAY] shuffle is now on.')
            else:
                yield ActionSuccess('[SAY] shuffle is now off.')
        except Exception as e:
            if 'NO_ACTIVE_DEVICE' in str(e):
                yield ActionSuccess("[SAY]spotify isn't open on a device.")
            yield ActionSuccess("[SAY]there was an error setting shuffle status.")
