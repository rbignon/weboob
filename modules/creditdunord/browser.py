# -*- coding: utf-8 -*-

# Copyright(C) 2012 Romain Bignon
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

# flake8: compatible

from __future__ import unicode_literals

from woob.browser import LoginBrowser, URL, need_login
from woob.exceptions import BrowserIncorrectPassword, BrowserPasswordExpired, ActionNeeded, BrowserUnavailable
from woob.capabilities.bank import Account
from woob.tools.capabilities.bank.investments import create_french_liquidity
from woob.tools.capabilities.bank.transactions import sorted_transactions

from .pages import (
    LoginPage, LoginConfirmPage, ProfilePage,
    AccountsPage, IbanPage, HistoryPage, InvestmentsPage,
    RgpdPage,
)


class CreditDuNordBrowser(LoginBrowser):
    ENCODING = 'UTF-8'
    BASEURL = "https://www.credit-du-nord.fr/"

    login = URL(
        r'$',
        r'/.*\?.*_pageLabel=page_erreur_connexion',
        r'/.*\?.*_pageLabel=reinitialisation_mot_de_passe',
        LoginPage
    )
    logout = URL(r'/pkmslogout')
    login_confirm = URL(r'/sec/vk/authent.json', LoginConfirmPage)

    bypass_rgpd = URL('/icd/zcd/data/gdpr-get-out-zs-client.json', RgpdPage)

    profile = URL(r'/icd/zco/data/public-user.json', ProfilePage)
    accounts = URL(r'/icd/fdo/data/comptesExternes.json', AccountsPage)
    history = URL(r'/icd/fdo/data/detailDunCompte.json', HistoryPage)
    investments = URL(r'/icd/fdo/data/getAccountWithAsset.json', InvestmentsPage)

    iban = URL(r'/icd/zvo/data/saisieVirement/saisieVirement.json', IbanPage)

    def __init__(self, *args, **kwargs):
        self.weboob = kwargs['weboob']
        super(CreditDuNordBrowser, self).__init__(*args, **kwargs)

    def do_login(self):
        self.login.go()
        website_unavailable = self.page.get_website_unavailable_message()
        if website_unavailable:
            raise BrowserUnavailable(website_unavailable)

        # Some users are still using their old password, that leads to a virtual keyboard crash.
        if not self.password.isdigit() or len(self.password) != 6:
            raise BrowserIncorrectPassword('Veuillez utiliser le nouveau code confidentiel fourni par votre banque.')

        self.page.login(self.username, self.password)

        assert self.login_confirm.is_here(), 'Should be on login confirmation page'

        if self.page.get_status() != 'ok':
            raise BrowserIncorrectPassword()
        reason = self.page.get_reason()
        if reason == 'chgt_mdp_oblig':
            # There is no message in the json return. There is just the code.
            raise BrowserPasswordExpired('Changement de mot de passe requis.')
        elif reason == 'SCA':
            raise ActionNeeded("Vous devez réaliser la double authentification sur le portail internet")
        elif reason == 'SCAW':
            raise ActionNeeded("Vous devez choisir si vous souhaitez dès à présent activer la double authentification sur le portail internet")

    def do_logout(self):
        self.logout.go()
        self.session.cookies.clear()

    @need_login
    def iter_accounts(self):
        # When retrieving labels page,
        # If GDPR was accepted partially the website throws a page that we treat
        # as an ActionNeeded. Sometime we can by-pass it. Hence this fix
        try:
            self.accounts.go()
        except ActionNeeded:
            self.bypass_rgpd.go()
            self.accounts.go()

        current_bank = self.page.get_current_bank()

        accounts = list(self.page.iter_accounts(current_bank=current_bank))
        accounts.extend(self.page.iter_loans(current_bank=current_bank))

        self.iban.go(data={
            'virementType': 'INDIVIDUEL',
            'hashFromCookieMultibanque': '',
        })

        for account in accounts:
            if account.type == Account.TYPE_CARD:
                # Match the card with its checking account using the account number
                account.parent = next(
                    (account_ for account_ in accounts if (
                        account_.type == Account.TYPE_CHECKING
                        and account_.number[:-5] == account.number[:-5]
                    )),
                    None,
                )
            if (
                account.type in (Account.TYPE_CHECKING, Account.TYPE_SAVINGS)
                and self.page.get_status() == 'OK'  # IbanPage is not available if transfers are not authorized
            ):
                account.iban = self.page.get_iban_from_account_number(account.number)

        return accounts

    @need_login
    def iter_history(self, account, coming=False):
        if (
            (coming and account.type != Account.TYPE_CARD)
            or account.type in (Account.TYPE_LOAN, Account.TYPE_REVOLVING_CREDIT)
        ):
            return

        current_page = 1
        has_transactions = True
        while has_transactions and current_page <= 50:
            self.history.go(data={
                'an200_idCompte': account.id,
                'an200_pageCourante': str(current_page),
            })

            if account._has_investments:
                history = self.page.iter_wealth_history()
            else:
                history = self.page.iter_history(account_type=account.type)

            for transaction in sorted_transactions(history):
                yield transaction

            has_transactions = self.page.has_transactions(account._has_investments)
            current_page = current_page + 1

    @need_login
    def iter_investment(self, account):
        if account._has_investments:
            self.investments.go(data={'an200_bankAccountId': account.id})
            if self.page.has_investments():
                for investment in self.page.iter_investment():
                    yield investment
            else:
                yield create_french_liquidity(account.balance)

    @need_login
    def get_profile(self):
        self.profile.go()
        return self.page.get_profile()
