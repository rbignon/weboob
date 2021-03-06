# -*- coding: utf-8 -*-

# Copyright(C) 2010-2012 Nicolas Duhamel
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

import datetime
import re

from woob.capabilities.base import NotAvailable, empty
from woob.capabilities.bank import Account, Transaction as BaseTransaction
from woob.capabilities.wealth import Investment
from woob.exceptions import BrowserUnavailable
from woob.tools.capabilities.bank.transactions import FrenchTransaction
from woob.browser.pages import LoggedPage, JsonPage
from woob.browser.elements import TableElement, ItemElement, method, DictElement
from woob.browser.filters.html import Link, TableCell
from woob.browser.filters.standard import (
    CleanDecimal, CleanText, Eval, Async, AsyncLoad, Date, Env, Format,
    Regexp, Base, Coalesce, Currency,
)
from woob.browser.filters.json import Dict
from woob.tools.compat import urljoin

from .base import MyHTMLPage


class Transaction(FrenchTransaction):
    PATTERNS = [
        (re.compile(r'^(?P<category>CHEQUE)( N)? (?P<text>.*)'), FrenchTransaction.TYPE_CHECK),
        (
            re.compile(r'^(?P<category>ACHAT CB) (?P<text>.*) (?P<dd>\d{2})\.(?P<mm>\d{2}).(?P<yy>\d{2,4}).*'),
            FrenchTransaction.TYPE_CARD,
        ),
        (re.compile(r'^(?P<category>ACHAT CB) EN COURS.*'), FrenchTransaction.TYPE_CARD),
        (
            re.compile(r'^(?P<category>(PRELEVEMENT|TELEREGLEMENT|TIP)) (DE )?(?P<text>.*)'),
            FrenchTransaction.TYPE_ORDER,
        ),
        (re.compile(r'^(?P<category>ECHEANCEPRET)(?P<text>.*)'), FrenchTransaction.TYPE_LOAN_PAYMENT),
        (
            re.compile(r'^CARTE X.\d{4} (?P<dd>\d{2})/(?P<mm>\d{2})/(?P<yy>\d{2,4}) A \d{2}H\d{2} (?P<text>(?P<category>RETRAIT DAB) .*)'),
            FrenchTransaction.TYPE_WITHDRAWAL,
        ),
        (
            re.compile(r'^(?P<category>RETRAIT DAB) (?P<dd>\d{2})/(?P<mm>\d{2})/(?P<yy>\d{2,4}) \d+H\d+ (?P<text>.*)'),
            FrenchTransaction.TYPE_WITHDRAWAL,
        ),
        (
            re.compile(r'^(?P<category>RETRAIT) (?P<text>.*) (?P<dd>\d{2})\.(?P<mm>\d{2})\.(?P<yy>\d{2,4})'),
            FrenchTransaction.TYPE_WITHDRAWAL,
        ),
        (re.compile(r'^(?P<category>VIR(EMEN)?T?) (DE |POUR )?(?P<text>.*)'), FrenchTransaction.TYPE_TRANSFER),
        (re.compile(r'^(?P<category>REMBOURST)(?P<text>.*)'), FrenchTransaction.TYPE_PAYBACK),
        (re.compile(r'^(?P<category>COMMISSIONS)(?P<text>.*)'), FrenchTransaction.TYPE_BANK),
        (re.compile(r'^(?P<category>FRAIS POUR)(?P<text>.*)'), FrenchTransaction.TYPE_BANK),
        (re.compile(r'^(?P<text>(?P<category>REMUNERATION).*)'), FrenchTransaction.TYPE_BANK),
        (re.compile(r'^(?P<category>REMISE DE CHEQUES?) (?P<text>.*)'), FrenchTransaction.TYPE_DEPOSIT),
        (re.compile(r'^(?P<category>VERSEMENT DAB) (?P<text>.*)'), FrenchTransaction.TYPE_DEPOSIT),
        (re.compile(r'^(?P<text>DEBIT CARTE BANCAIRE DIFFERE.*)'), FrenchTransaction.TYPE_CARD_SUMMARY),
        (re.compile(r'^(?P<category>COTISATION TRIMESTRIELLE).*'), FrenchTransaction.TYPE_BANK),
        (re.compile(r'^REMISE COMMERCIALE.*'), FrenchTransaction.TYPE_BANK),
        (re.compile(r'^(?P<category>.*UTILISATION DU DECOUVERT$)'), FrenchTransaction.TYPE_BANK),
        (re.compile(r'^(?P<category>FRAIS (TRIMESTRIELS )?DE TENUE DE COMPTE).*'), FrenchTransaction.TYPE_BANK),
        (re.compile(r'^(?P<category>FRAIS IRREGULARITES ET INCIDENTS).*'), FrenchTransaction.TYPE_BANK),
        (re.compile(r'^(?P<category>COMMISSION PAIEMENT PAR CARTE)'), FrenchTransaction.TYPE_BANK),
        (re.compile(r'^(?P<text>(?P<category>INTERETS).*)'), FrenchTransaction.TYPE_BANK),
        (
            re.compile(r'^(?P<category>CREDIT CARTE BANCAIRE) (?P<text>.*) (?P<dd>\d{2})\.(?P<mm>\d{2})\.(?P<yy>\d{2,4}) .*'),
            FrenchTransaction.TYPE_CARD,
        ),
        (re.compile(r'^(?P<category>RETRAIT DAB)/TPE INTERNE$'), FrenchTransaction.TYPE_WITHDRAWAL),
    ]


