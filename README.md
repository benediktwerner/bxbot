# BinEx Bot

To use the bot visit <https://telegram.me/binex_bot> and send it any message. It will acknowledge your existence with a "Hello" and send you updates when new pwns happen.

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
