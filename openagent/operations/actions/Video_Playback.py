# import time
#
# from selenium.webdriver import Keys
#
# from operations.action import ActionInputCollection
# from toolkits import spotify
# from operations.actions.Web_Browser_and_Website import *
# from utils.helpers import categorize_item
#
#
# class PlayVideo(Action):
#     def __init__(self):
#         super().__init__(agent, example='play some music')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Play music / resume video playback where what to play is unspecified'
#
#     def run_action(self):
#         try:
#             # if not spotify.has_active_device():
#             #     open_action = Open_Websites()
#             #     open_action.inputs.get(0).user_input = 'https://open.spotify.com/'
#             #     open_action.run_action(assistant)
#             #     time.sleep(9)
#             #     toolkits.browser.send_keys(Keys.SPACE)
#             #     time.sleep(2)
#
#             if spotify.is_playing():
#                 yield ActionResult('[SAY]that video is already playing.')
#
#             spotify.play()
#             yield ActionResult('[SAY]that video is now playing.')
#         except Exception as e:
#             if 'NO_ACTIVE_DEVICE' in str(e):
#                 yield ActionResult("[SAY]spotify isn't open on a device.")
#             yield ActionResult("[SAY]there was an error playing music.")
#
#
# class SearchPlayVideo(Action):
#     def __init__(self):
#         super().__init__(agent, example='play the beatles')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Search and Play a specific song/album/artist/playlist/genre'
#         self.inputs = ActionInputCollection([
#             ActionInput('spotify_search_query', examples=['drops of jupiter&&&your song&&&candle in the wind&&&fast car', 'blues'])
#         ])
#
#     def run_action(self):
#         try:
#             # if not spotify.has_active_device():
#             #     open_action = Open_Websites()
#             #     open_action.inputs.get(0).user_input = 'https://open.spotify.com/'
#             #     open_action.run_action(assistant)
#             #     time.sleep(9)
#             #     toolkits.browser.send_keys(Keys.SPACE)
#             #     time.sleep(2)
#
#             # spotify.play()
#
#             search_query = self.inputs.get(0).value
#             cats = [
#                 'track',
#                 'artist',
#                 'album',
#                 'playlist',
#                 'genre',
#             ]
#             cat = categorize_item(cats, search_query)
#             cat = cat.replace('song', 'track')
#             cat = cat.replace('band', 'artist')
#             cat = cat.replace('singer', 'artist')
#             if cat not in cats:
#                 print("whyyyy3479")
#             if cat == 'genre':
#                 results = spotify.sp.search(search_query, type='playlist', limit=1)
#                 uri = results['playlists']['items'][0]['uri']
# #                 songs = oai.get_scalar(f"""
# # List 5 of the best {search_query} song titles and their artist in the format '""" + "{title} by {artist}" + """'. Separate each by a newline
# # Songs:
# # """)
# #                 songs = [s.strip() for s in songs.split('\n') if s.strip() != '' and ' by ' in s.lower()]
# #                 for song in songs:
# #                     r = spotify.sp.search(song, limit=1, type='track')
# #                     uri = r['tracks']['items'][0]['uri']
#             else:
#                 results = spotify.sp.search(search_query, limit=1, type=cat)  # , market=None)
#                 uri = results[cat + 's']['items'][0]['uri']
#
#             if cat == 'track':
#                 spotify.sp.start_playback(device_id=spotify.device_id(), uris=[uri])
#             else:
#                 spotify.sp.start_playback(device_id=spotify.device_id(), context_uri=uri)
#
#             time.sleep(1)
#             cur_track = spotify.get_current_track_name()
#             if cur_track is None:
#                 cur_track = search_query
#
#             yield ActionResult("[SAY]" + cur_track + " is now playing.")
#         except Exception as e:
#             if 'NO_ACTIVE_DEVICE' in str(e):
#                 yield ActionResult("[SAY]spotify isn't open on a device.")
#             yield ActionResult("[SAY]there was an error playing the request.")
#
#
# class PauseMusic(Action):
#     def __init__(self):
#         super().__init__(agent, example='pause music')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Pause/Stop music'
#         # self.inputs.add('url', example='google.com'))
#
#     def run_action(self):
#         try:
#             # if not spotify.has_active_device():
#             #     open_action = Open_Website()
#             #     open_action.inputs.get(0).user_input = 'https://open.spotify.com/'
#             #     open_action.run_action(agent)
#             #     time.sleep(8)
#             #     apps.browser.send_keys(Keys.SPACE)
#
#             if not spotify.is_playing():
#                 yield ActionResult('[SAY]that no music is playing.')
#
#             spotify.pause()
#             yield ActionResult('[SAY]that music is now paused.')
#         except Exception as e:
#             if 'NO_ACTIVE_DEVICE' in str(e):
#                 yield ActionResult("[SAY]spotify isn't open on a device.")
#             yield ActionResult("[SAY]there was an error pausing music.")
#
#
# class NextTrack(Action):
#     def __init__(self):
#         super().__init__(agent, example='play the next music track')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Skip to the next track'
#
#     def run_action(self):
#         try:
#             # if not spotify.has_active_device():
#             #     open_action = Open_Website()
#             #     open_action.inputs.get(0).user_input = 'https://open.spotify.com/'
#             #     open_action.run_action(agent)
#             #     time.sleep(5)
#
#             track_name = spotify.skip_track()
#             yield ActionResult(f'[SAY]that the next track ({track_name}) is now playing.')
#         except Exception as e:
#             if 'NO_ACTIVE_DEVICE' in str(e):
#                 yield ActionResult("[SAY]spotify isn't open on a device.")
#             yield ActionResult("[SAY]there was an error playing the next track.")
#
#
# class PreviousTrack(Action):
#     def __init__(self):
#         super().__init__(agent, example='play the last track')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Play the previous track'
#
#     def run_action(self):
#         try:
#             # if not spotify.has_active_device():
#             #     open_action = Open_Website()
#             #     open_action.inputs.get(0).user_input = 'https://open.spotify.com/'
#             #     open_action.run_action(agent)
#             #     time.sleep(5)
#
#             spotify.previous_track()
#             yield ActionResult('[SAY]that the previous track is now playing.')
#         except Exception as e:
#             if 'NO_ACTIVE_DEVICE' in str(e):
#                 yield ActionResult("[SAY]spotify isn't open on a device.")
#             yield ActionResult("[SAY]there was an error playing the previous track.")
#
#
# class RepeatTrack(Action):
#     def __init__(self):
#         super().__init__(agent, example='replay this track')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Replay the current track'
#
#     def run_action(self):
#         try:
#             # if not spotify.has_active_device():
#             #     open_action = Open_Website()
#             #     open_action.inputs.get(0).user_input = 'https://open.spotify.com/'
#             #     open_action.run_action(agent)
#             #     time.sleep(5)
#
#             spotify.restart_song()
#             yield ActionResult('[SAY]that the track is now replaying.')
#         except Exception as e:
#             if 'NO_ACTIVE_DEVICE' in str(e):
#                 yield ActionResult("[SAY]spotify isn't open on a device.")
#             yield ActionResult("[SAY]there was an error replaying the track.")
#
#
# class SwitchPlaybackToSmartphone(Action):
#     def __init__(self):
#         super().__init__(agent, example='play music through my phone')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Switch music playback to smartphone for current music streaming'
#
#     def run_action(self):
#         try:
#             spotify.switch_to_smartphone_device()
#             spotify.play()
#             yield ActionResult('[SAY]that the playback is now playing through smartphone.')
#         except Exception as e:
#             if 'NO_ACTIVE_DEVICE' in str(e):
#                 yield ActionResult("[SAY]spotify isn't open on a device.")
#             yield ActionResult("[SAY]there was an error switching playback device.")
#
#
# class SwitchPlaybackToDesktop(Action):
#     def __init__(self):
#         super().__init__(agent, example='play music through my pc')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Switch music playback to desktop for current music streaming'
#
#     def run_action(self):
#         try:
#             spotify.switch_to_desktop_device()
#             spotify.play()
#             yield ActionResult('[SAY]that the playback is now playing through desktop.')
#         except Exception as e:
#             if 'NO_ACTIVE_DEVICE' in str(e):
#                 yield ActionResult("[SAY]spotify isn't open on a device.")
#             yield ActionResult("[SAY]there was an error switching playback device.")
#
#
# class ToggleShuffle(Action):
#     def __init__(self):
#         super().__init__(agent, example='turn shuffle on')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Toggle shuffle mode for current music playback'
#         self.inputs.add('state', format='Boolean (True/False)', examples=['True']))
#
#     def run_action(self):
#         state = self.inputs.get('state').value.lower().strip() == 'true'
#         try:
#             current_state = spotify.get_shuffle()
#             if current_state == state and state:
#                 yield ActionResult('[SAY]that shuffle is already on.')
#             elif current_state == state and not state:
#                 yield ActionResult('[SAY]that shuffle is already off.')
#             spotify.set_shuffle(state)
#             if state:
#                 yield ActionResult('[SAY]that shuffle is now on.')
#             else:
#                 yield ActionResult('[SAY]that shuffle is now off.')
#         except Exception as e:
#             if 'NO_ACTIVE_DEVICE' in str(e):
#                 yield ActionResult("[SAY]spotify isn't open on a device.")
#             yield ActionResult("[SAY]there was an error setting shuffle status.")
#
#
# class NameOfCurrentlyPlayingTrack(Action):
#     def __init__(self):
#         super().__init__(agent, example='what song is this?')
#         self.desc_prefix = 'requires me to'
#         self.desc = 'Get the name of the currently playing song/artist/album/playlist/genre'
#
#     def run_action(self):
#         try:
#             if not spotify.has_active_device():
#                 # try to shazam it
#                 yield ActionResult('[SAY]that no music is playing.')
#
#             cur_playing = spotify.get_current_track_name()
#
#             yield ActionResult(f'[ANS]{cur_playing}.')
#         except Exception as e:
#             if 'NO_ACTIVE_DEVICE' in str(e):
#                 yield ActionResult("[SAY]spotify isn't open on a device.")
#             yield ActionResult("[SAY]there was a problem finding an answer.")
