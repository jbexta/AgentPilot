from openagent.utils.apis import awspolly
import pyttsx3


def sync_all():
    awspolly.sync_polly()
    # uberduck.sync_uberduck()
    # fakeyou.sync_fakeyou()
    # elevenlabs.sync_elevenlabs()


engine = pyttsx3.init()
voices = engine.getProperty('voices')
engine.setProperty('voice', voices[13].id)


def tts(text):
    pyttsx3.speak(text)
