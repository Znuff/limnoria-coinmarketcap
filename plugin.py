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
try:
    from supybot.i18n import PluginInternationalization
    _ = PluginInternationalization('Coinmarketcap')
except ImportError:
    # Placeholder that allows to run the plugin on a bot
    # without the i18n module
    _ = lambda x: x

import json


class Coinmarketcap(callbacks.Plugin):
    """Coinmarketcap conversion"""
    threaded = True

    def convert(self, irc, msg, args, number, curr1, curr2):
        """[<number>] <currency1> to <currency2>

        Converts from <currency1> to <currency2>. If number isn't given, it
        defaults to 1.
        """

        # not needed yet
        # api_key = self.registryValue('apikey')

        # if not api_key:
        #    irc.error('No API Key configured.')

        url = 'https://api.coinmarketcap.com/v1/ticker/?convert=%s&limit=0'

        try:
            headers = {
                    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/65.0.3298.3 Safari/537.36',
                    'authority': 'api.coinmarketcap.com',
                    }
            content = utils.web.getUrl(url % curr2.upper(), timeout=5, headers=headers )
        except utils.web.Error, e:
            irc.error(str(e), Raise=True)

        data = json.loads(content)
        value = { }

        for x in data:
            if x['symbol'] not in value:
                value[x['symbol']] = x

        if data:
            try:
                exchange_rate = value['%s' % curr1.upper()]['price_%s' % curr2.lower()]
            except:
                irc.error('no such currency', Raise=True)
            try:
                result = number * float(exchange_rate)
                
                try: 
                    change_24h = float(value['%s' % curr1.upper()]['percent_change_24h'])

                    if change_24h >= 0:
                        change = '(%s)' % ircutils.mircColor('+%.2f%%' % change_24h, 'green')
                    else:
                        change = '(%s)' % ircutils.mircColor('%.2f%%' % change_24h, 'red')
                except:
                    change = ''

                coin_name = value['%s' % curr1.upper()]['id']
                coin_url = 'https://coinmarketcap.com/currencies/%s' % coin_name
                
                message = format('%s %s == %s %s %s %s',
                    ('%.10f' % number).rstrip('0').rstrip('.'),
                    curr1.upper(),
                    ('%.10f' % result).rstrip('0').rstrip('.'),
                    curr2.upper(),
                    change,
                    coin_url)

                irc.reply(message)

            except:
                irc.error('I have no idea. Something fucked up.')

    convert = wrap(convert, [optional('float', 1.0), 'lowered', 'to', 'lowered'])

Class = Coinmarketcap

# vim:set shiftwidth=4 softtabstop=4 expandtab
