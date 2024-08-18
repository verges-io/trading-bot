from common_functions import *
from typing import List, Dict
import psycopg2
from psycopg2.extras import DictCursor
from decimal import Decimal
import uuid
import math

try:
    with engine.connect() as connection:
        result = connection.execute(text("SELECT 1"))
        logging.info("Database connection successful")
except Exception as e:
    logging.error(f"Error connecting to database: {e}")
    raise

def getTradableCurrencies() -> List[str]:
    eurQuotes = getAllEURQuotes()
    return [product['base_currency_id'] for product in eurQuotes]

def getTradableCurrencies() -> List[str]:
    eurQuotes = getAllEURQuotes()
    return [product['base_currency_id'] for product in eurQuotes]

def fetch_market_data_last_4_days(tradable_currencies):
    four_days_ago = datetime.now() - timedelta(days=4)
    query = text("""
    SELECT symbol, price, timestamp
    FROM market_data
    WHERE timestamp >= :four_days_ago
    AND symbol IN :symbols
    ORDER BY symbol, timestamp
    """)
    
    with engine.connect() as connection:
        result = connection.execute(
            query,
            {
                "four_days_ago": four_days_ago,
                "symbols": tuple(tradable_currencies)
            }
        )
        df = pd.DataFrame(result.fetchall(), columns=result.keys())
    
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    return df

def resample_data(df, interval='1H'):
    df = df.set_index('timestamp')
    resampled = df.groupby('symbol').resample(interval.replace('H', 'h')).agg({'price': 'last'}).reset_index()
    return resampled

def get_sell_opportunities():
    global tradableCurrencies
    global marketData
    global resampledData
    global allCurrencyAnalysis

    accountsJson = getAccounts()
    sellableBalances = get_sellable_balances(accountsJson)
    sellableBalances = {k: v for k, v in sellableBalances.items() if k not in known_stablecoins}
    logging.info(f"Sellable non-stablecoin balances: {sellableBalances}")
    
    # Log analysis for all non-stablecoin currencies
    logging.info("Analysis for all non-stablecoin currencies:")
    for currency, analysis in allCurrencyAnalysis.items():
        logging.info(f"{currency}: Current price {analysis['currentPrice']:.4f}, "
                     f"SMA {analysis['sma']:.4f}, RSI {analysis['rsi']:.2f}")
    
    # Filter for sell opportunities
    sellOpportunities = []
    for currency, analysis in allCurrencyAnalysis.items():
        if currency in sellableBalances:
            balance = sellableBalances[currency]
            if balance > Decimal('0.00001') and analysis['currentPrice'] > analysis['sma'] and analysis['rsi'] > 70:
                print(currency)
                opportunity = {
                    'symbol': currency,
                    'currentPrice': analysis['currentPrice'],
                    'sma': analysis['sma'],
                    'rsi': analysis['rsi'],
                    'availableBalance': float(balance)
                }
                sellOpportunities.append(opportunity)
    
    if sellOpportunities:
        logging.info("Sell opportunities (with available balance):")
        for opportunity in sellOpportunities:
            logging.info(f"{opportunity['symbol']} with current price {opportunity['currentPrice']:.4f}, "
                         f"SMA {opportunity['sma']:.4f}, RSI {opportunity['rsi']:.2f}, "
                         f"Available balance: {opportunity['availableBalance']:.8f}")
    else:
        logging.info("No sell opportunities found based on the criteria and available balances.")
    
    return sellOpportunities

def get_buy_opportunities():
    global tradableCurrencies
    global marketData
    global resampledData
    global allCurrencyAnalysis

    eur_balance = Decimal(getAccountEURBalance())
    logging.info(f"Available EUR balance: {eur_balance}")

    if eur_balance <= 10:
        logging.info("Insufficient EUR available for investment.")
        return []

    # Sort currencies by RSI in ascending order (lower RSI is better for buying)
    sorted_currencies = sorted(allCurrencyAnalysis.items(), key=lambda x: x[1]['rsi'])

    # Determine how many top performers to consider
    if eur_balance < 20:
        top_count = 1
    elif eur_balance < 40:
        top_count = 2
    else:
        top_count = 3

    top_performers = sorted_currencies[:top_count]

    # Calculate investment amounts based on RSI
    total_inverse_rsi = sum(100 - analysis['rsi'] for _, analysis in top_performers)
    buy_opportunities = []
    remaining_balance = eur_balance

    for currency, analysis in top_performers:
        if remaining_balance < 1:
            break
        
        weight = (100 - analysis['rsi']) / total_inverse_rsi
        investment_amount = min(eur_balance * Decimal(weight), remaining_balance)
        
        # Round down to nearest euro
        rounded_amount = Decimal(math.floor(investment_amount))
        
        if rounded_amount >= 1:
            buy_opportunities.append({
                'symbol': currency,
                'amount_eur': rounded_amount,
                'current_price': analysis['currentPrice'],
                'rsi': analysis['rsi']
            })
            remaining_balance -= rounded_amount

    logging.info("Buy opportunities:")
    for opportunity in buy_opportunities:
        logging.info(f"{opportunity['symbol']}: €{opportunity['amount_eur']} "
                     f"(Price: {opportunity['current_price']}, RSI: {opportunity['rsi']:.2f})")

    return buy_opportunities

