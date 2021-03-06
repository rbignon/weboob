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


from datetime import datetime
import re
from decimal import Decimal

from woob.browser.pages import HTMLPage
from woob.capabilities.bill import DocumentTypes, Subscription, Detail, Bill
from woob.tools.compat import unicode


# Ugly array to avoid the use of french locale
FRENCH_MONTHS = [
    u'janvier',
    u'février',
    u'mars',
    u'avril',
    u'mai',
    u'juin',
    u'juillet',
    u'août',
    u'septembre',
    u'octobre',
    u'novembre',
    u'décembre',
]


class LoginPage(HTMLPage):
    def login(self, login, password):
        form = self.get_form('//form[@name="connexionCompteForm"]')
        form['vp_connexion_portlet_1numPS'] = login.encode('utf8')
        form['vp_connexion_portlet_1password'] = password.encode('utf8')
        form.submit()


class HomePage(HTMLPage):
    def on_loaded(self):
        pass


class SearchPage(HTMLPage):
    def on_loaded(self):
        pass


class AccountPage(HTMLPage):
    def iter_subscription_list(self):
        ident = self.doc.xpath('//div[@id="identification"]')[0]
        prof = self.doc.xpath('//div[@id="profession"]')[0]
        name = ident.xpath('//p/b')[0].text.replace('&nbsp;', ' ').strip()
        number = ident.xpath('//p')[1].text.replace('Cabinet', '').strip()
        label = prof.xpath('//div[@class="zoneTexte"]')[0].text.strip()
        sub = Subscription(number)
        sub._id = number
        sub.label = unicode(name) + ' ' + unicode(label)
        sub.subscriber = unicode(name)
        return sub


class HistoryPage(HTMLPage):
    def iter_history(self):
        tables = self.doc.xpath('//table[contains(concat(" ", @class, " "), " cTableauTriable ")]')
        if len(tables) > 0:
            lines = tables[0].xpath('.//tr')
            sno = 0
            for tr in lines:
                list_a = tr.xpath('.//a')
                if len(list_a) == 0:
                    continue
                date = tr.xpath('.//td')[0].text.strip()
                lot = list_a[0].text.replace('(*)', '').strip()
                if lot == 'SNL':
                    sno = sno + 1
                    lot = lot + str(sno)
                factures = tr.xpath('.//div[@class="cAlignGauche"]/a')
                factures_lbl = ''
                for a in factures:
                    factures_lbl = factures_lbl + a.text.replace('(**)', '').strip() + ' '
                montant = tr.xpath('.//div[@class="cAlignDroite"]')[0].text.strip()
                det = Detail()
                det.id = u'' + lot
                det.label = u'' + lot
                det.infos = u'' + factures_lbl
                det.datetime = datetime.strptime(date, "%d/%m/%Y").date()
                det.price = Decimal(montant.replace(',', '.'))
                yield det


class BillsPage(HTMLPage):
    def iter_documents(self):
        table = self.doc.xpath('//table[@id="releveCompteMensuel"]')[0].xpath('.//tr')
        for tr in table:
            list_tds = tr.xpath('.//td')
            if len(list_tds) == 0:
                continue

            date_str = tr.xpath('.//td[@class="cAlignGauche"]')[0].text
            month_str = date_str.split()[0]
            date = datetime.strptime(
                re.sub(month_str, str(FRENCH_MONTHS.index(month_str) + 1), date_str), "%m %Y"
            ).date()
            amount = tr.xpath('.//td[@class="cAlignDroite"]')[0].text
            amount = re.sub(r'[^\d,-]+', '', amount)
            for format in ('CSV', 'PDF'):
                bil = Bill()
                bil.id = date.strftime("%Y%m") + format
                bil.date = date
                clean_amount = amount.strip().replace(',', '.')
                if clean_amount != '':
                    bil.price = Decimal('-' + clean_amount)
                else:
                    bil.price = 0
                bil.label = u'' + date.strftime("%Y%m%d")
                bil.format = u'' + format
                bil.type = DocumentTypes.BILL
                filedate = date.strftime("%m%Y")
                bil.url = u'/PortailPS/fichier.do'
                bil._data = {
                    'FICHIER.type': format.lower() + '.releveCompteMensuel',
                    'dateReleve': filedate,
                    'FICHIER.titre': 'Releve' + filedate,
                }
                yield bil
