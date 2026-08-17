import requests

def get_pairs():
    response = requests.get('https://capi.coinglass.com/api/support/symbol')
    data = response.json()['data']
    return [f'{item}/USDT' for item in data]

