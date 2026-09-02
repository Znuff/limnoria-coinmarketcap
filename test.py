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

from supybot.test import *

import contextlib
import json
import unittest.mock as mock

import supybot.conf as conf
from supybot.utils import web

QUOTES_PATH = '/v3/cryptocurrency/quotes/latest'
CONVERT_PATH = '/v2/tools/price-conversion'


class FakeApi(object):
    """Callable standing in for utils.web.getUrl.

    Serves canned responses (bytes of JSON, or exceptions to raise) for
    routes given as (path fragment, query fragment, response) tuples and
    records every call made, so tests can assert which endpoints were
    probed in which order."""
    def __init__(self, routes=()):
        self.routes = list(routes)
        self.calls = []

    def route(self, path_frag, query_frag, response):
        self.routes.append((path_frag, query_frag, response))

    def __call__(self, url, size=None, timeout=None, headers=None,
                 data=None):
        self.calls.append({'url': url, 'headers': dict(headers or {})})
        for path_frag, query_frag, response in self.routes:
            if path_frag in url and query_frag in url:
                if isinstance(response, Exception):
                    raise response
                return response
        raise AssertionError('unexpected URL fetched: %r' % url)

    def fetched(self, frag):
        return [c for c in self.calls if frag in c['url']]


def _quotes_json(data):
    return json.dumps({'data': data,
                       'status': {'error_code': 0}}).encode('utf-8')


def _coin(symbol, slug, target, price, change=None):
    return {'id': 1, 'symbol': symbol, 'slug': slug,
            'quote': [{'symbol': target, 'price': price,
                       'percent_change_24h': change}]}


def _error_json(code, message):
    return json.dumps({'status': {'error_code': code,
                                  'error_message': message}}).encode('utf-8')


