from common_functions import *

def getCurrencyDetails(cId):
    conn.request("GET", "/currencies/"+cId, payload, headers)
    res = conn.getresponse()
    data = res.read()
    print(data.decode("utf-8"))

def getProducts():
    x = getResponseFromAPI(f"/api/v3/brokerage/market/products")
    return x

def getPortfolio():
    w = getAccounts()
    print(w)
    responseX = json.loads(w)

    portfolioId = responseX['accounts'][0]['retail_portfolio_id']
    x = getResponseFromAPI(f"/api/v3/brokerage/portfolios/{portfolioId}")
    return x

def getPortfolioBalance():
    x = getPortfolio()
    responseJson = json.loads(x)
    return responseJson['breakdown']['portfolio_balances']['total_balance']

def storePortfolioBalance():
    x = getPortfolioBalance()
    storePortfolioData(x['value'], x['currency'])

def getAllEURQuotes():
    allQuotes = getProducts()
    responseJson = json.loads(allQuotes)
    eurProducts = [product for product in responseJson['products'] if product['quote_currency_id'] == 'EUR']
    return eurProducts

def getRsiValueForSymbol(symbol, period='1h'):
    rsi = determineAllCurrencyAnalysis(resampleData(fetchMarketDataOfLastDays({symbol}), interval=period))
    return rsi.get(symbol).get('rsi')

def storeAllEURQuotes():
    x = getAllEURQuotes()
    for p in x:
        currentRsi = getRsiValueForSymbol(p['base_currency_id'])
        storeMarketData(p['base_currency_id'], p['price'], pd.to_datetime('now'), currentRsi)

if __name__ == '__main__':
    storeAllEURQuotes()
    storePortfolioBalance()