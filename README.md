# BinEx Bot

This is a [Telegram](https://telegram.org/) bot for the "Binary Exploitation" lab course at TUM (Technical University of Munich) that sends you a message whenever the pwning leaderboard changes. I wrote it in 2018 when I did the lab course.

To use the bot visit <https://telegram.me/binex_bot> and send it any message. It will acknowledge your existence with a "Hello" and send you updates when new pwns happen.

The bot is hosted for free on *Heroku* and uses *Google Docs* as a free mini-database.

## Deployment to Heroku
1. Add config vars:
    - BOT_TOKEN
    - GOOGLE_API_PRIVATE_KEY_ID
    - GOOGLE_API_PRIVATE_KEY_BASE64
    - GOOGLE_API_CLIENT_EMAIL
    - GOOGLE_API_CLIENT_ID
    - MAINTAINER_CHAT_ID (optional)
2. Deploy from github
3. Start `worker` dyno
