Loop Market Bot
A Telegram bot for creating, searching, and managing listings of items for sale or free in various cities.
Features

Create listings with categories, photos, prices, and geolocation.
Search for items by keyword, category, or city.
Edit or delete your listings.
Support for free items and moving kits.
Spanish-language interface with emoji support.

Prerequisites

Python 3.8+
A Telegram Bot Token (obtained from BotFather)
An Admin ID (your Telegram user ID)

Installation

Clone the repository:
git clone https://github.com/pl00mb00m/loop-market-bot.git
cd loop-market-bot


Create a virtual environment and install dependencies:
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt


Create a .env file in the root directory with the following content:
BOT_TOKEN=your_bot_token_here
ADMIN_ID=your_admin_id_here


Run the bot:
python bot.py



Deployment
To deploy on a server or hosting platform:

Ensure the .env file is properly configured.
Use a process manager like pm2 or a service like Heroku for continuous running.
Make sure the server has write permissions for user_data.json and listings.json.

Usage

/start: Start the bot and show the main menu.
🧳 Dejar objetos: Create a new listing.
🔍 Buscar objeto: Search for items by keyword,
