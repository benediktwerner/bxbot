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

from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from oauth2client.service_account import ServiceAccountCredentials
from telepot.loop import MessageLoop


TIME_BETWEEN_RESTARTS = 300
TIME_BETWEEN_UPDATES = 600
TOKEN_FILE = "token.txt"
GOOGLE_CREDENTIALS_FILE = "google_api_secret.json"
GOOGLE_SHEETS_URL = "https://docs.google.com/spreadsheets/d/1GDAj4AEgSfJW_sxoyMCEKNiu650t6Jr0ul_lRFz6Q84"
SCOREBOARD_URL = "https://leeting.sec.in.tum.de/"
SCOREBOARD_TERMINAL_URL = "https://leeting.sec.in.tum.de/t"
TIME_UNITS = {"s": 1, "m": 60, "h": 60 * 60}


def time_str_to_int(s):
    result = 0

    for p in s.split(" "):
        if p in ("day", "days"):
            continue
        elif p[-1] not in TIME_UNITS:
            result += int(p) * 60 * 60 * 24
        else:
            result += int(p[:-1]) * TIME_UNITS[p[-1]]

    return result


def time_int_to_str(i):
    delta = timedelta(seconds=i)
    mins, secs = divmod(delta.seconds, 60)
    hours, mins = divmod(mins, 60)
    return f"{delta.days:3}:{hours:02}:{mins:02}:{secs:02}"


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


def get_maintainer_chat_id():
    chat_id = os.environ.get("MAINTAINER_CHAT_ID")
    if chat_id is None:
        return None
    return int(chat_id)


def get_scoreboard():
    scoreboard = requests.get(SCOREBOARD_TERMINAL_URL).text
    scoreboard = re.sub(r"\x1b\[3?\dm", "", scoreboard)  # Remove colors
    scoreboard = scoreboard[scoreboard.find("Last Pwns:") + len("Last Pwns:\n") :]

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


def get_times():
    now = datetime.now()
    soup = BeautifulSoup(requests.get(SCOREBOARD_URL).text, "html.parser")

    teams = {}
    task_times = {}

    tasks_table = soup.findAll("table")[1]
    for task_row in tasks_table.tbody.findAll("tr"):
        cols = task_row.findAll("td")
        task_name = cols[0].text
        if not task_name.startswith("pwn"):
            continue
        task_name = task_name[3:]
        task_start = datetime.strptime(cols[2].text, "%Y-%m-%d %H:%M:%S")
        task_times[task_name] = int((now - task_start).total_seconds())

    score_table = soup.find("table", id="scores")
    task_names = list(map(lambda c: c.text, score_table.thead.tr.findAll("th")[2:]))

    for row in score_table.tbody.findAll("tr"):
        cols = row.findAll("td")
        team_name = cols[1].text
        total_time = 0

        for i, task in enumerate(cols[2:-1]):
            if task_names[i] not in task_times:
                continue
            if task.span.has_attr("class") and "solved" in task.span.attrs["class"]:
                total_time += time_str_to_int(task.span.attrs["title"])
            else:
                total_time += task_times[task_names[i]]

        teams[team_name] = total_time

    result = []
    for team_name, total_time in sorted(teams.items(), key=lambda x: x[1]):
        result.append(f"{team_name:20}{time_int_to_str(total_time)}")
    return "```" + "\n".join(result) + "```"


