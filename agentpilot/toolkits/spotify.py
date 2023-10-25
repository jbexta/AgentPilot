import spotipy
from spotipy.oauth2 import SpotifyOAuth
from agentpilot.utils import api

api_config = api.apis.get('spotify')
acc_key = api_config['client_key']
priv_key = api_config['priv_key']

scope = "user-read-playback-state,user-modify-playback-state,streaming"

spotify_client = None

if priv_key:
    spotify_client = spotipy.Spotify(client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))


def device_id():
    devices = spotify_client.devices()
    active_devices = [d for d in devices['devices'] if d['is_active']]
    if len(active_devices) == 0: return None
    dev_id = active_devices[0]['id']
    return dev_id


def has_active_device():
    return device_id() is not None


def switch_to_smartphone_device():
    devices = spotify_client.devices()
    smartphone_devices = [d for d in devices['devices'] if d['type'] == 'Smartphone']
    if len(smartphone_devices) == 0: return None

    dev_id = smartphone_devices[0]['id']
    spotify_client.transfer_playback(device_id=dev_id, force_play=True)
    return dev_id


def switch_to_desktop_device():
    devices = spotify_client.devices()
    desktop_devices = [d for d in devices['devices'] if d['type'] == 'Computer']
    if len(desktop_devices) == 0: return None

    dev_id = desktop_devices[0]['id']
    spotify_client.transfer_playback(device_id=dev_id, force_play=True)
    return dev_id


def is_playing():
    cur_playing = spotify_client.currently_playing()
    playing = cur_playing.get('is_playing', False) if cur_playing else False
    return playing


def get_shuffle():
    cur_playback = spotify_client.current_playback()
    shuffle_state = cur_playback.get('shuffle_state', False) if cur_playback else False
    return shuffle_state


def set_shuffle(state):
    spotify_client.shuffle(state, device_id=device_id())


def play():
    spotify_client.start_playback(device_id=device_id())


def skip_track():
    track_name = get_next_track_name()
    spotify_client.next_track(device_id=device_id())
    return track_name


def restart_song():
    spotify_client.seek_track(0, device_id())


def previous_track():
    spotify_client.previous_track(device_id=device_id())
    # play()


def pause():
    spotify_client.pause_playback(device_id=device_id())


def get_current_track_name():
    try:
        q = spotify_client.queue()
        return f"{q['currently_playing']['name']} by {q['currently_playing']['artists'][0]['name']}"

    except Exception as e:
        print(e)
        return None


def get_next_track_name():
    try:
        q = spotify_client.queue()
        return f"{q['queue'][0]['name']} by {q['queue'][0]['artists'][0]['name']}"

    except Exception as e:
        print(e)
        return None
