import spotipy
from spotipy.oauth2 import SpotifyOAuth
from utils import api

api_config = api.apis.get('spotify')
acc_key = api_config['client_key']
priv_key = api_config['priv_key']

scope = "user-read-playback-state,user-modify-playback-state,streaming"


def sp():
    return spotipy.Spotify(
        client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))


def device_id():
    sp = spotipy.Spotify(
        client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))
    devices = sp.devices()
    active_devices = [d for d in devices['devices'] if d['is_active']]
    if len(active_devices) == 0: return None
    dev_id = active_devices[0]['id']
    return dev_id


def has_active_device():
    return device_id() is not None


def switch_to_smartphone_device():
    sp = spotipy.Spotify(
        client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))
    devices = sp.devices()
    smartphone_devices = [d for d in devices['devices'] if d['type'] == 'Smartphone']
    if len(smartphone_devices) == 0: return None

    dev_id = smartphone_devices[0]['id']
    sp.transfer_playback(device_id=dev_id, force_play=True)
    return dev_id


def switch_to_desktop_device():
    sp = spotipy.Spotify(
        client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))
    devices = sp.devices()
    desktop_devices = [d for d in devices['devices'] if d['type'] == 'Computer']
    if len(desktop_devices) == 0: return None

    dev_id = desktop_devices[0]['id']
    sp.transfer_playback(device_id=dev_id, force_play=True)
    return dev_id


def is_playing():
    sp = spotipy.Spotify(
        client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))
    cur_playing = sp.currently_playing()
    playing = cur_playing.get('is_playing', False) if cur_playing else False
    return playing


def get_shuffle():
    sp = spotipy.Spotify(
        client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))
    cur_playback = sp.current_playback()
    shuffle_state = cur_playback.get('shuffle_state', False) if cur_playback else False
    return shuffle_state


def set_shuffle(state):
    sp = spotipy.Spotify(
        client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))
    sp.shuffle(state, device_id=device_id())


def play():
    sp = spotipy.Spotify(
        client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))
    sp.start_playback(device_id=device_id())


def skip_track():
    sp = spotipy.Spotify(
        client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))
    track_name = get_next_track_name()
    sp.next_track(device_id=device_id())
    # play()
    return track_name


def restart_song():
    sp = spotipy.Spotify(
        client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))
    sp.seek_track(0, device_id())
    # play()


def previous_track():
    sp = spotipy.Spotify(
        client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))
    sp.previous_track(device_id=device_id())
    # play()


def pause():
    sp = spotipy.Spotify(
        client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))
    sp.pause_playback(device_id=device_id())


def get_current_track_name():
    try:
        sp = spotipy.Spotify(
            client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))
        q = sp.queue()
        return f"{q['currently_playing']['name']} by {q['currently_playing']['artists'][0]['name']}"

    except Exception as e:
        print(e)
        return None


def get_next_track_name():
    try:
        sp = spotipy.Spotify(
            client_credentials_manager=SpotifyOAuth(acc_key, priv_key, redirect_uri='http://127.0.0.1:9090', scope=scope))
        q = sp.queue()
        return f"{q['queue'][0]['name']} by {q['queue'][0]['artists'][0]['name']}"

    except Exception as e:
        print(e)
        return None