def determine_all_currency_analysis(df):
    analysis = {}
    for symbol in df['symbol'].unique():
        symbolData = df[df['symbol'] == symbol].sort_values('timestamp')
        
        if len(symbolData) < 20:  # Ensure we have enough data points
            continue
        
        prices = symbolData['price']
        currentPrice = prices.iloc[-1]
        sma = simple_moving_average(prices).iloc[-1]
        rsi = calculate_rsi(prices).iloc[-1]
        
        analysis[symbol] = {
            'currentPrice': currentPrice,
            'sma': sma,
            'rsi': rsi
        }
    
    return analysis

def getAccountEURBalance():
    accountsJson = getAccounts()
    accounts = json.loads(accountsJson)['accounts']
    
    for account in accounts:
        if account['currency'] == 'EUR':
            return account['available_balance']['value']
    
    return '0'  # Return '0' as a string if no EUR account is found

def save_trade_to_db(symbol, trade_type, amount, price, total_value, transaction_id):
    query = text("""
    INSERT INTO trades (symbol, type, amount, price, total_value, transaction_id)
    VALUES (:symbol, :type, :amount, :price, :total_value, :transaction_id)
    """)
    
    try:
        with engine.begin() as connection:
            result = connection.execute(query, {
                "symbol": symbol,
                "type": trade_type,
                "amount": amount,
                "price": price,
                "total_value": total_value,
                "transaction_id": transaction_id
            })
            logging.info(f"Trade saved to database: {trade_type} {amount} {symbol}")
            logging.debug(f"Database insert result: {result.rowcount} row(s) affected")
    except Exception as e:
        logging.error(f"Error saving trade to database: {e}")
        raise  # Re-raise the exception to ensure it's not silently ignored

def get_sellable_balances(accountsJson):
    accounts = json.loads(accountsJson)['accounts']
    sellableBalances = {}
    
    for account in accounts:
        currency = account['currency']
        balance = Decimal(account['available_balance']['value'])
        
        if balance > 0:
            sellableBalances[currency] = balance
    
    return sellableBalances

def simple_moving_average(prices, window=20):
    return prices.rolling(window=window).mean()

def calculate_rsi(prices, periods=14):
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=periods).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=periods).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def sellCurrency(opportunity, force=False):
    if TESTING_MODE and not force:
        logging.info(f"TESTING: Would sell {opportunity['availableBalance']} of {opportunity['symbol']}")
        return None

    symbol = opportunity['symbol']
    base_amount = opportunity['availableBalance']
    
    if base_amount <= 0.00001:  # Minimum amount to sell
        logging.warning(f"Amount too small to sell for {symbol}: {base_amount}")
        return None

    product_id = f"{symbol}-EUR"
    
    # Runden Sie die Menge auf 8 Dezimalstellen ab (typisch für Kryptowährungen)
    base_amount = math.floor(float(opportunity['availableBalance']) * 1e8) / 1e8
    
    order_data = {
        "client_order_id": str(uuid.uuid4()),
        "product_id": product_id,
        "side": "SELL",
        "order_configuration": {
            "market_market_ioc": {
                "base_size": str(base_amount)
            }
        }
    }
    
    payload = json.dumps(order_data)
    logging.debug(f"Sending sell order with payload: {payload}")
    response = getResponseFromAPI("/api/v3/brokerage/orders", method='POST', data=payload)
    
    logging.debug(f"Full API response: {response}")
    
    try:
        response_json = json.loads(response)
        if "success" in response_json and response_json["success"]:
            order_id = response_json["success_response"]["order_id"]
            
            # Warte kurz, um der API Zeit zu geben, den Auftrag zu verarbeiten
            time.sleep(2)
            
            # Hole die Orderdetails
            order_details = getOrderDetails(order_id)
            
            if order_details:
                filled_size = float(order_details.get("filled_size", base_amount))
                filled_value = float(order_details.get("filled_value", 0))
                price = filled_value / filled_size if filled_size > 0 else opportunity['currentPrice']
                
                logging.info(f"Attempting to save trade to database: {symbol}, SELL, {filled_size}, {price}, {filled_value}, {order_id}")
                save_trade_to_db(symbol, "SELL", filled_size, price, filled_value, order_id)
                logging.info(f"Trade save attempt completed")
                
                logging.info(f"Sold {filled_size} {symbol} for approximately {filled_value:.2f} EUR at price {price:.2f}")
                print(f"Sold {filled_size} {symbol} for approximately {filled_value:.2f} EUR at price {price:.2f}")
            else:
                logging.warning(f"Order placed but unable to retrieve details. Order ID: {order_id}")
            
            return response
        else:
            error_message = response_json.get("error_response", {}).get("message", "Unknown error")
            logging.error(f"Error selling {base_amount} {symbol}: {error_message}")
            print(f"Error selling {base_amount} {symbol}: {error_message}")
            logging.error(f"Full error response: {json.dumps(response_json, indent=2)}")
            return None
    except Exception as e:
        logging.error(f"Exception occurred while processing sell order for {symbol}: {str(e)}")
        print(f"Exception occurred while processing sell order for {symbol}: {str(e)}")
        logging.error(f"Full response that caused the error: {response}")
        return None

