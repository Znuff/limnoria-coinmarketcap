###
# Copyright (c) 2018, Znuff
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#   * Redistributions of source code must retain the above copyright notice,
#     this list of conditions, and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright notice,
#     this list of conditions, and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * Neither the name of the author of this software nor the name of
#     contributors to this software may be used to endorse or promote products
#     derived from this software without specific prior written consent.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.
###

import json
import time
import urllib.parse

import supybot.utils as utils
from supybot.commands import *
import supybot.plugins as plugins
import supybot.ircutils as ircutils
import supybot.callbacks as callbacks
import supybot.log as log
try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('Coinmarketcap')
except ImportError:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x

_KEYED_BASE = 'https://pro-api.coinmarketcap.com'
# CMC's keyless public API: free, no key or signup needed, but with
# lower IP-based rate limits.
_KEYLESS_BASE = 'https://pro-api.coinmarketcap.com/public-api'
_QUOTES_PATH = '/v3/cryptocurrency/quotes/latest'
_CONVERT_PATH = '/v2/tools/price-conversion'
_TIMEOUT = 5
_MIN_AMOUNT = 1e-8    # CMC's minimum convertible amount
_MAX_AMOUNT = 1e12    # CMC's maximum convertible amount


class ApiError(Exception):
    """Raised when an API call fails.  ``fatal`` marks failures (bad key,
    rate limit, network) for which the fallback chain should not be
    attempted."""
    def __init__(self, message, fatal=False):
        Exception.__init__(self, message)
        self.fatal = fatal


def _fmt(n):
    """Format a number for display, without trailing zeros."""
    s = ('%.10f' % n).rstrip('0').rstrip('.')
    return '0' if s == '-0' else s


class Coinmarketcap(callbacks.Plugin):
    """Converts between crypto-currencies and fiat using CoinMarketCap."""
    threaded = True

    def __init__(self, irc):
        callbacks.Plugin.__init__(self, irc)
        # url -> (expiry, parsed json) cache of successful API responses
        self._cache = {}

    def _get_json(self, path, params):
        """Fetch path with params from CoinMarketCap, return parsed JSON.

        Uses the keyed API when an api_key is configured and the free
        keyless public API otherwise.  Raises ApiError on failure; HTTP 400
        style errors are non-fatal since they usually just mean an unknown
        symbol for the endpoint being probed."""
        api_key = self.registryValue('api_key')
        headers = {'Accepts': 'application/json'}
        if api_key:
            base = _KEYED_BASE
            headers['X-CMC_PRO_API_KEY'] = api_key
        else:
            base = _KEYLESS_BASE
        url = base + path + '?' + urllib.parse.urlencode(params)

        ttl = self.registryValue('cache_timeout')
        now = time.time()
        if ttl > 0:
            cached = self._cache.get(url)
            if cached is not None and cached[0] > now:
                return cached[1]

        try:
            content = utils.web.getUrl(url, timeout=_TIMEOUT,
                                       headers=headers).decode('utf-8')
        except utils.web.Error as e:
            err = str(e)
            if '401' in err:
                raise ApiError('CoinMarketCap API key error: %s' % err,
                               fatal=True)
            elif '429' in err:
                raise ApiError('CoinMarketCap rate limit hit, '
                               'please retry in a moment', fatal=True)
            elif '400' in err:
                raise ApiError('Invalid request: %s' % err)
            raise ApiError('Request failed: %s' % err, fatal=True)
        except Exception as e:
            raise ApiError('Request failed: %s' % e, fatal=True)

        try:
            j = json.loads(content)
        except Exception as e:
            raise ApiError('Could not parse API response: %s' % e,
                           fatal=True)

        # error_code is an int with an API key but a string in keyless mode
        status = j.get('status') or {}
        try:
            error_code = int(status.get('error_code') or 0)
        except (TypeError, ValueError):
            error_code = 0
        if error_code != 0:
            message = status.get('error_message') or ('error %s' % error_code)
            raise ApiError('API Error: %s' % message,
                           fatal=error_code != 400)

        if ttl > 0:
            # Prune expired entries while we're here, then cache the reply
            self._cache = {u: e for (u, e) in self._cache.items()
                           if e[0] > now}
            self._cache[url] = (now + ttl, j)
        return j

    def _quote_from_data(self, data, target):
        """Pick the best quote for target out of a quotes/latest or
        price-conversion payload; returns (price, change_24h, slug) or
        None.

        The v3 endpoints return a list of every coin sharing a symbol
        (rank-ordered, some with null prices), so we take the first entry
        that actually has a price for target.  v1-style dict payloads are
        tolerated as well."""
        if not data:
            return None
        if isinstance(data, dict):
            data = list(data.values())
        for coin in data:
            quotes = coin.get('quote') or {}
            if isinstance(quotes, dict):  # v1 shape: {'EUR': {...}}
                quote = quotes.get(target)
            else:  # v3 shape: [{'symbol': 'EUR', 'price': ...}, ...]
                quote = next((q for q in quotes
                              if q.get('symbol') == target), None)
            if not quote:
                continue
            price = quote.get('price')
            if price is None or price <= 0:
                continue
            return (price, quote.get('percent_change_24h'), coin.get('slug'))
        return None

    def _try_quotes(self, base, target):
        """Latest quote for 1 unit of crypto `base` in `target`.
        Returns (price, change_24h, slug) or None if unavailable."""
        try:
            j = self._get_json(_QUOTES_PATH,
                               {'symbol': base, 'convert': target})
        except ApiError as e:
            if e.fatal:
                raise
            return None
        return self._quote_from_data(j.get('data'), target)

    def _try_conversion(self, amount, base, target):
        """Direct conversion of `amount` of `base` into `target` (this
        endpoint accepts fiat bases).  Returns (price, None, None) or
        None if unavailable."""
        try:
            j = self._get_json(_CONVERT_PATH,
                               {'amount': amount, 'symbol': base,
                                'convert': target})
        except ApiError as e:
            if e.fatal:
                raise
            return None
        return self._quote_from_data(j.get('data'), target)

    def convert(self, irc, msg, args, number, curr1, curr2):
        """[<number>] <currency1> to <currency2>

        Converts <number> units of <currency1> into <currency2>; defaults
        to 1 if no number is given.  Works in every direction: crypto to
        fiat (1 btc to eur), fiat to crypto (50000 eur to btc), crypto to
        crypto (1 btc to eth) and fiat to fiat (100 usd to eur).
        """
        if number <= 0:
            irc.error('Amount must be greater than zero', Raise=True)
        if number < _MIN_AMOUNT:
            irc.error('Amount too small (minimum is 10^-8)', Raise=True)
        if number > _MAX_AMOUNT:
            irc.error('Amount too large (maximum is 10^12)', Raise=True)

        curr1 = curr1.upper()
        curr2 = curr2.upper()

        try:
            # quotes/latest only accepts a cryptocurrency as its base
            # symbol, so try curr1 first, then curr2 inverted...
            quote = self._try_quotes(curr1, curr2)
            invert = False
            if quote is None:
                quote = self._try_quotes(curr2, curr1)
                invert = True
            if quote is not None:
                rate, change_24h, slug = quote
                result = number / rate if invert else number * rate
            else:
                # ... neither side is a cryptocurrency, so let CMC's
                # price-conversion endpoint handle it (fiat to fiat).
                quote = self._try_conversion(number, curr1, curr2)
                if quote is None:
                    irc.error('Unknown currency or unsupported pair: '
                              '%s/%s' % (curr1, curr2), Raise=True)
                result = quote[0]
                change_24h = None
                slug = None
        except ApiError as e:
            irc.error(str(e), Raise=True)

        try:
            change_24h = float(change_24h)
        except (TypeError, ValueError):
            change_24h = None
        if change_24h is not None:
            if change_24h >= 0:
                change = '(%s)' % ircutils.mircColor('+%.2f%%' % change_24h,
                                                     'green')
            else:
                change = '(%s)' % ircutils.mircColor('%.2f%%' % change_24h,
                                                     'red')
        else:
            change = ''

        if slug:
            coin_url = 'https://coinmarketcap.com/currencies/%s' % slug
        else:
            coin_url = ''

        message = format('%s %s == %s %s',
                         _fmt(number), curr1,
                         _fmt(result), curr2)
        if change:
            message = ' '.join((message, change))
        if coin_url:
            message = ' '.join((message, coin_url))
        irc.reply(message)

    convert = wrap(convert, [optional('float', 1.0), 'something', 'to',
                             'something'])

Class = Coinmarketcap

# vim:set shiftwidth=4 softtabstop=4 expandtab
