import hashlib
import hmac
import base64
import time
import os
import json
from urllib.parse import urlencode

import requests


def get_depwith():
    """
    Fetch deposit and withdrawal history from Poloniex.

    Returns
    -------
    list of dict
        Each dict has keys: unix, type, asset, amt, status.
    """
    os.environ['POLO_API_KEY'] = ''
    os.environ['POLO_API_SECRET'] = ''
    # os.environ['POLO_API_KEY'] = ''
    # os.environ['POLO_API_SECRET'] = ''
    api_key = os.environ['POLO_API_KEY']
    api_secret = os.environ['POLO_API_SECRET']

    now_ms = str(int(time.time() * 1000))
    params = {
        'start': '0',
        'end': str(int(time.time() * 1000)),
        'signTimestamp': now_ms,
    }
    sorted_params = urlencode(sorted(params.items()))

    method = 'GET'
    path = '/wallets/activity'
    sign_payload = f"{method}\n{path}\n{sorted_params}"

    signature = base64.b64encode(
        hmac.new(
            api_secret.encode('utf-8'),
            sign_payload.encode('utf-8'),
            hashlib.sha256,
        ).digest()
    ).decode('utf-8')

    headers = {
        'key': api_key,
        'signTimestamp': now_ms,
        'signatureMethod': 'HmacSHA256',
        'signatureVersion': '2',
        'signature': signature,
    }

    query_params = urlencode(sorted(
        {k: v for k, v in params.items() if k != 'signTimestamp'}.items()
    ))
    url = f"https://api.poloniex.com{path}?{query_params}"
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    data = resp.json()

    results = []
    for d in data.get('deposits', []):
        results.append({
            'unix': d['timestamp'],
            'type': 'DEPOSIT',
            'asset': d['currency'],
            'amt': d['amount'],
            'status': d['status'],
        })
    for w in data.get('withdrawals', []):
        results.append({
            'unix': w['timestamp'],
            'type': 'WITHDRAWAL',
            'asset': w['currency'],
            'amt': w['amount'],
            'status': w['status'],
        })

    return results
