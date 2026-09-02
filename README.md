# Coinmarketcap

Converts between crypto-currencies and fiat (and back) using CoinMarketCap
data.

## Configuration

No configuration is required. Without an API key the plugin uses
CoinMarketCap's free keyless public API (no signup, no credits, but
lower IP-based rate limits). For higher rate limits you can set a free
API key from <https://coinmarketcap.com/api/pricing/>:

    config plugins.Coinmarketcap.api_key <your-key>

API responses are cached for `cache_timeout` seconds (default 60, which
matches CoinMarketCap's quote refresh interval; 0 disables caching):

    config plugins.Coinmarketcap.cache_timeout 60

## Usage

```
<user> >coinmarketcap convert 1 btc to eur
<bot> 1 BTC == 66765.0447 EUR (+0.61%) https://coinmarketcap.com/currencies/bitcoin

<user> >coinmarketcap convert 50000 eur to btc
<bot> 50000 EUR == 0.7488948774 BTC (+0.61%) https://coinmarketcap.com/currencies/bitcoin

<user> >coinmarketcap convert 100 usd to eur
<bot> 100 USD == 91.53 EUR
```

The amount is optional and defaults to 1. All directions are supported:
crypto→fiat, fiat→crypto, crypto→crypto and fiat→fiat. The 24h change and
the currency link are shown whenever a cryptocurrency is involved.