class CoinmarketcapTestCase(PluginTestCase):
    plugins = ('Coinmarketcap',)

    def _patch_api(self, fake, no_cache=True):
        """Patch utils.web.getUrl with `fake`; optionally disable the
        response cache so every command hits the (mocked) network."""
        stack = contextlib.ExitStack()
        if no_cache:
            stack.enter_context(
                conf.supybot.plugins.Coinmarketcap.cache_timeout.context(0))
        stack.enter_context(mock.patch.object(web, 'getUrl', fake))
        return stack

    def testCryptoToFiat(self):
        fake = FakeApi()
        fake.route(QUOTES_PATH, 'symbol=BTC&convert=EUR',
                   _quotes_json([_coin('BTC', 'bitcoin', 'EUR',
                                       62500.0, 1.5)]))
        with self._patch_api(fake):
            self.assertRegexp('convert 1 btc to eur', r'1 BTC == 62500 EUR')
            self.assertRegexp('convert 1 btc to eur', r'\+1\.50%')
            self.assertRegexp('convert 1 btc to eur',
                              r'coinmarketcap\.com/currencies/bitcoin')
            # no amount defaults to 1
            self.assertRegexp('convert btc to eur', r'1 BTC == 62500 EUR')
            self.assertEqual(len(fake.fetched('symbol=BTC&convert=EUR')), 4)

    def testFiatToCrypto(self):
        fake = FakeApi()
        fake.route(QUOTES_PATH, 'symbol=EUR&convert=BTC', _quotes_json([]))
        fake.route(QUOTES_PATH, 'symbol=BTC&convert=EUR',
                   _quotes_json([_coin('BTC', 'bitcoin', 'EUR',
                                       62500.0, -2.5)]))
        with self._patch_api(fake):
            self.assertRegexp('convert 50000 eur to btc',
                              r'50000 EUR == 0\.8 BTC')
            self.assertRegexp('convert 50000 eur to btc', r'-2\.50%')
            self.assertRegexp('convert 50000 eur to btc',
                              r'coinmarketcap\.com/currencies/bitcoin')
            # EUR is probed as the base first, then the pair is swapped
            self.assertIn('symbol=EUR', fake.calls[0]['url'])
            self.assertEqual(len(fake.fetched('symbol=EUR&convert=BTC')), 3)
            self.assertEqual(len(fake.fetched('symbol=BTC&convert=EUR')), 3)

    def testFiatToFiat(self):
        fake = FakeApi()
        fake.route(QUOTES_PATH, 'symbol=USD&convert=EUR', _quotes_json([]))
        fake.route(QUOTES_PATH, 'symbol=EUR&convert=USD', _quotes_json([]))
        fake.route(CONVERT_PATH, 'symbol=USD&convert=EUR',
                   json.dumps({'data': [
                       {'id': 2781, 'symbol': 'USD', 'quote': {
                           'EUR': {'price': 91.5}}}],
                       'status': {'error_code': 0}}).encode('utf-8'))
        with self._patch_api(fake):
            self.assertResponse('convert 100 usd to eur',
                                '100 USD == 91.5 EUR')
            # both quotes probes failed before price-conversion kicked in
            self.assertEqual(len(fake.fetched(QUOTES_PATH)), 2)
            self.assertEqual(len(fake.fetched(CONVERT_PATH)), 1)

    def testUnknownPair(self):
        fake = FakeApi()
        fake.route(QUOTES_PATH, 'symbol=FOO&convert=BAR',
                   web.Error('HTTP Error 400: Bad Request'))
        fake.route(QUOTES_PATH, 'symbol=BAR&convert=FOO', _quotes_json([]))
        fake.route(CONVERT_PATH, 'symbol=FOO&convert=BAR',
                   _error_json(400, 'Invalid value for "symbol": "FOO"'))
        with self._patch_api(fake):
            self.assertRegexp('convert 1 foo to bar',
                              r'Error: Unknown currency or unsupported '
                              r'pair: FOO/BAR')

    def testSkipsNullPrices(self):
        dead = {'id': 6582, 'symbol': 'ZZZ', 'slug': 'zzz-finance',
                'quote': [{'symbol': 'USD', 'price': None}]}
        live = _coin('ZZZ', 'zzz-coin', 'USD', 0.42, None)
        fake = FakeApi()
        fake.route(QUOTES_PATH, 'symbol=ZZZ&convert=USD',
                   _quotes_json([dead, live]))
        with self._patch_api(fake):
            self.assertResponse(
                'convert 1 zzz to usd',
                '1 ZZZ == 0.42 USD https://coinmarketcap.com/currencies/zzz-coin')

    def testAmountValidation(self):
        fake = FakeApi()  # no routes: any fetch fails the test
        with self._patch_api(fake):
            self.assertRegexp('convert -5 btc to eur',
                              r'Error: Amount must be greater than zero')
            self.assertRegexp('convert 0 btc to eur',
                              r'Error: Amount must be greater than zero')
            self.assertRegexp('convert 1e-9 btc to eur',
                              r'Error: Amount too small')
            self.assertRegexp('convert 1e13 btc to eur',
                              r'Error: Amount too large')
            self.assertEqual(fake.calls, [])

    def testKeylessByDefault(self):
        fake = FakeApi()
        fake.route(QUOTES_PATH, 'symbol=KLT&convert=EUR',
                   _quotes_json([_coin('KLT', 'klt-token', 'EUR', 2.0)]))
        with self._patch_api(fake):
            self.assertRegexp('convert 1 klt to eur', r'1 KLT == 2 EUR')
        self.assertIn('/public-api/', fake.calls[0]['url'])
        self.assertNotIn('X-CMC_PRO_API_KEY', fake.calls[0]['headers'])

    def testApiKeyUsedWhenConfigured(self):
        fake = FakeApi()
        fake.route(QUOTES_PATH, 'symbol=KLT&convert=EUR',
                   _quotes_json([_coin('KLT', 'klt-token', 'EUR', 2.0)]))
        with conf.supybot.plugins.Coinmarketcap.api_key.context('testkey'):
            with self._patch_api(fake):
                self.assertRegexp('convert 1 klt to eur', r'1 KLT == 2 EUR')
        self.assertNotIn('/public-api/', fake.calls[0]['url'])
        self.assertEqual(fake.calls[0]['headers'].get('X-CMC_PRO_API_KEY'),
                         'testkey')

    def testCacheAvoidsRefetching(self):
        fake = FakeApi()
        fake.route(QUOTES_PATH, 'symbol=CCC&convert=DDD',
                   _quotes_json([_coin('CCC', 'ccc-coin', 'DDD', 3.0)]))
        with self._patch_api(fake, no_cache=False):  # default ttl: 60s
            self.assertRegexp('convert 2 ccc to ddd', r'2 CCC == 6 DDD')
            self.assertRegexp('convert 3 ccc to ddd', r'3 CCC == 9 DDD')
            self.assertEqual(len(fake.fetched('symbol=CCC&convert=DDD')), 1)

    def testFatalApiErrorsAbortFallbacks(self):
        fake = FakeApi()
        fake.route(QUOTES_PATH, 'symbol=AUTH&convert=USD',
                   web.Error('HTTP Error 401: Unauthorized'))
        fake.route(QUOTES_PATH, 'symbol=RATE&convert=USD',
                   web.Error('HTTP Error 429: Too Many Requests'))
        with self._patch_api(fake):
            self.assertRegexp('convert 1 auth to usd',
                              r'Error: CoinMarketCap API key error')
            self.assertEqual(len(fake.fetched('symbol=AUTH')), 1)
            self.assertRegexp('convert 1 rate to usd',
                              r'Error: CoinMarketCap rate limit hit')
            self.assertEqual(len(fake.fetched('symbol=RATE')), 1)


# vim:set shiftwidth=4 tabstop=4 expandtab textwidth=79:
