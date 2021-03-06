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

from __future__ import unicode_literals

from woob.browser import URL
from woob.browser.browsers import LoginBrowser, need_login
from woob.exceptions import BrowserIncorrectPassword
from woob.browser.exceptions import ClientError

from .pages import SigninPage, UserPage, DocumentsPage
from .sensor_data import build_sensor_data, get_cf_date

sensor_data = build_sensor_data()


class TrainlineBrowser(LoginBrowser):
    BASEURL = 'https://www.thetrainline.com'

    signin = URL(r'/login-service/api/login', SigninPage)
    user_page = URL(r'/login-service/v5/user', UserPage)
    documents_page = URL(r'/my-account/api/bookings/past', DocumentsPage)

    def __init__(self, login, password, *args, **kwargs):
        super(TrainlineBrowser, self).__init__(login, password, *args, **kwargs)
        self.session.headers['X-Requested-With'] = 'XMLHttpRequest'

    def do_login(self):
        # set some cookies
        self.go_home()
        if self.session.cookies.get('_abck'):
            # _abck cookie is special, (you can find it to some other website also)
            # first we receive it with one value (which contains ~-1~ in the middle)
            # and we have to send it to receive it again but with another value
            # this new value is mandatory

            # update cookie _abck
            self.open('/staticweb/31b06785f73ti1714cafa96c8bd3eba79')
            data = {
                "sensor_data": sensor_data % (
                    self.session.headers['User-Agent'],
                    get_cf_date(),
                    self.session.cookies['_abck'],
                ),
            }
            self.open('/staticweb/31b06785f73ti1714cafa96c8bd3eba79', json=data)

        try:
            self.signin.go(json={'email': self.username, 'password': self.password})
        except ClientError as e:
            if e.response.status_code == 403:
                error = e.response.json().get('message')
                if 'invalid_grant' in error:
                    raise BrowserIncorrectPassword(error)
            raise

        self.user_page.go()

    @need_login
    def get_subscription_list(self):
        self.user_page.stay_or_go()
        yield self.page.get_subscription()

    @need_login
    def iter_documents(self, subscription):
        self.documents_page.go()
        return self.page.iter_documents(subid=subscription.id)
