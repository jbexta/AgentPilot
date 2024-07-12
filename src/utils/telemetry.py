from posthog import Posthog

# from src.utils.security import decrypt_string

# from src.utils.security import xor_encrypt_decrypt

posthog = None
my_uuid = ''
enabled = True


def initialize():
    global posthog
    # e_key = "unMmEp1XrAwxfPO7uCY3WhZp8i//nJ1wYdqtFfohoJjSlJrz4+zAGrD2FIPSlaHq2Q16ZDZteCvh7PzhBZTsMQ=="
    # decrypt_string(e_key, "DxomyewkFd")  # Just to avoid plaintext in github, not sensitive
    key = 'phc_JIasLtRWye7WuvbM5bwZE5BbNdVABvoTtGJtQ3ESenA'
    posthog = Posthog(project_api_key=key, host='https://eu.i.posthog.com')


def set_uuid(uuid):
    global my_uuid
    my_uuid = uuid


def send(event, properties=None):
    global posthog, my_uuid, enabled
    if posthog is None:
        return
    if not enabled:
        return
    dev_uuids = [
        'd6b60f89-be9f-4ab9-ac55-7102a53401e5',
    ]
    if my_uuid in dev_uuids:
        return

    properties = properties or {}
    posthog.capture(my_uuid, event, properties)
