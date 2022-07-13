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
  Save the ***Bot Token*** because you will need it in step 4.  
  Also save the ***Application ID*** because you will need it in step 5.

3. Scroll down to the *Privileged Gateway Intents* section and enable all privileged intents, then save changes.

4. Now copy the ***Bot Token*** from step 2 into the *TOKEN* field of your `config.json` file.

5. Invite your newly created bot to your Discord server by copying the following URL into a browser:  
  (Replace `YOUR_BOT_APPLICATION_ID` with the ***Application ID*** from step 2)  
  ```
  https://discord.com/api/oauth2/authorize?client_id=YOUR_BOT_APPLICATION_ID&permissions=939879488&scope=bot%20applications.commands
  ```

6. After your bot joins your Discord server, make sure the bot has all of the necessary read/write persmissions in all of the applicable channels *(double check channel overrides)*

7. Finally, copy your ***Discord Server ID*** into the *TEST_GUILD* field of your `config.json` file.  
  Help: [How to get Discord server ID](https://support.discord.com/hc/en-us/articles/206346498-Where-can-I-find-my-User-Server-Message-ID-)

### GW2Bot
To use Toothy with [GW2Bot](https://github.com/Maselkov/GW2Bot), just clone the GW2Bot repo to the `cogs` directory and install dependencies:
``` bash
git clone https://github.com/Maselkov/GW2Bot.git ./cogs

# Go to cogs directory
cd cogs

# Activate the Toothy virtual environment
source ~/.venvs/toothyenv/bin/activate # POSIX
source ~/.venvs/toothyenv/Scripts/activate # Windows

# Install GW2Bot dependencies
pip install -r requirements.txt
```

## Run
``` bash
# Activate the Toothy virtual environment
source ~/.venvs/toothyenv/bin/activate # POSIX
source ~/.venvs/toothyenv/Scripts/activate # Windows

# Run Toothy
py run.py
```