#!/usr/bin/env python3

import base64
import emoji
import gspread
import os
import re
import requests
import sys
import telepot
import time

from oauth2client.service_account import ServiceAccountCredentials
from telepot.loop import MessageLoop


CHATS_FILE = "chats.txt"
TOKEN_FILE = "token.txt"
GOOGLE_CREDENTIALS_FILE = "google_api_secret.json"
GOOGLE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1GDAj4AEgSfJW_sxoyMCEKNiu650t6Jr0ul_lRFz6Q84"
SCOREBOARD_URL = "https://pwning.sec.in.tum.de/t"


def get_bot_token():
    token = os.environ.get("BOT_TOKEN", None)
    if token:
        return token
    if len(sys.argv) > 1:
        return sys.argv[1]
    if not os.path.isfile(TOKEN_FILE):
        print("No bot token found")
        exit(1)
    with open(TOKEN_FILE) as f:
        for line in f:
            return line.rstrip()


def get_scoreboard():
    scoreboard = requests.get(SCOREBOARD_URL).text
    scoreboard = re.sub(r"\x1b\[3?\dm", "", scoreboard) # Remove colors
    scoreboard = scoreboard[scoreboard.find("Last Pwns:")+len("Last Pwns:\n"):]

    news, scores, *_ = scoreboard.split("\n\nScores:\n")
    news_cleaned = []
    for entry in news.split("\n"):
        news_cleaned.append(entry.split(": "))

    scores = scores.split("\n")
    scores_cleaned = []
    for s in scores:
        if not s:
            continue
        scores_cleaned.append([x for x in s.split(" ") if x])
    return news_cleaned, scores_cleaned


class Storage:
    def __init__(self):
        self.credentials = self._get_credentials()
        self._sheet = None
        self.last_login = 0

    def _get_credentials(self):
        scope = ("https://spreadsheets.google.com/feeds",)

        if os.path.isfile(GOOGLE_CREDENTIALS_FILE):
            return ServiceAccountCredentials.from_json_keyfile_name("google_api_secret.json", scope)
        else:
            private_key_id = os.environ.get("GOOGLE_API_PRIVATE_KEY_ID", None)
            private_key_base64 = os.environ.get("GOOGLE_API_PRIVATE_KEY_BASE64", None)
            client_email = os.environ.get("GOOGLE_API_CLIENT_EMAIL", None)
            client_id = os.environ.get("GOOGLE_API_CLIENT_ID", None)

            if not all((private_key_id, private_key_base64, client_email, client_id)):
                raise Exception("No Google API credentials found")

            return ServiceAccountCredentials.from_json_keyfile_dict({
                    "type": "service_account",
                    "private_key_id": private_key_id,
                    "private_key": base64.b64decode(private_key_base64),
                    "client_email": client_email,
                    "client_id": client_id
                }, scope)

    @property
    def sheet(self):
        now = time.time()
        if now - self.last_login > 3500:
            self.last_login = now
            client = gspread.authorize(self.credentials)
            self._sheet = client.open_by_url(GOOGLE_SHEETS_URL).sheet1
        return self._sheet

    def load_chats(self):
        return [int(x) for x in self.sheet.col_values(1)]

    def add_chat(self, chat_id):
        next_row = len(self.sheet.col_values(1)) + 1
        self.sheet.update_cell(next_row, 1, chat_id)
    
    def _get_row(self, key):
        keys = self.sheet.col_values(2)
        if key not in keys:
            return None
        return keys.index(key) + 1

    def set(self, key, value):
        row = self._get_row(key)
        if row:
            self.sheet.update_cell(row, 3, value)
        else:
            row = len(self.sheet.col_values(2)) + 1
            self.sheet.update_cell(row, 2, key)
            self.sheet.update_cell(row, 3, value)

    def get(self, key):
        row = self._get_row(key)
        if row:
            return self.sheet.cell(row, 3).value
        return None


class BxBot:
    def __init__(self):
        self.token = get_bot_token()
        self.bot = telepot.Bot(self.token)

        try:
            self.storage = Storage()
            self.chats = self.storage.load_chats()
            self.last_pwn_time = self.storage.get("last_pwn_time")
            self.last_rank = str(self.storage.get("last_rank"))
        except Exception as e:
            print(e, file=sys.stderr)
            self.send_debug(str(e), "error")
            exit(1)
        
        self.maintainer_chat_id = os.environ.get("MAINTAINER_CHAT_ID", None)
        MessageLoop(self.bot, self.handle).run_as_thread()

        print("Bot started")
        self.send_debug("Bot started")
    
    def loop(self, time_between_updates=600):
        try:
            while True:
                self.update()
                time.sleep(time_between_updates)
        except Exception as e:
            self.send_debug(str(e), "error")
            raise

    def send_debug(self, msg, msg_type="debug"):
        type_prefix = {
            "debug": ":construction:",
            "warning": ":warning",
            "error": ":x:ERROR"
        }
        if self.maintainer_chat_id:
            if msg_type in type_prefix:
                msg = type_prefix[msg_type] + " " + msg
            self.bot.sendMessage(int(self.maintainer_chat_id), emoji.emojize(msg))
    
    def send_all(self, msg):
        print("Sending to", len(self.chats), "chats")
        for chat in self.chats:
            self.bot.sendMessage(chat, msg)
            time.sleep(1)

    def update(self):
        news, scores = get_scoreboard()
        updates = []

        for time, headline in news:
            if time == self.last_pwn_time:
                break
            else:
                updates.insert(0, headline)
        if updates:
            self.last_pwn_time = news[0][0]
            self.storage.set("last_pwn_time", self.last_pwn_time)
            self.send_all("\n".join(updates))

        for row in scores:
            if row[1] == "Team" and row[2] == "0xCD" and row[0] != self.last_rank:
                smiley = ":)" if row[0] < self.last_rank else ":("
                self.send_all("Team 0xCD's rank changed from {} to {} {}".format(self.last_rank, row[0], smiley))
                self.last_rank = row[0]
                self.storage.set("last_rank", self.last_rank)
                
    def handle(self, msg):
        content_type, _, chat_id = telepot.glance(msg)

        if content_type == "text":
            user = msg["chat"].get("username", chat_id)
            if chat_id not in self.chats:
                print("New user:", user)
                self.send_debug(":eight_spoked_asterisk: New user: " + user, None)
                self.chats.append(chat_id)
                self.bot.sendMessage(chat_id, "Hello!")
                self.storage.add_chat(chat_id)
            else:
                print(user, "asked if I'm still here")
                self.bot.sendMessage(chat_id, "Yes, I'm still here!")


BxBot().loop()
