import spotipy
from spotipy.oauth2 import SpotifyOAuth


class SpotifyClient:
    def __init__(self, client_id, client_secret):
        scope = "user-read-playback-state,user-modify-playback-state,streaming"
        self.client = spotipy.Spotify(client_credentials_manager=SpotifyOAuth(
            client_id,
            client_secret,
            redirect_uri='http://127.0.0.1:9090',
            scope=scope)
        )

    def device_id(self):
        devices = self.client.devices()
        active_devices = [d for d in devices['devices'] if d['is_active']]
        if len(active_devices) == 0: return None
        dev_id = active_devices[0]['id']
        return dev_id

    def has_active_device(self):
        return self.device_id() is not None

    def switch_to_smartphone_device(self):
        devices = self.client.devices()
        smartphone_devices = [d for d in devices['devices'] if d['type'] == 'Smartphone']
        if len(smartphone_devices) == 0: return None

        dev_id = smartphone_devices[0]['id']
        self.client.transfer_playback(device_id=dev_id, force_play=True)
        return dev_id

    def switch_to_desktop_device(self):
        devices = self.client.devices()
        desktop_devices = [d for d in devices['devices'] if d['type'] == 'Computer']
        if len(desktop_devices) == 0: return None

        dev_id = desktop_devices[0]['id']
        self.client.transfer_playback(device_id=dev_id, force_play=True)
        return dev_id

    def is_playing(self):
        cur_playing = self.client.currently_playing()
        playing = cur_playing.get('is_playing', False) if cur_playing else False
        return playing

    def get_shuffle(self):
        cur_playback = self.client.current_playback()
        shuffle_state = cur_playback.get('shuffle_state', False) if cur_playback else False
        return shuffle_state

    def set_shuffle(self, state):
        self.client.shuffle(state, device_id=self.device_id())

    def play(self):
        self.client.start_playback(device_id=self.device_id())

    def skip_track(self):
        track_name = self.get_next_track_name()
        self.client.next_track(device_id=self.device_id())
        return track_name

    def restart_song(self):
        self.client.seek_track(0, self.device_id())

    def previous_track(self):
        self.client.previous_track(device_id=self.device_id())
        # play()

    def pause(self):
        self.client.pause_playback(device_id=self.device_id())

    def get_current_track_name(self):
        try:
            q = self.client.queue()
            return f"{q['currently_playing']['name']} by {q['currently_playing']['artists'][0]['name']}"

        except Exception as e:
            print(e)
            return None

    def get_next_track_name(self):
        try:
            q = self.client.queue()
            return f"{q['queue'][0]['name']} by {q['queue'][0]['artists'][0]['name']}"

        except Exception as e:
            print(e)
            return None
