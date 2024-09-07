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

def resampleData(df, interval='1H'):
    df = df.set_index('timestamp')
    resampled = df.groupby('symbol').resample(interval).agg({'price': 'last'}).reset_index()
    return resampled

def calculateRsi(prices, periods=14):
    prices = prices.astype(float).dropna()
    delta = prices.diff()

    gain = delta.where(delta > 0, 0).ewm(span=periods, adjust=False).mean()
    loss = -delta.where(delta < 0, 0).ewm(span=periods, adjust=False).mean()

    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi

def determineAllCurrencyAnalysis(df, rsi_periods=14):
    analysis = {}
    for symbol in df['symbol'].unique():
        symbol_data = df[df['symbol'] == symbol].sort_values('timestamp')

        if len(symbol_data) < rsi_periods:
            print(f"Skipping {symbol} due to insufficient data")
            continue

        prices = symbol_data['price'].astype(float)
        current_price = prices.iloc[-1]
        rsi = calculateRsi(prices, periods=rsi_periods).iloc[-1]

        if pd.isna(current_price) or pd.isna(rsi):
            print(f"Skipping {symbol} due to NaN values")
            continue

        analysis[symbol] = {
            'currentPrice': float(current_price),
            'rsi': float(rsi)
        }
    
    return analysis

def fetchMarketDataOfLastDays(tradable_currencies):
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

def getSellOpportunities():
    global tradableCurrencies
    global marketData
    global resampledData
    global allCurrencyAnalysis

    accountsJson = getAccounts()
    sellableBalances = getSellableBalances(accountsJson)
    sellableBalances = {k: v for k, v in sellableBalances.items() if k not in known_stablecoins}
    logging.info(f"Sellable non-stablecoin balances: {sellableBalances}")
    
    # Log analysis for all non-stablecoin currencies
    logging.info("Analysis for all non-stablecoin currencies:")
    for currency, analysis in allCurrencyAnalysis.items():
        logging.info(f"{currency}: Current price {analysis['currentPrice']:.4f}, "
                     f"RSI {analysis['rsi']:.2f}")
    
    # Filter for sell opportunities
    sellOpportunities = []
    for currency, analysis in allCurrencyAnalysis.items():
        if currency in sellableBalances:
            balance = sellableBalances[currency]
            if balance > Decimal('0.00001') and analysis['rsi'] > 70:  # Entfernen Sie die MA-Bedingung
                opportunity = {
                    'symbol': currency,
                    'currentPrice': analysis['currentPrice'],
                    'rsi': analysis['rsi'],
                    'availableBalance': float(balance)
                }
                sellOpportunities.append(opportunity)

    if sellOpportunities:
        logging.info("Sell opportunities (with available balance):")
        for opportunity in sellOpportunities:
            logging.info(f"{opportunity['symbol']} with current price {opportunity['currentPrice']:.4f}, "
                         f"RSI {opportunity['rsi']:.2f}, "
                         f"Available balance: {opportunity['availableBalance']:.8f}")
    else:
        logging.info("No sell opportunities found based on the criteria and available balances.")
        print("No sell opportunities found based on the criteria and available balances.")
    
    return sellOpportunities

def getBuyOpportunities():
    global tradableCurrencies
    global marketData
    global resampledData
    global allCurrencyAnalysis

    eur_balance = Decimal(getAccountEURBalance())
    eur_balance = Decimal(str(math.floor(eur_balance / 10) * 10))
    print(f"Available EUR balance (rounded down to nearest ten): {eur_balance}")

    if eur_balance < 10:
        print("Insufficient EUR available for investment.")
        return []

    # Filter currencies with RSI < 30 and sort them by RSI in ascending order
    top_performers = sorted(
        [(currency, analysis) for currency, analysis in allCurrencyAnalysis.items() if analysis['rsi'] < 50],
        key=lambda x: x[1]['rsi']
    )[:3]  # Limit to top 3

    if not top_performers:
        print("No cryptocurrencies with RSI < 50 found. Investment postponed.")
        return []

    buy_opportunities = []
    
    # Spezialfall: Wenn genau 10 Euro verfügbar sind
    if eur_balance == Decimal('10'):
        top_currency, top_analysis = top_performers[0]
        buy_opportunities.append({
            'symbol': top_currency,
            'amount_eur': eur_balance,
            'current_price': top_analysis['currentPrice'],
            'rsi': top_analysis['rsi']
        })
        print(f"Exactly €10 available. Investing all in top opportunity: {top_currency}")
    else:
        remaining_balance = eur_balance
        total_inverse_rsi = sum(1 / analysis['rsi'] for _, analysis in top_performers)
        
        for currency, analysis in top_performers:
            if remaining_balance < 10:
                print(f"Remaining balance {remaining_balance} is less than 10 EUR. Stopping.")
                break
            
            # Calculate weight based on inverse of RSI
            weight = (1 / analysis['rsi']) / total_inverse_rsi
            investment_amount = eur_balance * Decimal(weight)
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
    
    return '0'  

def saveTradeToDb(symbol, trade_type, amount, price, total_value, transaction_id):
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
        raise  

def getSellableBalances(accountsJson):
    accounts = json.loads(accountsJson)['accounts']
    sellableBalances = {}
    
    for account in accounts:
        currency = account['currency']
        balance = Decimal(account['available_balance']['value'])
        
        eurValue = getWalletsEurValue(currency)
        logging.debug(f"{currency} wallet has the € value " + str(eurValue))

        if eurValue > 0.90:
            sellableBalances[currency] = balance
    
    return sellableBalances

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

    def trySell(amount, places):
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
            
            time.sleep(2)
            order_details = getOrderDetails(order_id)
            
            if order_details:
                filled_size = float(order_details.get("filled_size", rounded_amount))
                filled_value = float(order_details.get("filled_value", 0))
                price = filled_value / filled_size if filled_size > 0 else opportunity['currentPrice']
                
                logging.info(f"Sold {filled_size} {symbol} for approximately {filled_value:.2f} EUR at price {price:.2f}")
                print(f"Sold {filled_size} {symbol} for approximately {filled_value:.2f} EUR at price {price:.2f}")
                
                saveTradeToDb(symbol, "SELL", filled_size, price, filled_value, order_id)
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

    for places in range(decimal_places, 0, -1):
        result = trySell(base_amount, places)
        if result is True:
            return "Success"
        elif result is None:
            return None  

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
                    
                    saveTradeToDb(symbol, "BUY", filled_size, price, filled_value, order_id)
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

def printTopRsiValues():

    marketData = fetchMarketDataOfLastDays(tradableCurrencies)
    resampledData = resampleData(marketData, interval='1h')

    all_currency_analysis = determineAllCurrencyAnalysis(resampledData)
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
    tradableCurrencies = filterOutStablecoins(tradableCurrencies)
    logging.info(f"Tradable non-stablecoin currencies: {tradableCurrencies}")

    marketData = fetchMarketDataOfLastDays(tradableCurrencies)
    resampledData = resampleData(marketData, interval='1h')

    allCurrencyAnalysis = determineAllCurrencyAnalysis(resampledData)

    printTopRsiValues()

    sellOpportunities = getSellOpportunities()
    for opportunity in sellOpportunities:
        sellCurrency(opportunity)
    
    buyOpportunities = getBuyOpportunities()
    for opportunity in buyOpportunities:
        buyCurrency(opportunity['symbol'], opportunity['amount_eur'])
    
