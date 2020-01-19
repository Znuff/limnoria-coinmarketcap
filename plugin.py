###
# Copyright (c) 2018, Bogdan Ilisei
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

try:
    import json
except Exception as e:
    log.error('Could not import module: {0}'.format(e))

class Coinmarketcap(callbacks.Plugin):
    """Coinmarketcap conversion"""
    threaded = True

    def convert(self, irc, msg, args, number, curr1, curr2):
        """[<number>] <currency1> to <currency2>

        Converts from <currency1> to <currency2>. If number isn't given, it
        defaults to 1.
        """

        api_key = self.registryValue('api_key')
        if not api_key:
            irc.error('No CoinMarketCap API Key', Raise=True)

        curr1 = curr1.upper()
        curr2 = curr2.upper()

        url = 'https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest?symbol={0}&convert={1}'
        headers = {
                'Accepts': 'application/json',
                'X-CMC_PRO_API_KEY': api_key }

        try:
            content = utils.web.getUrl(url.format(curr1, curr2), timeout=3, headers=headers).decode('utf-8')
        except Exception as e:
            # there doesn't seem to be a way to handle exceptions based on the error code with utils.web.getUrl()
            e = str(e)
            if '401' in e:
                irc.error('api key error → {0}'.format(e), Raise=True)
            elif '400' in e:
                irc.error('probably unknown currency → {0}'.format(e), Raise=True)
            else:
                irc.error(e, Raise=True)

        try:
            j = json.loads(content)
        except Exception as e:
            irc.error('could not load json: {0}'.format(e))

        if j['status']['error_code'] == 0 and j['data']:
            try:
                exchange_rate = j['data'][curr1]['quote'][curr2]['price']
            except:
                irc.error('no such currency', Raise=True)

            try:
                result = number * float(exchange_rate)
            except Exception as e:
                irc.error('could not calculate result: {0}'.format(e), Raise=true)

            try:
                change_24h = j['data'][curr1]['quote'][curr2]['percent_change_24h']

                if change_24h >= 0:
                    change = '(%s)' % ircutils.mircColor('+%.2f%%' % change_24h, 'green')
                else:
                    change = '(%s)' % ircutils.mircColor( '%.2f%%' % change_24h, 'red')
            except:
                change = ''

            try:
                coin_name = j['data'][curr1]['slug']
                coin_url = 'https://coinmarketcap.com/currencies/{0}'.format(coin_name)
            except:
                coin_name = ''
                coin_url = ''

            message = format('%s %s == %s %s %s %s',
                    ('%.10f' % number).rstrip('0').rstrip('.'),
                    curr1,
                    ('%.10f' % result).rstrip('0').rstrip('.'),
                    curr2,
                    change,
                    coin_url)

            irc.reply(message)

        else:
            irc.error('API Error → {0}'.format(j['status']['error_message']))

    convert = wrap(convert, [optional('float', 1.0), 'something', 'to', 'something'])

Class = Coinmarketcap

# vim:set shiftwidth=4 softtabstop=4 expandtab