class Storage:
    CHATS_COL = 1
    DATA_KEY_COL = 2
    DATA_VAL_COL = DATA_KEY_COL + 1
    MSG_COL = 4

    def __init__(self):
        self.credentials = self._get_credentials()
        self._sheet = None
        self.last_login = 0

    def _get_credentials(self):
        scope = ("https://spreadsheets.google.com/feeds",)

        if os.path.isfile(GOOGLE_CREDENTIALS_FILE):
            return ServiceAccountCredentials.from_json_keyfile_name(
                GOOGLE_CREDENTIALS_FILE, scope
            )
        else:
            private_key_id = os.environ.get("GOOGLE_API_PRIVATE_KEY_ID", None)
            private_key_base64 = os.environ.get("GOOGLE_API_PRIVATE_KEY_BASE64", None)
            client_email = os.environ.get("GOOGLE_API_CLIENT_EMAIL", None)
            client_id = os.environ.get("GOOGLE_API_CLIENT_ID", None)

            if not all((private_key_id, private_key_base64, client_email, client_id)):
                raise Exception("No Google API credentials found")

            return ServiceAccountCredentials.from_json_keyfile_dict(
                {
                    "type": "service_account",
                    "private_key_id": private_key_id,
                    "private_key": base64.b64decode(private_key_base64),
                    "client_email": client_email,
                    "client_id": client_id,
                },
                scope,
            )

    @property
    def sheet(self):
        now = time.time()
        if now - self.last_login > 3500:
            self.last_login = now
            client = gspread.authorize(self.credentials)
            self._sheet = client.open_by_url(GOOGLE_SHEETS_URL).sheet1
        return self._sheet

    def load_chats(self):
        return [int(x) for x in self.sheet.col_values(self.CHATS_COL) if x]

    def add_chat(self, chat_id):
        col = self.sheet.col_values(self.CHATS_COL)
        if all(col):
            next_row = len(self.sheet.col_values(self.CHATS_COL)) + 1
        else:
            next_row = col.index("") + 1
        self.sheet.update_cell(next_row, self.CHATS_COL, chat_id)

    def remove_chat(self, chat_id):
        col = self.sheet.col_values(self.CHATS_COL)
        if str(chat_id) in col:
            row = col.index(str(chat_id)) + 1
            self.sheet.update_cell(row, self.CHATS_COL, "")

    def _get_row(self, key, col=None):
        keys = self.sheet.col_values(col if col is not None else self.DATA_KEY_COL)
        if key not in keys:
            return None
        return keys.index(key) + 1

    def set(self, key, value):
        row = self._get_row(key)
        if row:
            self.sheet.update_cell(row, self.DATA_VAL_COL, value)
        else:
            row = len(self.sheet.col_values(self.DATA_KEY_COL)) + 1
            self.sheet.update_cell(row, self.DATA_KEY_COL, key)
            self.sheet.update_cell(row, self.DATA_VAL_COL, value)

    def get(self, key):
        row = self._get_row(key)
        if row:
            return self.sheet.cell(row, self.DATA_VAL_COL).value
        return None

    def save_msg(self, user, text):
        row = len(self.sheet.col_values(self.MSG_COL)) + 1
        self.sheet.update_cell(row, self.MSG_COL, user)
        self.sheet.update_cell(row, self.MSG_COL + 1, text)


class BxBot:
    def __init__(self):
        self.token = get_bot_token()
        self.bot = telepot.Bot(self.token)

        try:
            self.storage = Storage()
            self.chats = self.storage.load_chats()
            self.last_pwn_time = self.storage.get("last_pwn_time")
        except Exception as e:
            print(e, file=sys.stderr)
            self.send_debug(str(e), "error")
            exit(1)

        self.maintainer_chat_id = get_maintainer_chat_id()
        MessageLoop(self.bot, self.handle).run_as_thread()

        print("Bot started")
        self.send_debug("Bot started")

    def run(self):
        while True:
            try:
                self.loop()
            except KeyboardInterrupt:
                print("Interrupted by User. Exiting ...")
                return
            except Exception as e:
                msg = f"Caught an exception: {type(e).__name__} {e}"
                print(msg)
                self.send_debug(msg, "error")
                time.sleep(TIME_BETWEEN_RESTARTS)

    def loop(self):
        while True:
            self.update()
            time.sleep(TIME_BETWEEN_UPDATES)

    def send_debug(self, msg, msg_type="debug"):
        type_prefix = {
            "debug": ":construction:",
            "warning": ":warning:",
            "error": ":x:ERROR",
        }
        if self.maintainer_chat_id is not None:
            if msg_type in type_prefix:
                msg = type_prefix[msg_type] + " " + msg
            msg = emoji.emojize(msg, use_aliases=True)
            self.bot.sendMessage(self.maintainer_chat_id, msg)

    def send_all(self, msg):
        print("Sending to", len(self.chats), "chats")
        for chat in self.chats:
            try:
                self.bot.sendMessage(chat, msg)
            except telepot.exception.BotWasBlockedError:
                self.remove_chat(chat)
            except telepot.exception.TelegramError as e:
                if (
                    len(e.args) == 3
                    and e.args[0] == "Forbidden: user is deactivated"
                    and e.args[1] == 403
                ):
                    self.remove_chat(chat)
                else:
                    raise
            time.sleep(1)

    def remove_chat(self, chat):
        self.storage.remove_chat(chat)
        self.chats.remove(chat)
        self.send_debug(f":door: User left: {chat}", None)

    def update(self):
        news, _ = get_scoreboard()
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

    def handle(self, msg):
        content_type, _, chat_id = telepot.glance(msg)

        if content_type == "text":
            user = msg["chat"].get("username", str(chat_id))
            if chat_id not in self.chats:
                print("New user:", user)
                self.send_debug(
                    f":eight_spoked_asterisk: New user: {user}\n{msg['text']}", None
                )
                self.chats.append(chat_id)
                self.bot.sendMessage(chat_id, "Hello!")
                self.storage.add_chat(chat_id)
            elif msg["text"] == "/times":
                self.bot.sendMessage(chat_id, get_times())
                return
            else:
                print(user, "asked if I'm still here")
                self.bot.sendMessage(chat_id, "Yes, I'm still here!")
            self.storage.save_msg(user, msg["text"])


if __name__ == "__main__":
    BxBot().run()
