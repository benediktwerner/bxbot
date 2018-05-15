#!/usr/bin/env python3

import os
import re
import requests
import sys
import telepot
import time

from telepot.loop import MessageLoop


CHATS_FILE = "chats.txt"
TOKEN_FILE = "token.txt"
LOG_FILE = "log.txt"


def get_bot_token():
    token = os.environ.get("BOT_TOKEN", None)
    if token:
        return token
    if len(sys.argv) > 1:
        return sys.argv[1]
    if not os.path.isfile(TOKEN_FILE):
        log("No bot token found")
        exit(1)
    with open(TOKEN_FILE) as f:
        for line in f:
            return line.rstrip()


def log(*text):
    with open(LOG_FILE, "a") as f:
        print("[{}]".format(time.ctime()), " ".join(text), file=f)

def get_scoreboard():
    scoreboard = requests.get("https://pwning.sec.in.tum.de/t").text
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


class BxBot:
    def __init__(self):
        self.load_chats()
        self.last_pwn_time = None
        self.token = get_bot_token()
        self.bot = telepot.Bot(self.token)
        self.last_rank = "1"
        MessageLoop(self.bot, self.handle).run_as_thread()
        log("Bot started")
    
    def load_chats(self):
        self.chats = []
        if not os.path.isfile(CHATS_FILE):
            return
        with open(CHATS_FILE) as f:
            for line in f:
                if line:
                    self.chats.append(int(line.rstrip()))
    
    def save_chats(self):
        with open(CHATS_FILE, "w") as f:
            for chat in self.chats:
                print(chat, file=f)

    def loop(self, time_between_updates=600):
        while True:
            self.update()
            time.sleep(time_between_updates)
    
    def send_all(self, msg):
        log("Sending to", len(self.chats), "chats")
        for chat in self.chats:
            self.bot.sendMessage(chat, msg)
            time.sleep(1)

    def update(self):
        news, scores = get_scoreboard()
        msg = ""

        for time, headline in news:
            if self.last_pwn_time and time == self.last_pwn_time:
                break
            else:
                msg += "\n" + time + ": " + headline
        if news:
            self.last_pwn_time = news[0][0]
        if msg:
            self.send_all("New pwns:" + msg)

        for row in scores:
            if row[1] == "Team" and row[2] == "0xCD" and row[0] != self.last_rank:
                smiley = ":)" if row[0] < self.last_rank else ":("
                self.send_all("Team 0xCD's rank changed from {} to {} {}".format(self.last_rank, row[0], smiley))
                self.last_rank = row[0]
                
    def handle(self, msg):
        content_type, _, chat_id = telepot.glance(msg)

        if content_type == "text":
            if chat_id not in self.chats:
                log("New user:", msg["chat"]["username"])
                self.chats.append(chat_id)
                self.bot.sendMessage(chat_id, "Hello!")
                self.save_chats()


BxBot().loop()
