# -*- coding: utf-8 -*-

# Copyright(C) 2013-2015      Christophe Lampin
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

from decimal import Decimal

from woob.browser import LoginBrowser, URL, need_login
from woob.exceptions import BrowserIncorrectPassword
from woob.capabilities.bill import Detail
from woob.tools.compat import urlencode

from .pages import LoginPage, HomePage, AccountPage, HistoryPage, BillsPage, SearchPage

__all__ = ['AmeliProBrowser']


class AmeliProBrowser(LoginBrowser):
    BASEURL = 'https://espacepro.ameli.fr'

    loginp = URL(r'/PortailPS/appmanager/portailps/professionnelsante\?_nfpb=true&_pageLabel=vp_login_page', LoginPage)
    homep = URL(r'/PortailPS/appmanager/portailps/professionnelsante\?_nfpb=true&_pageLabel=vp_accueil_page', HomePage)
    accountp = URL(
        r'/PortailPS/appmanager/portailps/professionnelsante\?_nfpb=true&_pageLabel=vp_coordonnees_infos_perso_page',
        AccountPage
    )
    billsp = URL(
        r'/PortailPS/appmanager/portailps/professionnelsante\?_nfpb=true&_pageLabel=vp_releves_mensuels_page',
        BillsPage
    )
    searchp = URL(
        r'/PortailPS/appmanager/portailps/professionnelsante\?_nfpb=true&_pageLabel=vp_recherche_par_date_paiements_page',
        SearchPage
    )
    historyp = URL(
        r'/PortailPS/appmanager/portailps/professionnelsante\?_nfpb=true&_windowLabel=vp_recherche_paiement_tiers_payant_portlet_1&vp_recherche_paiement_tiers_payant_portlet_1_actionOverride=%2Fportlets%2Fpaiements%2Frecherche&_pageLabel=vp_recherche_par_date_paiements_page',
        HistoryPage
    )

    logged = False

    def do_login(self):
        self.logger.debug('call Browser.do_login')
        if self.logged:
            return True

        self.loginp.stay_or_go()
        if self.homep.is_here():
            self.logged = True
            return True

        self.page.login(self.username, self.password)

        if not self.homep.is_here():
            raise BrowserIncorrectPassword()

        self.logged = True

    @need_login
    def get_subscription_list(self):
        self.logger.debug('call Browser.get_subscription_list')
        self.accountp.stay_or_go()
        return self.page.iter_subscription_list()

    @need_login
    def get_subscription(self, id):
        return self.get_subscription_list()

    @need_login
    def iter_history(self, subscription):
        self.searchp.stay_or_go()

        date_deb = self.page.doc.xpath(
            '//input[@name="vp_recherche_paiement_tiers_payant_portlet_1dateDebutRecherche"]'
        )[0].value
        date_fin = self.page.doc.xpath(
            '//input[@name="vp_recherche_paiement_tiers_payant_portlet_1dateFinRecherche"]'
        )[0].value

        data = {
            'vp_recherche_paiement_tiers_payant_portlet_1dateDebutRecherche': date_deb,
            'vp_recherche_paiement_tiers_payant_portlet_1dateFinRecherche': date_fin,
            'vp_recherche_paiement_tiers_payant_portlet_1codeOrganisme': 'null',
            'vp_recherche_paiement_tiers_payant_portlet_1actionEvt': 'rechercheParDate',
            'vp_recherche_paiement_tiers_payant_portlet_1codeRegime': '01',
        }

        self.session.headers.update({'Content-Type': 'application/x-www-form-urlencoded'})
        self.historyp.go(data=urlencode(data))
        if self.historyp.is_here():
            return self.page.iter_history()

    @need_login
    def get_details(self, sub):
        det = Detail()
        det.id = sub.id
        det.label = sub.label
        det.infos = ''
        det.price = Decimal('0.0')
        return det

    @need_login
    def iter_documents(self):
        self.billsp.stay_or_go()
        return self.page.iter_documents()

    @need_login
    def get_document(self, id):
        for b in self.iter_documents():
            if id == b.id:
                return b
        return None

    @need_login
    def download_document(self, bill):
        request = self.open(bill.url, data=bill._data, stream=True)
        return request.content
