import os
import http.client
import logging
import argparse
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

known_stablecoins = ['USDT', 'USDC', 'DAI', 'BUSD', 'TUSD', 'PAX', 'GUSD', 'HUSD', 'EURC']

payload = ''

def parse_arguments():
    parser = argparse.ArgumentParser(description="Trading Bot with customizable log level")
    parser.add_argument('--log-level', default='INFO', 
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Set the logging level')
    parser.add_argument('--testing', action='store_true',
                        help='Run in testing mode without executing trades')
    return parser.parse_args()

args = parse_arguments()
log_level = getattr(logging, args.log_level.upper())
TESTING_MODE = args.testing

def filter_out_stablecoins(currencies):
    return [currency for currency in currencies if currency not in known_stablecoins]

def setup_logging(log_directory='/var/log', log_level=logging.INFO):
    if not os.path.exists(log_directory):
        os.makedirs(log_directory)
    
    log_filename = f"trading_bot.log"
    log_filepath = os.path.join(log_directory, log_filename)
    
    logging.basicConfig(
        filename=log_filepath,
        level=log_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    logging.info(f"Logging initialized. Log file: {log_filepath}")

# Set up logging
setup_logging(log_level=log_level)

def getResponseFromAPI(uri, method='GET', data=None):
    global payload, headers
    
    jwt_token = getJwtToken(uri, method)
    headers['Authorization'] = "Bearer " + jwt_token
    
    if method == 'POST':
        headers['Content-Type'] = 'application/json'
        payload = data
    else:
        payload = None

    logging.debug(f"Making {method} request to: {uri}")
    logging.debug(f"Headers: {headers}")
    if payload:
        logging.debug(f"Payload: {payload}")

    try:
        conn.request(method, uri, payload, headers)
        res = conn.getresponse()
        response_data = res.read().decode("utf-8")
        
        logging.debug(f"Response status: {res.status}")
        logging.debug(f"Response headers: {dict(res.getheaders())}")
        logging.debug(f"Response body: {response_data[:400]}...")  # Log first 200 characters

        return response_data
    except Exception as e:
        logging.error(f"Error in API request: {str(e)}")
        return None

def getCurrencyDetails(cId):
    conn.request("GET", "/currencies/"+cId, payload, headers)
    res = conn.getresponse()
    data = res.read()
    print(data.decode("utf-8"))

def getAccounts():
    x = getResponseFromAPI(f"/api/v3/brokerage/accounts")
    logging.info(f"getAccounts returned: {x[:100]}...")  # Zeigt die ersten 100 Zeichen
    return x

def getCurrentPrice(product_id):
    response = getResponseFromAPI(f"/api/v3/brokerage/products/{product_id}", method='GET')
    price_data = json.loads(response)
    return price_data['price']

def getProducts():
    x = getResponseFromAPI(f"/api/v3/brokerage/market/products")
    return x

def getOrderDetails(order_id):
    response = getResponseFromAPI(f"/api/v3/brokerage/orders/historical/{order_id}", method='GET')
    try:
        order_details = json.loads(response)
        return order_details.get("order", {})
    except Exception as e:
        logging.error(f"Error retrieving order details for order {order_id}: {str(e)}")
        return None

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