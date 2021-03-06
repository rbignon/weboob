# -*- coding: utf-8 -*-

# Copyright(C) 2019 Romain Bignon
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

from woob.browser import AbstractBrowser


class GroupamaBrowser(AbstractBrowser):
    PARENT = 'ganpatrimoine'
    PARENT_ATTR = 'package.browser.GanPatrimoineBrowser'

    def __init__(self, website, *args, **kwargs):
        super(GroupamaBrowser, self).__init__(website, *args, **kwargs)
        self.website = website
        self.BASEURL = 'https://espaceclient.%s.fr' % website
