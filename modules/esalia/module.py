# -*- coding: utf-8 -*-

# Copyright(C) 2016      Edouard Lambert
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


from woob.tools.backend import AbstractModule, BackendConfig
from woob.tools.value import ValueBackendPassword, Value
from woob.capabilities.wealth import CapBankWealth
from woob.capabilities.bill import CapDocument
from woob.capabilities.profile import CapProfile

from .browser import EsaliaBrowser


__all__ = ['EsaliaModule']


class EsaliaModule(AbstractModule, CapBankWealth, CapDocument, CapProfile):
    NAME = 'esalia'
    DESCRIPTION = u'Société Générale Épargne Salariale'
    MAINTAINER = u'Edouard Lambert'
    EMAIL = 'elambert@budget-insight.com'
    LICENSE = 'LGPLv3+'
    VERSION = '3.1'
    CONFIG = BackendConfig(
             ValueBackendPassword('login',    label='Identifiant', masked=False),
             ValueBackendPassword('password', label='Code secret', regexp='^(\d{6})$'),
             Value('otp', label='Code unique temporaire', default=''),
    )

    BROWSER = EsaliaBrowser
    PARENT = 's2e'

    def create_default_browser(self):
        return self.create_browser(self.config, weboob=self.weboob)