def buyCurrency(symbol, amount_eur, force=False):
    if TESTING_MODE and not force:
        logging.info(f"TESTING: Would buy {amount_eur}€ of {symbol}")
        return None

    eur_balance = Decimal(getAccountEURBalance())
    if eur_balance < Decimal(str(amount_eur)):
        logging.error(f"Insufficient balance to buy {amount_eur}€ of {symbol}. Available balance: {eur_balance}€")
        return None

    product_id = f"{symbol}-EUR"
    
    order_data = {
        "client_order_id": str(uuid.uuid4()),
        "product_id": product_id,
        "side": "BUY",
        "order_configuration": {
            "market_market_ioc": {
                "quote_size": str(amount_eur)
            }
        }
    }
    
    payload = json.dumps(order_data)
    logging.debug(f"Sending buy order with payload: {payload}")
    response = getResponseFromAPI("/api/v3/brokerage/orders", method='POST', data=payload)
    
    logging.debug(f"Full API response: {response}")
    
    try:
        response_json = json.loads(response)
        if "success" in response_json and response_json["success"]:
            order_id = response_json["success_response"]["order_id"]
            
            # Warte kurz, um der API Zeit zu geben, den Auftrag zu verarbeiten
            time.sleep(2)
            
            # Hole die Orderdetails
            order_details = getOrderDetails(order_id)
            
            if order_details:
                filled_size = float(order_details.get("filled_size", 0))
                filled_value = float(order_details.get("filled_value", amount_eur))
                price = filled_value / filled_size if filled_size > 0 else 0
                
                logging.info(f"Attempting to save trade to database: {symbol}, BUY, {filled_size}, {price}, {filled_value}, {order_id}")
                save_trade_to_db(symbol, "BUY", filled_size, price, filled_value, order_id)
                logging.info(f"Trade save attempt completed")
                logging.info(f"Successfully bought approximately {filled_size:.8f} {symbol} for {filled_value:.2f}€ at price {price:.2f}")
                print(f"Successfully bought approximately {filled_size:.8f} {symbol} for {filled_value:.2f}€ at price {price:.2f}")
            else:
                logging.warning(f"Order placed but unable to retrieve details. Order ID: {order_id}")
                print(f"Order placed but unable to retrieve details. Order ID: {order_id}")
            
            return response
        else:
            error_message = response_json.get("error_response", {}).get("message", "Unknown error")
            logging.error(f"Error buying {amount_eur}€ of {symbol}: {error_message}")
            print(f"Error buying {amount_eur}€ of {symbol}: {error_message}")
            logging.error(f"Full error response: {json.dumps(response_json, indent=2)}")
            return None
    except Exception as e:
        logging.error(f"Exception occurred while processing buy order for {symbol}: {str(e)}")
        print(f"Exception occurred while processing buy order for {symbol}: {str(e)}")
        logging.error(f"Full response that caused the error: {response}")
        return None

def print_top_rsi_values():

    marketData = fetch_market_data_last_4_days(tradableCurrencies)
    resampledData = resample_data(marketData, interval='1h')

    all_currency_analysis = determine_all_currency_analysis(resampledData)
    sell_candidates = sorted(all_currency_analysis.items(), key=lambda x: x[1]['rsi'], reverse=True)[:3]
    buy_candidates = sorted(all_currency_analysis.items(), key=lambda x: x[1]['rsi'])[:3]
    
    print("Top 3 RSI values for potential sell:")
    for symbol, analysis in sell_candidates:
        print(f"{symbol}: RSI {analysis['rsi']:.2f}")
    
    print("\nTop 3 RSI values for potential buy:")
    for symbol, analysis in buy_candidates:
        print(f"{symbol}: RSI {analysis['rsi']:.2f}")
    
    print("\n")

if __name__ == "__main__":
    tradableCurrencies = getTradableCurrencies()
    tradableCurrencies = filter_out_stablecoins(tradableCurrencies)
    logging.info(f"Tradable non-stablecoin currencies: {tradableCurrencies}")

    marketData = fetch_market_data_last_4_days(tradableCurrencies)
    resampledData = resample_data(marketData, interval='1h')

    allCurrencyAnalysis = determine_all_currency_analysis(resampledData)

    print_top_rsi_values()

    sellOpportunities = get_sell_opportunities()
    for opportunity in sellOpportunities:
        sellCurrency(opportunity)
    
    buyOpportunities = get_buy_opportunities()
    for opportunity in buyOpportunities:
        buyCurrency(opportunity['symbol'], opportunity['amount_eur'])
    
    #buyCurrency('UNI', 2, True) 
    #sellCurrency('BTC', 10, True)