class AccountHistory(LoggedPage, MyHTMLPage):
    def on_load(self):
        if bool(CleanText('//h2[contains(text(), "ERREUR")]')(self.doc)):
            raise BrowserUnavailable()

    def is_here(self):
        return not bool(CleanText('//h1[contains(text(), "tail de vos cartes")]')(self.doc))

    def get_next_link(self):
        for a in self.doc.xpath('//a[@class="btn_crt"]'):
            txt = ''.join([txt2.strip() for txt2 in a.itertext()])
            if 'mois précédent' in txt:
                return a.attrib['href']

    def get_history(self, deferred=False):
        """
        deffered is True when we are on a card page.
        """
        mvt_ligne = []
        if self.has_transactions():
            mvt_table = self.doc.xpath("//table[contains(@id, 'mouvements')]", smart_strings=False)[0]
            mvt_ligne = mvt_table.xpath("./tbody/tr")

        operations = []

        if deferred:
            # look for the card number, debit date, and if it is already debited
            txt = CleanText('//div[@class="infosynthese"]')(self.doc)
            m = re.search(r'sur votre carte n°\*\*\*\*\*\*(\d+)\*', txt)
            card_no = 'inconnu'
            if m:
                card_no = m.group(1)

            m = re.search(r'(\d+)/(\d+)/(\d+)', txt)
            if m:
                debit_date = datetime.date(*map(int, reversed(m.groups())))
            coming = 'En cours' in txt

            if not coming:
                # we must be on card account history: create a fake summary transaction
                tr = self.generate_card_summary()
                if tr.amount:
                    operations.append(tr)
                else:
                    assert not self.has_transactions()
        else:
            coming = False

        for mvt in mvt_ligne:
            op = Transaction()
            op.parse(
                date=CleanText('./td[@data-label="Date"]')(mvt),
                raw=CleanText('./td[@data-label="Libellé"]')(mvt),
            )

            if op.label.startswith('DEBIT CARTE BANCAIRE DIFFERE'):
                op.deleted = True

            op.amount = Coalesce(
                CleanDecimal.French('./td[@data-label="Euros"]', default=None),
                CleanDecimal.French('./td[@data-label="Credit"]', default=None),
                CleanDecimal.French('./td[@data-label="Debit"]', default=None)
            )(mvt)

            if deferred:
                op._cardid = 'CARTE %s' % card_no
                op.type = Transaction.TYPE_DEFERRED_CARD
                op.rdate = op.bdate = op.date
                op.date = debit_date
                # on card page, amounts are without sign
                if op.amount > 0:
                    op.amount = - op.amount

            op._coming = coming

            operations.append(op)
        return operations

    def generate_card_summary(self):
        tr = Transaction()
        text = CleanText('//div[@class="infosynthese"]')
        # card account: positive summary amount
        tr.amount = abs(CleanDecimal.French(
            Regexp(text, r'[Montant imputé le|cours prélevé au] \d+/\d+/\d+ : (.*) €')
        )(self.doc))
        tr.date = tr.rdate = Date(
            Regexp(text, r'[Montant imputé le|cours prélevé au] (\d+/\d+/\d+)'),
            dayfirst=True
        )(self.doc)
        tr.type = tr.TYPE_CARD_SUMMARY
        tr.label = 'DEBIT CARTE BANCAIRE DIFFERE'
        tr._coming = False
        return tr

    def has_transactions(self):
        return not CleanText(
            """//table[contains(@id, 'mouvements')]//tr[contains(., "as d'opération")]"""
        )(self.doc)

    @method
    class iter_transactions(TableElement):
        head_xpath = '//table[@id="mouvementsTable"]/thead/tr/th/a'
        item_xpath = '//table[@id="mouvementsTable"]/tbody/tr'

        col_date = re.compile('Date')
        col_label = re.compile('Libellé')
        col_amount = [re.compile('Montant'), re.compile('Valeur')]

        class item(ItemElement):
            klass = Transaction

            def condition(self):
                return self.page.has_transactions()

            obj_date = Date(CleanText(TableCell('date')), dayfirst=True)
            obj_amount = CleanDecimal(TableCell('amount'), replace_dots=True)
            obj__coming = Env('coming', False)

            def parse(self, el):
                raw_label = CleanText(TableCell('label'))(self)
                label = CleanText(TableCell('label')(self)[0].xpath('./br/following-sibling::text()'))(self)

                if (label and label.split()[0] != raw_label.split()[0]) or not label:
                    label = raw_label

                self.env['raw_label'] = Base(TableCell('label'), CleanText('a'))(self) or label

            obj_raw = Transaction.Raw(Env('raw_label'))

    def get_single_card(self, parent_id):
        div, = self.doc.xpath('//div[@class="infosynthese"]')

        ret = Account()
        ret.type = Account.TYPE_CARD
        ret.coming = CleanDecimal(
            Regexp(
                CleanText('.'),
                r'cours prélevé au \d+/\d+/\d+ : ([\d\s,-]+) [euros|€]'
            ),
            replace_dots=True
        )(div)
        ret.number = Regexp(CleanText('.'), r'sur votre carte [nN]°([\d*]+)')(div)
        ret.id = '%s.%s' % (parent_id, ret.number)
        ret.currency = 'EUR'
        ret.label = 'CARTE %s' % ret.number
        ret.url = self.url
        return ret


class CardsList(LoggedPage, MyHTMLPage):
    def is_here(self):
        return bool(
            CleanText('//h1[contains(text(), "tail de vos cartes")]')(self.doc)
            and not CleanText('//h1[contains(text(), "tail de vos op")]')(self.doc)
        )

    @method
    class get_cards(TableElement):
        item_xpath = '//table[@class="dataNum"]/tbody/tr'
        head_xpath = '//table[@class="dataNum"]/thead/tr/th'

        col_label = re.compile('Vos cartes Encours actuel prélevé au')
        col_balance = 'Euros'
        col_number = 'Numéro'
        col__credit = 'Crédit (euro)'
        col__debit = 'Débit (euro)'

        class item(ItemElement):
            klass = Account

            obj_type = Account.TYPE_CARD
            obj_currency = 'EUR'
            obj_number = CleanText(TableCell('number'))
            obj_label = Format('%s %s', CleanText(TableCell('label')), obj_number)
            obj_id = Format('%s.%s', Env('parent_id'), obj_number)

            def obj_coming(self):
                comings = (
                    CleanDecimal(TableCell('balance', default=None), replace_dots=True, default=None)(self),
                    CleanDecimal(TableCell('_credit', default=None), replace_dots=True, default=None)(self),
                    CleanDecimal(TableCell('_debit', default=None), replace_dots=True, default=None)(self),
                )

                for coming in comings:
                    if not empty(coming):
                        return coming
                else:
                    raise AssertionError("There should have at least 0.00 in debit column")

            def obj_url(self):
                td = TableCell('label')(self)[0].xpath('.//a')[0]
                return urljoin(self.page.url, td.attrib['href'])


class SavingAccountSummary(LoggedPage, MyHTMLPage):
    def on_load(self):
        link = Link('//ul[has-class("tabs")]//a[@title="Historique des mouvements"]', default=NotAvailable)(self.doc)
        if link:
            self.browser.location(link)

    def get_balance(self):
        return CleanDecimal(default=None, replace_dots=True).filter(
            self.doc.xpath('//dt[span[text()="Total des versements bruts"]]/following::dd[1]/span/strong/text()'))


class InvestTable(TableElement):
    col_label = 'Support'
    col_share = ['Poids en %', 'Répartition en %']
    col_quantity = 'Nb U.C'
    col_valuation = re.compile('Montant')


class InvestItem(ItemElement):
    klass = Investment

    obj_label = CleanText(TableCell('label', support_th=True))
    obj_portfolio_share = Eval(
        lambda x: x and x / 100,
        CleanDecimal(TableCell('share', support_th=True), replace_dots=True, default=NotAvailable)
    )
    obj_quantity = CleanDecimal(TableCell('quantity', support_th=True), replace_dots=True, default=NotAvailable)
    obj_valuation = CleanDecimal(TableCell('valuation', support_th=True), replace_dots=True, default=NotAvailable)

    def validate(self, obj):
        # Skip investments with empty valuation
        return not empty(obj.valuation)


class CachemireCatalogPage(LoggedPage, MyHTMLPage):
    def on_load(self):
        self.product_codes = self.load_product_codes()

    def load_product_codes(self):
        # store ISIN codes in a dictionary with a (label: isin) fashion
        product_codes = {}
        for table in self.doc.xpath('//table/tbody'):
            for row in table.xpath('//tr[contains(./th/@scope,"row")]'):
                label = CleanText('./th[1]', default=None)(row)
                isin_code = CleanText('./td[1]', default=None)(row)
                if label and isin_code:
                    product_codes[label.upper()] = isin_code
        return product_codes


class LifeInsuranceSummary(LoggedPage, MyHTMLPage):
    def get_opening_date(self):
        return Date(
            CleanText('//dt[span/text()="Date d\'effet :"]/following-sibling::dd[1]'),
            dayfirst=True,
            default=NotAvailable,
        )(self.doc)


class LifeInsuranceInvest(LoggedPage, MyHTMLPage):
    def has_error(self):
        return 'erreur' in CleanText('//p[has-class("titlePage")]')(self.doc) or 'ERREUR' in CleanText('//h2')(self.doc)

    def get_cachemire_link(self):
        return Link('//a[contains(@title, "espace cachemire")]', default=None)(self.doc)

    @method
    class iter_investments(InvestTable):
        head_xpath = '//table[starts-with(@id, "mouvements")]/thead//th'
        item_xpath = '//table[starts-with(@id, "mouvements")]/tbody//tr'

        col_unitvalue = 'Valeur Liquidative'
        col_vdate = 'Date'

        class item(InvestItem):
            obj_unitvalue = CleanDecimal(TableCell('unitvalue'), replace_dots=True, default=NotAvailable)
            obj_vdate = Date(CleanText(TableCell('vdate')), dayfirst=True, default=NotAvailable)


class LifeInsuranceHistory(LoggedPage, MyHTMLPage):
    @method
    class get_history(TableElement):
        head_xpath = '//table[@id="options"]/thead//th'
        item_xpath = '//table[@id="options"]/tbody//tr'

        col_date = 'Date de valeur'
        col_amount = 'Montant'
        col_label = "Type d'opération"

        class item(ItemElement):
            klass = BaseTransaction

            obj_label = CleanText(TableCell('label'))
            obj_amount = CleanDecimal(TableCell('amount'), replace_dots=True)
            obj_date = Date(CleanText(TableCell('date')), dayfirst=True)
            obj__coming = False

            load_invs = Link('.//a', default=NotAvailable) & AsyncLoad

            def obj_investments(self):
                try:
                    page = Async('invs').loaded_page(self)

                    return list(page.iter_investments())
                except AttributeError:  # No investments available
                    return list()


class LifeInsuranceHistoryInv(LoggedPage, MyHTMLPage):
    @method
    class iter_investments(InvestTable):
        head_xpath = '//table/thead//th'
        item_xpath = '//table/tbody//tr[count(td) >= 1 and count(th) = 1]'

        def parse(self, el):
            if len(el.xpath('//table/thead//th')) <= 2:
                raise AttributeError()  # Don't handle multiple invests in same tr

        class item(InvestItem):
            pass


class RetirementHistory(LoggedPage, MyHTMLPage):
    @method
    class get_history(TableElement):
        head_xpath = '//table[@id="mvt" or @id="options" or @id="mouvements"]/thead//th'
        item_xpath = '//table[@id="mvt" or @id="options" or @id="mouvements"]/tbody//tr'

        col_date = re.compile('Date')
        col_label = "Type d'opération"
        col_amount = 'Montant'

        class item(ItemElement):
            klass = BaseTransaction

            obj_label = CleanText(TableCell('label'))
            obj_date = Date(CleanText(TableCell('date')), dayfirst=True)
            obj_amount = CleanDecimal(TableCell('amount'), replace_dots=True)
            obj__coming = False


class TemporaryPage(LoggedPage, MyHTMLPage):
    def get_next_link(self):
        return self.absurl(
            Regexp(
                CleanText('//script'),
                r'location.replace\([\'"](.*)[\'"]\)'
            )(self.doc)
        )


class CardsJsonDetails(LoggedPage, JsonPage):
    @method
    class iter_cards(DictElement):
        item_xpath = 'cartouchesCarte'

        def condition(self):
            return self.page.doc.get('userMessage', '') != 'Aucune carte'

        class item(ItemElement):
            klass = Account

            def condition(self):
                return CleanText(Dict('typeDeDebit'))(self) == 'DIFFÉRÉ'

            obj_type = Account.TYPE_CARD
            obj_number = CleanText(Dict('numeroPanTronque'), replace=[(' ', '')])
            obj_coming = CleanDecimal.US(
                Dict('encoursCarte/listeOuverte/0/montantEncours', default=None),
                default=NotAvailable
            )
            obj_currency = Currency(
                Dict('encoursCarte/listeOuverte/0/deviseEncours', default=''),
                default=NotAvailable
            )

            def obj_id(self):
                return '%s.%s' % (Env('parent_id')(self), self.obj.number)

            def obj_label(self):
                return 'CARTE %s' % self.obj.number

    def generate_summary(self, card):
        for item in self.doc['cartouchesCarte']:
            if CleanText(Dict('numeroPanTronque'), replace=[(' ', '')])(item) != card.number:
                continue
            if empty(card.coming):
                continue
            tr = Transaction()
            # card account: positive summary amount
            tr.amount = abs(card.coming)
            tr.date = tr.rdate = Date(Dict('encoursCarte/listeOuverte/0/dateEncours'))(item)
            tr.type = tr.TYPE_CARD_SUMMARY
            tr.label = 'DEBIT CARTE BANCAIRE DIFFERE'
            tr._coming = False
            return [tr]
        return []
