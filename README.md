# Toothy
A Discord bot platform, powered by discord.py commands extension.

To run you need:
 * [Python](https://www.python.org/downloads/)
 * [MongoDB](https://www.mongodb.com/try/download/community) running

## Setup

### Python
``` bash
# Install dependencies
pip install -r requirements.txt
```

### Discord
1. Login to [Discord Developer Portal](https://discord.com/developers/applications) and click "New Application".

1. After creating a new application, go to the *Bot* tab and click the *Add Bot* button.  
  Save the ***Bot Token*** because you will need it in step 4.  
  Also save the ***Application ID*** because you will need it in step 5.

1. Scroll down to the *Privileged Gateway Intents* section and enable all privileged intents, then save changes.

1. Now copy the ***Bot Token*** from step 2 into the *TOKEN* field of `/settings/config.json` file.

1. Invite your newly created bot to your Discord server by copying the following URL into a browser:  
  ```  
  https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_APPLICATION_ID&permissions=939879488&scope=bot%20applications.commands  
  ```  
  (Replacing `YOUR_BOT_APPLICATION_ID` with the ***Application ID*** from step 2)

1. After your bot joins your Discord server, make sure the bot has all of the necessary read/write persmissions in all of the applicable channels *(double check channel overrides)*

1. Finally, copy your ***Discord Server ID*** into the *DEBUG_GUILD* field of `/settings/config.json` file.  
  Help: [How to get Discord server ID](https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID-)

### GW2Bot
To use Toothy with [GW2Bot](https://github.com/Maselkov/GW2Bot), just clone the GW2Bot repo to the `cogs` directory:
``` bash
git clone https://github.com/Maselkov/GW2Bot.git ./cogs
```

## Run
``` bash
py run.py
```