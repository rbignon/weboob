# -*- coding: utf-8 -*-

# Copyright(C) 2017      Phyks (Lucas Verney)
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


from woob.browser import LoginBrowser, need_login, URL
from woob.exceptions import BrowserIncorrectPassword, BrowserUnavailable

from .pages import LoginPage, MonBienPage, MesChargesPage, DocumentsPage


class MyFonciaBrowser(LoginBrowser):
    BASEURL = 'https://fr.foncia.com'

    login = URL(r'/login', LoginPage)
    monBien = URL(r'/espace-client/espace-de-gestion/mon-bien', MonBienPage)
    mesCharges = URL(r'/espace-client/espace-de-gestion/mes-charges/(?P<subscription>.+)', MesChargesPage)
    documents = URL(r'/espace-client/espace-de-gestion/mes-documents/(?P<subscription>.+)/(?P<letter>[A-Z])', DocumentsPage)

    def do_login(self):
        self.login.stay_or_go().do_login(self.username, self.password)

        if self.login.is_here():
            error_message = self.page.get_error_message()
            if not error_message:
                raise AssertionError('We are stuck at the login page without error message')
            if 'votre mot de passe est incorrect' in error_message:
                raise BrowserIncorrectPassword(error_message)
            if 'Service momentanément indisponible' in error_message:
                raise BrowserUnavailable(error_message)
            raise AssertionError('An unexpected error occured: %s' % error_message)

    @need_login
    def get_subscriptions(self):
        return self.monBien.stay_or_go().get_subscriptions()

    @need_login
    def get_documents(self, subscription_id):
        # the last char of subscription_id is a letter, we need this to put this at the end of the url
        if not subscription_id[-1:].isupper():
            self.logger.debug('The last char of subscription id is not an uppercase')
        self.documents.go(subscription=subscription_id, letter=subscription_id[-1:])
        for doc in self.page.iter_documents():
            yield doc

        self.mesCharges.go(subscription=subscription_id)
        for bill in self.page.get_documents():
            yield bill
