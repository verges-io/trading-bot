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
engine = create_engine(db_url, echo=True)  # Enable SQL echo for debugging

payload = ''

def getResponseFromAPI(uri, method='GET'):
    jwt_token = getJwtToken(uri, method)
    headers['Authorization'] = "Bearer " + jwt_token
    
    conn.request(method, uri, payload, headers)
    res = conn.getresponse()
    data = res.read()
    return data.decode("utf-8")

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