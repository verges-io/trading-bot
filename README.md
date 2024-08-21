# Coinbase Trading Bot

This project implements a simple trading bot for Coinbase, using RSI (Relative Strength Index) and SMA (Simple Moving Average) indicators to make trading decisions.

## Features

- Fetches market data for tradable currencies from Coinbase API
- Calculates RSI and SMA for each currency
- Identifies buy and sell opportunities based on RSI and SMA values
- Executes trades automatically
- Stores trade history and market data in a PostgreSQL database

## Requirements

- Python 3.7+
- PostgreSQL database
- Coinbase API key and secret

## Setup

1. Clone the repository:
   ```
   git clone https://github.com/verges-io/trading-bot.git
   cd trading-bot
   ```

2. Install the required Python packages:
   ```
   pip install -r requirements.txt
   ```

3. Set up your PostgreSQL database:
   - Install PostgreSQL if you haven't already
   - Create a new database for the trading bot:
     ```
     createdb coinbase_trading_bot
     ```
   - Connect to the database:
     ```
     psql coinbase_trading_bot
     ```
   - Create the necessary tables by running the following SQL commands:
     ```sql
     CREATE TABLE IF NOT EXISTS trades (
         id SERIAL PRIMARY KEY,
         timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
         symbol VARCHAR(10) NOT NULL,
         type VARCHAR(4) NOT NULL CHECK (type IN ('BUY', 'SELL')),
         amount DECIMAL(18, 8) NOT NULL,
         price DECIMAL(18, 8) NOT NULL,
         total_value DECIMAL(18, 8) NOT NULL,
         transaction_id VARCHAR(100)
     );

     CREATE TABLE market_data (
         id SERIAL PRIMARY KEY,
         symbol VARCHAR(10),
         timestamp TIMESTAMPTZ,
         price DECIMAL
     );
     ```
   - Exit the PostgreSQL prompt:
     ```
     \q
     ```

4. Set up your Coinbase API credentials:
   - Log in to your Coinbase Pro account
   - Navigate to API settings
   - Create a new API key with the necessary permissions (view, trade)
   - Make note of the API key and API secret

5. Create a `.env` file in the project root directory and add your database and Coinbase API credentials:
   ```
   POSTGRES_DB=coinbase_trading_bot
   POSTGRES_USER=your_username
   POSTGRES_PASS=your_password

   COINBASE_API_KEY_NAME=your_api_key
   COINBASE_API_PRIVATE_KEY=your_api_secret
   ```

   Make sure to replace `your_username`, `your_password`, `your_api_key`, and `your_api_secret` with your actual credentials.

## Usage

1. To run the trading bot:
   ```
   python trading-bot.py
   ```

2. To fetch and store current market data:
   ```
   python coinbase-load-data.py
   ```

It's recommended to set up a cron job or a scheduler to run `trading-bot.py` every 4 hours and `coinbase-load-data.py` more frequently (e.g., every 15 minutes) to keep the market data up-to-date.

## Configuration

You can adjust the trading parameters in the `trading-bot.py` file:

- RSI overbought/oversold thresholds
- SMA period
- Minimum trade amounts

## Logging

The bot logs its activities to `/var/log/trading_bot.log`. You can adjust the log level by passing the `--log-level` argument when running the script.

## Testing Mode

To run the bot in testing mode without executing actual trades, use the `--testing` flag:

```
python trading-bot.py --testing
```

## Disclaimer

This bot is for educational purposes only. Use it at your own risk. Always understand the code and strategies before running automated trading systems with real money.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

