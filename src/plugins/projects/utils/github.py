import asyncio
import json
import os

import aiohttp
import keyring
from keyring.errors import KeyringError, PasswordDeleteError

CLIENT_ID = os.environ.get('AP_GITHUB_CLIENT_ID', 'Ov23liVq5Tg3Ki5qjSYd')
SCOPES = 'repo workflow'
KEYRING_SERVICE = 'agentpilot'
KEYRING_USER = 'github'


async def _post(url, data):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, data=data, headers={'Accept': 'application/json'},
        ) as response:
            response.raise_for_status()
            return await response.json()


async def request_device_code():
    """Start a sign-in. Returns GitHub's `user_code`, `verification_uri`,
    `device_code` and `interval`."""
    return await _post(
        'https://github.com/login/device/code',
        {'client_id': CLIENT_ID, 'scope': SCOPES},
    )


async def poll_token(device_code, interval):
    """Wait until the user approves the sign-in, and return the token."""
    while True:
        await asyncio.sleep(interval)
        result = await _post('https://github.com/login/oauth/access_token', {
            'client_id': CLIENT_ID,
            'device_code': device_code,
            'grant_type': 'urn:ietf:params:oauth:grant-type:device_code',
        })
        error = result.get('error')
        if error == 'authorization_pending':
            continue
        if error == 'slow_down':
            interval = result.get('interval', interval + 5)
            continue
        if error:
            raise RuntimeError(result.get('error_description', error))
        return result['access_token']


async def _api(method, path, token, json=None):
    """Call the GitHub REST API, raising GitHub's message on failure."""
    async with aiohttp.ClientSession() as session:
        async with session.request(
            method, f'https://api.github.com{path}', json=json,
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/vnd.github+json',
            },
        ) as response:
            data = await response.json()
            if response.status >= 400:
                errors = data.get('errors') or [{}]
                raise RuntimeError(
                    errors[0].get('message') or data.get('message')
                    or f'GitHub returned {response.status}')
            return data


async def get_login(token):
    return (await _api('GET', '/user', token))['login']


async def get_identity(token):
    """A (name, email) for commits, using GitHub's private noreply email."""
    user = await _api('GET', '/user', token)
    email = f"{user['id']}+{user['login']}@users.noreply.github.com"
    return user['name'] or user['login'], email


async def create_repo(token, name, description, private):
    """Create a repo on the signed in account, and return its clone URL."""
    data = await _api('POST', '/user/repos', token, json={
        'name': name, 'description': description, 'private': private,
    })
    return data['clone_url']


async def get_account():
    """The signed in `{'token', 'login'}`, or None."""
    try:
        value = await asyncio.to_thread(
            keyring.get_password, KEYRING_SERVICE, KEYRING_USER)
    except KeyringError:
        return None
    return json.loads(value) if value else None


async def get_token():
    account = await get_account()
    return account['token'] if account else None


async def sign_in(token):
    """Save the account for `token`, and return its login."""
    login = await get_login(token)
    value = json.dumps({'token': token, 'login': login})
    await asyncio.to_thread(
        keyring.set_password, KEYRING_SERVICE, KEYRING_USER, value)
    return login


async def sign_out():
    try:
        await asyncio.to_thread(
            keyring.delete_password, KEYRING_SERVICE, KEYRING_USER)
    except PasswordDeleteError:
        pass
