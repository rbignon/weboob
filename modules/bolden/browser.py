# -*- coding: utf-8 -*-

# Copyright(C) 2018      Vincent A
#
# This file is part of a woob module.
#
# This woob module is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This woob module is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this woob module. If not, see <http://www.gnu.org/licenses/>.

from __future__ import unicode_literals

from datetime import timedelta, datetime

from woob.browser import LoginBrowser, need_login, URL, StatesMixin
from woob.exceptions import BrowserQuestion, NeedInteractiveFor2FA
from woob.capabilities.bill import DocumentTypes, Document
from woob.tools.capabilities.bank.investments import create_french_liquidity
from woob.tools.value import Value

from .pages import (
    LoginPage, OtpPage,
    HomeLendPage, PortfolioPage, OperationsPage,
    MAIN_ID, ProfilePage, MainPage,
)


class BoldenBrowser(LoginBrowser, StatesMixin):
    BASEURL = 'https://bolden.fr/'

    main = URL(r'$', MainPage)
    login = URL(r'/connexion', LoginPage)
    otp = URL(r'/Account/VerifyCode', OtpPage)
    home_lend = URL(r'/tableau-de-bord-investisseur', HomeLendPage)
    profile = URL(r'/mon-profil', ProfilePage)
    portfolio = URL(r'/InvestorDashboard/GetPortfolio', PortfolioPage)
    operations = URL(r'/InvestorDashboard/GetOperations\?startDate=(?P<start>[\d-]+)&endDate=(?P<end>[\d-]+)', OperationsPage)

    def __init__(self, config, *args, **kwargs):
        kwargs['username'] = config['login'].get()
        kwargs['password'] = config['password'].get()

        super(BoldenBrowser, self).__init__(*args, **kwargs)
        self.config = config

        # else the otp page message is in English
        self.session.headers['Accept-Language'] = 'fr,fr-FR'

    def do_login(self):
        def try_otp():
            if self.config['otp'].get():
                self.page.send_otp(self.config['otp'].get())
                assert self.home_lend.is_here()
                return True

        if self.otp.is_here():
            if try_otp():
                return
            else:
                raise NeedInteractiveFor2FA()

        self.main.go()
        self.page.check_website_maintenance()
        self.login.go()
        self.page.do_login(self.username, self.password)

        if self.login.is_here():
            self.page.check_error()
            raise AssertionError('Should not be on login page.')

        if self.otp.is_here():
            if not try_otp():
                if self.config['request_information'] is None:
                    raise NeedInteractiveFor2FA()

                message = self.page.get_otp_message()
                raise BrowserQuestion(Value('otp', label=message))

    @need_login
    def iter_accounts(self):
        self.portfolio.go()
        return self.page.iter_accounts()

    def iter_investments(self):
        self.portfolio.go()
        yield create_french_liquidity(self.page.get_liquidity())
        for inv in self.page.iter_investments():
            yield inv

    @need_login
    def iter_history(self, account):
        if account.id != MAIN_ID:
            return
        end = datetime.now()
        while True:
            start = end - timedelta(days=365)

            self.operations.go(start=start.strftime('%Y-%m-%d'), end=end.strftime('%Y-%m-%d'))
            transactions = list(self.page.iter_history())
            if not transactions:
                break

            last_with_date = None
            for tr in transactions:
                if tr.date is None:
                    tr.date = last_with_date.date
                    tr.label = '%s %s' % (last_with_date.label, tr.label)
                else:
                    last_with_date = tr

                yield tr

            end = start

    @need_login
    def get_profile(self):
        self.profile.go()
        return self.page.get_profile()

    @need_login
    def iter_documents(self):
        for inv in self.iter_investments():
            if inv.label == "Liquidités":
                continue
            doc = Document()
            doc.id = inv.id
            doc.url = inv._docurl
            doc.label = 'Contrat %s' % inv.label
            doc.type = DocumentTypes.CONTRACT
            doc.format = 'pdf'
            yield doc

        self.profile.go()
        for doc in self.page.iter_documents():
            yield doc
