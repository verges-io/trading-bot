from common_functions import *
from typing import List, Dict
import psycopg2
from psycopg2.extras import DictCursor
from decimal import Decimal

# Set up logging
setup_logging()

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
    tradableCurrencies = getTradableCurrencies()
    logging.info(f"Tradable currencies: {tradableCurrencies}")
    
    accountsJson = getAccounts()
    sellableBalances = get_sellable_balances(accountsJson)
    logging.info(f"Sellable balances: {sellableBalances}")
    
    marketData = fetch_market_data_last_4_days(tradableCurrencies)
    resampledData = resample_data(marketData, interval='1h')
    
    allCurrencyAnalysis = determine_all_currency_analysis(resampledData)
    
    # Log analysis for all currencies
    logging.info("Analysis for all currencies:")
    for currency, analysis in allCurrencyAnalysis.items():
        logging.info(f"{currency}: Current price {analysis['currentPrice']:.4f}, "
                     f"SMA {analysis['sma']:.4f}, RSI {analysis['rsi']:.2f}")
    
    # Filter for sell opportunities
    sellOpportunities = []
    for currency, analysis in allCurrencyAnalysis.items():
        if currency in sellableBalances:
            if analysis['currentPrice'] > analysis['sma'] and analysis['rsi'] > 70:
                opportunity = {
                    'symbol': currency,
                    'currentPrice': analysis['currentPrice'],
                    'sma': analysis['sma'],
                    'rsi': analysis['rsi'],
                    'availableBalance': float(sellableBalances[currency])
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
    tradableCurrencies = getTradableCurrencies()
    logging.info(f"Tradable currencies: {tradableCurrencies}")

    accountsJson = getAccounts()
    marketData = fetch_market_data_last_4_days(tradableCurrencies)
    resampledData = resample_data(marketData, interval='1h')

    allCurrencyAnalysis = determine_all_currency_analysis(resampledData)

    eur_balance = Decimal(getAccountEURBalance().get('EUR', '0'))
    logging.info(f"Available EUR balance: {eur_balance}")

    if eur_balance <= 0:
        logging.info("No EUR available for investment.")
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

    for currency, analysis in top_performers:
        weight = (100 - analysis['rsi']) / total_inverse_rsi
        investment_amount = eur_balance * Decimal(weight)

        buy_opportunities.append({
            'symbol': currency,
            'amount_eur': round(investment_amount, 2),
            'current_price': analysis['currentPrice'],
            'rsi': analysis['rsi']
        })

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
    
    return '0'

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

def sellCurrency(symbol, amount):
    payload = json.dumps({
        "symbol": symbol,
        "amount": str(amount)
    })
    #response = getResponseFromAPI("/api/v3/brokerage/sell", method='POST', payload=payload)
    #logging.info(f"Response from selling {amount} {symbol}: {response}")
    print(f"Would sell {amount} {symbol}")

if __name__ == "__main__":
    sellOpportunities = get_sell_opportunities()
    for opportunity in sellOpportunities:
        sellCurrency(opportunity['symbol'], opportunity['availableBalance'])
    
    buyOpportunities = get_buy_opportunities()