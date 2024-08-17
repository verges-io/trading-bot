from common_functions import *

def getCurrencyDetails(cId):
    conn.request("GET", "/currencies/"+cId, payload, headers)
    res = conn.getresponse()
    data = res.read()
    print(data.decode("utf-8"))

def getAccounts():
    x = getResponseFromAPI(f"/api/v3/brokerage/accounts")
    print(x)

def getProducts():
    x = getResponseFromAPI(f"/api/v3/brokerage/market/products")
    return x

def getAllEURQuotes():
    allQuotes = getProducts()
    responseJson = json.loads(allQuotes)
    eurProducts = [product for product in responseJson['products'] if product['quote_currency_id'] == 'EUR']
    return eurProducts

def storeAllEURQuotes():
    x = getAllEURQuotes()
    for p in x:
        #print(p['base_currency_id'], p['price'])
        storeMarketData(p['base_currency_id'], p['price'], pd.to_datetime('now'))

if __name__ == '__main__':
    storeAllEURQuotes()