# Toothy
A Discord bot platform, powered by discord.py commands extension.

To run you need:
 * [Python](https://www.python.org/downloads/)
 * [MongoDB](https://www.mongodb.com/try/download/community) running

## Setup

### Toothy
``` bash
# Make a directory for virtual environments
mkdir ~/.venvs

# Make a virtual environment for Toothy
py -m venv ~/.venvs/toothyenv

# Activate the new Toothy virtual environment
source ~/.venvs/toothyenv/bin/activate # POSIX
source ~/.venvs/toothyenv/Scripts/activate # Windows

# Install dependencies
pip install -r requirements.txt

# Make a copy of the example config file and name it "config.json"
cp ./settings/config-example.json ./settings/config.json
```

### Discord
1. Login to [Discord Developer Portal](https://discord.com/developers/applications) and click "New Application".

2. After creating a new application, go to the Bot tab and click the *Add Bot* button.  
    * Save the ***Bot Token*** because you will need it in Step 4.  
    * Save the ***Application ID*** because you will need it in Step 5.

3. Scroll down to the *Privileged Gateway Intents* section and enable all privileged intents, then save changes.

4. Edit your `config.json` file:  
    * Copy the ***Bot Token*** from Step 2 into the **TOKEN** field.  
    * Copy your ***Discord User ID*** into the **OWNER_ID** field.  
    * Copy your ***Discord Server ID*** into the **TEST_GUILD** field.  
  *Help: [How to get Discord IDs](https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID-)*

5. Invite your newly created bot to your Discord server by copying the following URL into a browser:  
  (Replace `YOUR_BOT_APPLICATION_ID` with the ***Application ID*** from Step 2)  
  ```
  https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_APPLICATION_ID&permissions=939879488&scope=bot%20applications.commands
  ```

6. After your bot joins your Discord server, make sure the bot has all of the necessary read/write persmissions in all of the applicable channels ***(double check channel overrides)***

### GW2Bot
To use Toothy with [GW2Bot](https://github.com/Maselkov/GW2Bot), just follow the [GW2Bot setup instructions](https://github.com/Maselkov/GW2Bot/blob/master/README.md).

## Run
``` bash
# Activate the Toothy virtual environment
source ~/.venvs/toothyenv/bin/activate # POSIX
source ~/.venvs/toothyenv/Scripts/activate # Windows

# Run Toothy
py run.py
```