from src.utils.zzzapis import awspolly


def sync_all():
    awspolly.sync_polly()
    # uberduck.sync_uberduck()
    # fakeyou.sync_fakeyou()
    # elevenlabs.sync_elevenlabs()
