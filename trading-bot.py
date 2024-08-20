from common_functions import *
from typing import List, Dict
import psycopg2
from psycopg2.extras import DictCursor
from decimal import Decimal, ROUND_DOWN
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

def resample_data(df, interval='1H'):
    df = df.set_index('timestamp')
    resampled = df.groupby('symbol').resample(interval).agg({'price': 'last'}).reset_index()
    return resampled

def calculate_rsi(prices, periods=14):
    delta = prices.diff()
    
    gain = (delta.where(delta > 0, 0)).ewm(span=periods, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(span=periods, adjust=False).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def determine_all_currency_analysis(df, rsi_periods=14, sma_window=20):
    analysis = {}
    for symbol in df['symbol'].unique():
        symbol_data = df[df['symbol'] == symbol].sort_values('timestamp')
        
        if len(symbol_data) < max(rsi_periods, sma_window):
            continue
        
        prices = symbol_data['price']
        current_price = prices.iloc[-1]
        sma = prices.rolling(window=sma_window).mean().iloc[-1]
        rsi = calculate_rsi(prices, periods=rsi_periods).iloc[-1]
        
        analysis[symbol] = {
            'currentPrice': current_price,
            'sma': sma,
            'rsi': rsi
        }
    
    return analysis

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
        print("No sell opportunities found based on the criteria and available balances.")
    
    return sellOpportunities

def get_buy_opportunities():
    global tradableCurrencies
    global marketData
    global resampledData
    global allCurrencyAnalysis

    # Hole den aktuellen EUR-Kontostand
    eur_balance = Decimal(getAccountEURBalance())
    
    # Runde das Investitionskapital auf die nächste Zehnerstelle ab
    eur_balance = Decimal(str(math.floor(eur_balance / 10) * 10))
    
    print(f"Available EUR balance (rounded down to nearest ten): {eur_balance}")

    if eur_balance < 10:
        print("Insufficient EUR available for investment.")
        return []

    # Filter currencies with RSI < 30 and sort them by RSI in ascending order
    top_performers = sorted(
        [(currency, analysis) for currency, analysis in allCurrencyAnalysis.items() if analysis['rsi'] < 30],
        key=lambda x: x[1]['rsi']
    )[:3]  # Limit to top 3

    if not top_performers:
        print("No cryptocurrencies with RSI < 30 found. Investment postponed.")
        return []

    buy_opportunities = []
    remaining_balance = eur_balance

    for i, (currency, analysis) in enumerate(top_performers):
        if remaining_balance < 10:
            print(f"Remaining balance {remaining_balance} is less than 10 EUR. Stopping.")
            break

        if i == len(top_performers) - 1 or len(top_performers) == 1:
            investment_amount = remaining_balance
        else:
            investment_amount = remaining_balance / Decimal(len(top_performers) - i)

        rounded_amount = Decimal(math.floor(investment_amount / 10) * 10)

        print(f"Considering {currency}: Investment amount before rounding: {investment_amount}, after rounding: {rounded_amount}")

        if rounded_amount >= 10:
            buy_opportunities.append({
                'symbol': currency,
                'amount_eur': rounded_amount,
                'current_price': analysis['currentPrice'],
                'rsi': analysis['rsi']
            })
            remaining_balance -= rounded_amount
            print(f"Added buy opportunity for {currency}: {rounded_amount} EUR. Remaining balance: {remaining_balance}")
        else:
            print(f"Skipping {currency} because rounded amount {rounded_amount} is less than 10 EUR")

    print("Final buy opportunities:")
    for opportunity in buy_opportunities:
        print(f"{opportunity['symbol']}: €{opportunity['amount_eur']} (RSI: {opportunity['rsi']:.2f})")

    return buy_opportunities

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

def sellCurrency(opportunity, force=False, decimal_places=8):
    if TESTING_MODE and not force:
        logging.info(f"TESTING: Would sell {opportunity['availableBalance']} of {opportunity['symbol']} with {decimal_places} decimal places")
        return None

    symbol = opportunity['symbol']
    base_amount = Decimal(str(opportunity['availableBalance']))
    
    if base_amount <= Decimal('0.00001'):  # Minimum amount to sell
        logging.warning(f"Amount too small to sell for {symbol}: {base_amount}")
        return None

    product_id = f"{symbol}-EUR"

    def try_sell(amount, places):
        # Runden Sie die Menge auf die spezifizierte Anzahl von Dezimalstellen ab
        rounded_amount = amount.quantize(Decimal('1e-{}'.format(places)), rounding=ROUND_DOWN)
        
        order_data = {
            "client_order_id": str(uuid.uuid4()),
            "product_id": product_id,
            "side": "SELL",
            "order_configuration": {
                "market_market_ioc": {
                    "base_size": str(rounded_amount)
                }
            }
        }
        
        payload = json.dumps(order_data)
        logging.debug(f"Sending sell order with payload: {payload}")
        response = getResponseFromAPI("/api/v3/brokerage/orders", method='POST', data=payload)
        
        logging.debug(f"Full API response: {response}")
        
        response_json = json.loads(response)
        if "success" in response_json and response_json["success"]:
            order_id = response_json["success_response"]["order_id"]
            
            # Warte kurz, um der API Zeit zu geben, den Auftrag zu verarbeiten
            time.sleep(2)
            
            # Hole die Orderdetails
            order_details = getOrderDetails(order_id)
            
            if order_details:
                filled_size = float(order_details.get("filled_size", rounded_amount))
                filled_value = float(order_details.get("filled_value", 0))
                price = filled_value / filled_size if filled_size > 0 else opportunity['currentPrice']
                
                logging.info(f"Sold {filled_size} {symbol} for approximately {filled_value:.2f} EUR at price {price:.2f}")
                print(f"Sold {filled_size} {symbol} for approximately {filled_value:.2f} EUR at price {price:.2f}")
                
                save_trade_to_db(symbol, "SELL", filled_size, price, filled_value, order_id)
            else:
                logging.warning(f"Order placed but unable to retrieve details. Order ID: {order_id}")
            
            return True
        else:
            error_message = response_json.get("error_response", {}).get("message", "Unknown error")
            if "Too many decimals in order amount" in error_message:
                return False
            else:
                logging.error(f"Error selling {rounded_amount} {symbol}: {error_message}")
                print(f"Error selling {rounded_amount} {symbol}: {error_message}")
                logging.error(f"Full error response: {json.dumps(response_json, indent=2)}")
                return None

    # Versuchen Sie den Verkauf mit abnehmender Anzahl von Dezimalstellen
    for places in range(decimal_places, 0, -1):
        result = try_sell(base_amount, places)
        if result is True:
            return "Success"
        elif result is None:
            return None  # Ein anderer Fehler ist aufgetreten, Abbruch

    logging.error(f"Failed to sell {symbol} even with 1 decimal place")
    return None

def buyCurrency(symbol, amount_eur, force=False):
    print(f"Attempting to buy {symbol} for {amount_eur} EUR")
    
    if amount_eur < 10:
        print(f"Skipping buy for {symbol} because amount {amount_eur} EUR is less than 10 EUR")
        return None

    if TESTING_MODE and not force:
        print(f"TESTING: Would buy {amount_eur}€ of {symbol}")
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
            
            time.sleep(2)
            order_details = getOrderDetails(order_id)
            
            if order_details:
                filled_size = float(order_details.get("filled_size", 0))
                filled_value = float(order_details.get("filled_value", amount_eur))
                
                if filled_size > 0 and filled_value > 0:
                    price = filled_value / filled_size
                    
                    logging.info(f"Successfully bought approximately {filled_size:.8f} {symbol} for {filled_value:.2f}€ at price {price:.2f}")
                    print(f"Successfully bought approximately {filled_size:.8f} {symbol} for {filled_value:.2f}€ at price {price:.2f}")
                    
                    save_trade_to_db(symbol, "BUY", filled_size, price, filled_value, order_id)
                else:
                    logging.warning(f"Order placed for {symbol} but filled size or value is zero. Order ID: {order_id}")
                    print(f"Order placed for {symbol} but no coins were bought. Please check your account.")
            else:
                logging.warning(f"Order placed but unable to retrieve details. Order ID: {order_id}")
                print(f"Order placed for {symbol} but unable to retrieve details. Please check your account.")
            
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
