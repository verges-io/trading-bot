import os
import http.client
import logging
from sqlalchemy import create_engine, exc, text
import json
import jwt
import pandas as pd
from cryptography.hazmat.primitives import serialization
import time
import secrets
from coinbase import jwt_generator
from dotenv import load_dotenv
import logging
from datetime import datetime, timedelta

# Load .env file
load_dotenv()

api_key = os.getenv('COINBASE_API_KEY_NAME')
api_secret = os.getenv('COINBASE_API_PRIVATE_KEY')

db_db = os.getenv('POSTGRES_DB')
db_user = os.getenv('POSTGRES_USER')
db_pass = os.getenv('POSTGRES_PASS')
db_db = os.getenv('POSTGRES_DB')

requestHost   = "api.coinbase.com"
conn = http.client.HTTPSConnection(requestHost)

headers = {
    'Content-Type': 'application/json',
    'User-Agent': 'Dennis Trading Bot/1.0',
}

# Set up database connection
db_url = os.getenv('DATABASE_URL', f'postgresql://{db_user}:{db_pass}@localhost:5432/{db_db}')
engine = create_engine(db_url, echo=False)  # Enable SQL echo for debugging

payload = ''

def setup_logging(log_directory='/var/log', log_level=logging.INFO, console_output=False):
    # Ensure the log directory exists
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)
    
    # Create a timestamp for the log file name
    log_filename = f"trading_bot.log"
    log_filepath = os.path.join(log_directory, log_filename)
    
     # Configure logging to file only
    logging.basicConfig(
        filename=log_filepath,
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    if console_output:
        # Add console handler if requested
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logging.getLogger().addHandler(console_handler)
    
    logging.info(f"Logging initialized. Log file: {log_filepath}")

def getResponseFromAPI(uri, method='GET'):
    jwt_token = getJwtToken(uri, method)
    headers['Authorization'] = "Bearer " + jwt_token
    
    conn.request(method, uri, payload, headers)
    res = conn.getresponse()
    data = res.read()
    return data.decode("utf-8")

def getCurrencyDetails(cId):
    conn.request("GET", "/currencies/"+cId, payload, headers)
    res = conn.getresponse()
    data = res.read()
    print(data.decode("utf-8"))

def getAccounts():
    x = getResponseFromAPI(f"/api/v3/brokerage/accounts")
    logging.info(f"getAccounts returned: {x[:100]}...")  # Zeigt die ersten 100 Zeichen
    return x

def getProducts():
    x = getResponseFromAPI(f"/api/v3/brokerage/market/products")
    return x

def getAllEURQuotes():
    allQuotes = getProducts()
    responseJson = json.loads(allQuotes)
    eurProducts = [product for product in responseJson['products'] if product['quote_currency_id'] == 'EUR']
    return eurProducts

def storeMarketData(symbol, price, timestamp):
    try:
        with engine.begin() as conn:  # Use a transaction
            stmt = text("INSERT INTO market_data (symbol, price, timestamp) VALUES (:symbol, :price, :timestamp)")
            logging.debug(f"Executing SQL: {stmt} with params symbol={symbol}, price={price}, timestamp={timestamp}")
            conn.execute(stmt, {"symbol": symbol, "price": float(price), "timestamp": str(timestamp)})
            logging.debug(f"Stored market data for {symbol} at {timestamp} with price {price}")
    except exc.SQLAlchemyError as e:
        logging.error(f"Failed to store market data for {symbol} at {timestamp} with price {price}: {e}")
        print(f"Failed to store market data for {symbol} at {timestamp} with price {price}: {e}")

def getJwtToken(uri, method='GET'):
    jwt_uri = jwt_generator.format_jwt_uri(method, uri)
    jwt_token = jwt_generator.build_rest_jwt(jwt_uri, api_key, api_secret)
    return jwt_token