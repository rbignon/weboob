# -*- coding: utf-8 -*-

# Copyright(C) 2013 Romain Bignon
#
# This file is part of a weboob module.
#
# This weboob module is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This weboob module is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this weboob module. If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

import datetime

from weboob.exceptions import BrowserIncorrectPassword
from weboob.browser.browsers import LoginBrowser, need_login
from weboob.browser.exceptions import HTTPNotFound, ServerError
from weboob.browser.url import URL
from dateutil.parser import parse as parse_date

from .pages import (
    AccountsPage, JsonBalances, JsonPeriods, JsonHistory,
    JsonBalances2, CurrencyPage, LoginPage, WrongLoginPage, AccountSuspendedPage,
    NoCardPage, NotFoundPage,
)


__all__ = ['AmericanExpressBrowser']


class AmericanExpressBrowser(LoginBrowser):
    BASEURL = 'https://global.americanexpress.com'

    login = URL('/myca/logon/.*', LoginPage)
    wrong_login = URL('/myca/fuidfyp/emea/.*', WrongLoginPage)
    account_suspended = URL('/myca/onlinepayments/', AccountSuspendedPage)

    accounts = URL(r'/accounts', AccountsPage)
    js_balances = URL(r'/account-data/v1/financials/balances', JsonBalances)
    js_balances2 = URL(r'/api/servicing/v1/financials/transaction_summary\?type=split_by_cardmember&statement_end_date=(?P<date>[\d-]+)', JsonBalances2)
    js_pending = URL(r'/account-data/v1/financials/transactions\?limit=1000&offset=(?P<offset>\d+)&status=pending',
                     JsonHistory)
    js_posted = URL(r'/account-data/v1/financials/transactions\?limit=1000&offset=(?P<offset>\d+)&statement_end_date=(?P<end>[0-9-]+)&status=posted',
                    JsonHistory)
    js_periods = URL(r'/account-data/v1/financials/statement_periods', JsonPeriods)
    currency_page = URL(r'https://www.aexp-static.com/cdaas/axp-app/modules/axp-balance-summary/4.7.0/(?P<locale>\w\w-\w\w)/axp-balance-summary.json', CurrencyPage)

    no_card = URL(r'https://www.americanexpress.com/us/content/no-card/',
                  r'https://www.americanexpress.com/us/no-card/', NoCardPage)

    not_found = URL(r'/accounts/error', NotFoundPage)

    SUMMARY_CARD_LABEL = [
        'PAYMENT RECEIVED - THANK YOU',
        'PRELEVEMENT AUTOMATIQUE ENREGISTRE-MERCI',
    ]

    def __init__(self, *args, **kwargs):
        super(AmericanExpressBrowser, self).__init__(*args, **kwargs)
        self.cache = {}

    def do_login(self):
        if not self.login.is_here():
            self.location('/myca/logon/emea/action?request_type=LogonHandler&DestPage=https%3A%2F%2Fglobal.americanexpress.com%2Fmyca%2Fintl%2Facctsumm%2Femea%2FaccountSummary.do%3Frequest_type%3D%26Face%3Dfr_FR%26intlink%3Dtopnavvotrecompteneligne-HPmyca&Face=fr_FR&Info=CUExpired')

        self.page.login(self.username, self.password)
        if self.wrong_login.is_here() or self.login.is_here() or self.account_suspended.is_here():
            raise BrowserIncorrectPassword()

    @need_login
    def get_accounts(self):
        self.accounts.go()
        accounts = list(self.page.iter_accounts())

        for account in accounts:
            try:
                # for the main account
                self.js_balances.go(headers={'account_tokens': account._balances_token})
            except HTTPNotFound:
                # for secondary accounts
                self.js_periods.go(headers={'account_token': account._balances_token})
                periods = self.page.get_periods()
                self.js_balances2.go(date=periods[1], headers={'account_tokens': account._balances_token})
            self.page.set_balances(accounts)

        # get currency
        loc = self.session.cookies.get_dict(domain=".americanexpress.com")['axplocale'].lower()
        self.currency_page.go(locale=loc)
        currency = self.page.get_currency()

        for acc in accounts:
            acc.currency = currency
            yield acc

    @need_login
    def get_accounts_list(self):
        for account in self.get_accounts():
            yield account

    @need_login
    def iter_history(self, account):
        self.js_periods.go(headers={'account_token': account._token})
        periods = self.page.get_periods()
        today = datetime.date.today()
        # TODO handle pagination
        for p in periods:
            self.js_posted.go(offset=0, end=p, headers={'account_token': account._token})
            for tr in self.page.iter_history(periods=periods):
                # As the website is very handy, passing account_token is not enough:
                # it will return every transactions of each account, so we
                # have to match them manually
                if tr._owner == account._idforJSON and tr.date <= today:
                    yield tr

    @need_login
    def iter_coming(self, account):
        # Coming transactions can be found in a 'pending' JSON if it exists
        # ('En attente' tab on the website), as well as in a 'posted' JSON
        # ('Enregistrées' tab on the website)

        # "pending" have no vdate and debit date is in future
        self.js_periods.go(headers={'account_token': account._token})
        periods = self.page.get_periods()
        date = parse_date(periods[0]).date()
        today = datetime.date.today()
        # when the latest period ends today we can't know the coming debit date
        if date != today:
            try:
                self.js_pending.go(offset=0, headers={'account_token': account._token})
            except ServerError as exc:
                # At certain times of the month a connection might not have pendings;
                # in that case, `js_pending.go` would throw a 502 error Bad Gateway
                error_code = exc.response.json().get('code')
                error_message = exc.response.json().get('message')
                self.logger.warning('No pendings page to access to, got error %s and message "%s" instead.', error_code, error_message)
            else:
                for tr in self.page.iter_history(periods=periods):
                    if tr._owner == account._idforJSON:
                        tr.date = date
                        yield tr

        # "posted" have a vdate but debit date can be future or past
        for p in periods:
            self.js_posted.go(offset=0, end=p, headers={'account_token': account._token})
            for tr in self.page.iter_history(periods=periods):
                if tr.date > today or not tr.date:
                    if tr._owner == account._idforJSON:
                        yield tr
                else:
                    return
