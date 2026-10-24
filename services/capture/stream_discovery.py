"""Find live MapleStory streams using the Twitch API."""

import os
import json
from urllib.request import Request, urlopen
from urllib.parse import urlencode


CLIENT_ID = os.environ["TWITCH_CLIENT_ID"]
CLIENT_SECRET = os.environ["TWITCH_CLIENT_SECRET"]


def get_access_token():
    url = "https://id.twitch.tv/oauth2/token"
    request = Request(url,urlencode({
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "client_credentials",
        }).encode())
    with urlopen(request) as response:
        result = json.load(response)
    return result["access_token"]


def fetch_data(endpoint, params, token):
    url = f"https://api.twitch.tv/helix/{endpoint}?{urlencode(params)}"
    request = Request(url, headers={
        "Client-Id": CLIENT_ID,
        "Authorization": f"Bearer {token}",
    })
    with urlopen(request) as response:
        return json.load(response)


def discover_streams():
    token = get_access_token()
    # find maplestory game id
    result = fetch_data("games", {"name": "MapleStory"}, token)

    if not result["data"]:
        return []

    game_id = result["data"][0]["id"]

    # fetch 50 streams
    result = fetch_data("streams", {
        "game_id": game_id,
        "first": 50,
    }, token)

    channels = []

    for stream in result["data"]:
        channels.append(stream["user_login"])

    return channels