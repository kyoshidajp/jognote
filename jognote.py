#!/usr/bin/env python
# -*- coding:utf-8 -*-
"""
jognote.py

    JogNote(http://www.jognote.com)のデータをエクスポートします。

    $ python jognote.py -i userid -p password  \
        -s 2012/01 -e 2013/01 
"""

from bs4 import BeautifulSoup
from datetime import datetime
import mechanize
import cookielib
import re
import sys
import time
import logging
import optparse

__author__ = 'kyoshidajp <claddvd@gmail.com>'


class Workout(object):
    """
    ワークアウトクラス
    """

    RUN, SWIM, BIKE, WALK = range(4)

    def __init__(self, name=RUN):
        # 日付: datetime
        self.date = None
        # 種類: int
        #   0: RUN, 1: SWIM, 2: BIKE, 3: WALK
        self.name = name
        # 距離(km): str 
        self.distance = None
        # 時間: strのtuple
        self.time = None

    def __cmp__(self, other):
        """
        日付で比較
        """

        return cmp(self.date, other.date)

    def __str__(self):
        """
        文字列出力
        """

        return '%s,%s,%s,%s' \
            % (self.date.strftime('%Y/%m/%d %H:%M:%S'),
               str(self.name), self.distance, self.time)


class Jognote(object):
    """
    JogNoteクラス
    """

    def __init__(self, user_id, user_pass,
                 start_date, end_date, 
                 log_level=logging.WARNING):

        self.TOP_URL = 'http://www.jognote.com'
        self.EXPORT_START_DATE = '2011/01'
        self.date_format = '%Y/%m'
        self.today = datetime.now()

        # 1ページアクセスごとのスリープタイム
        self.__SLEEP_TIME = 2

        self.init_log(log_level)

        # ユーザ個別の番号
        self.user_num = None

        self.user_id, self.user_pass = self.get_account(user_id, user_pass)
        self.start_date, self.end_date = self.get_export_date(start_date, end_date)

        # ブラウザの作成
        self.browser = self.make_browser()

    def get_account(self, user_id, user_pass):
        """
        ログインアカウントの設定
        """

        if not (user_id and user_pass):
            logging.error('ユーザIDまたはパスワードが設定されていません。')
            sys.exit()

        # ログインアカウント情報
        return (user_id, user_pass)

    def get_export_date(self, start_date_str, end_date_str):
        """
        エクスポート対象日の設定
        """

        start_date, end_date = (None, None)

        try:
            if start_date_str:
                start_date = datetime.strptime(start_date_str,
                                               self.date_format)
            if end_date_str:
                end_date = datetime.strptime(end_date_str,
                                             self.date_format)
            if start_date > end_date:
                raise ValueError()
            pass
        except ValueError:
            logging.error('エクスポート開始日時または終了日時が正しく指定されていません。')
            sys.exit()

        # 未設定の場合はデフォルト日を設定
        if not start_date:
            start_date = datetime.strptime(EXPORT_START_DATE,
                                           date_format)
        if not end_date:
            end_date = self.today

        logging.debug('start date is %s/%s' 
            % (str(start_date.year), str(start_date.month)))
        logging.debug('end date is %s/%s' 
            % (str(end_date.year), str(end_date.month)))

        return (start_date, end_date)

    def login(self):
        """
        ログイン
        """

        self.browser.open('%s/top' % self.TOP_URL)
        self.browser.select_form(nr=1)
        self.browser.form['u[n]'] = self.user_id   
        self.browser.form['u[p]'] = self.user_pass 
        self.browser.submit()
        url = self.browser.geturl()

        num_re = re.compile(r'^%s/users/(\d+?)$' % self.TOP_URL)
        if not num_re.match(url):
            logging.error('アクセスに失敗しました。ユーザIDまたはパスワードを確認してください。')
            sys.exit()

        # ユーザ番号の取得
        self.user_num = self.get_user_number(url)

    def export(self):
        """
        データのエクスポート
        """

        self.login()

        history = []

        for year in range(self.start_date.year, self.end_date.year + 1):

            # エクスポート月の設定
            start_month, end_month = (1, 12)
            if year == self.start_date.year:
                start_month = self.start_date.month
                if year == self.end_date.year:
                    end_month = self.end_date.month

            for month in range(start_month, end_month + 1):
                logging.debug('%02d/%02d' % (year, month))
                history += self.__export_by_month(year, month)
                logging.debug('%02d/%02d has %d data.' 
                    % (year, month, len(history)))
                if self.is_today_month(year, month):
                    return history

        return history

    def is_today_month(self, year, month):
        """
        指定された日付が今月か判断
        """

        if year != self.today.year:
            return False
        if month != self.today.month:
            return False
        return True

    def __export_by_month(self, year, month):
        """
        月ごとのデータのエクスポート
        """

        try:
            self.browser.open('%s/user/%s/days?month=%s&year=%s' 
                % (self.TOP_URL, self.user_num, month, year))
        except mechanize.HTTPError:
            logging.error('アクセスに失敗しました。')
            sys.exit()

        body = self.browser.response().read()

        history = []

        day_matches = re.findall('/days/\d+', body)
        for day in list(set(day_matches)):

            self.browser.open(self.TOP_URL + day)
            body = self.browser.response().read()
            soup = BeautifulSoup(body)

            # date
            date = soup.find(id='workoutDate').h2
            date_str = self.get_date(date.get_text())

            # 各ワークアウトデータを取得
            history += self.get_history(soup, date_str)
            logging.debug('%s/%s%s' %(year, month, day))

            # 一休さん
            time.sleep(self.__SLEEP_TIME)

        history.sort()
        return history

    def get_history(self, soup, date_str):
        """
        ワークアウト履歴を取得
        """

        workout_dict =  {
            Workout.RUN  : 'workout_jogs',
            Workout.SWIM : 'workout_swims',
            Workout.BIKE : 'workout_bikes',
            Workout.WALK : 'workout_walks',
        }

        workouts = []
        keys = workout_dict.keys()
        for key in keys:
            div_soup = soup('div', {'class' : workout_dict[key]})
            for div in div_soup:
                workout = Workout(key)
                workout.date = date_str
                text = div.h4.get_text()
                workout.distance = self.get_distance(text)
                workout.time = self.get_time(text)
                workouts.append(workout)
        return workouts

    def make_browser(self):
        """
        擬似ブラウザを作成
        """
        browser = mechanize.Browser()

        cj = cookielib.LWPCookieJar()
        browser.set_cookiejar(cj)

        browser.set_handle_equiv(True)
        browser.set_handle_redirect(True)
        browser.set_handle_referer(True)
        browser.set_handle_robots(False)
        browser.set_handle_refresh(mechanize._http.HTTPRefreshProcessor(),
                                   max_time=1)

        browser.addheaders = [('User-agent',
                              ('Mozilla/5.0 (Windows; U; Windows NT 5.1; rv:1.7.3)'
                               ' Gecko/20041001 Firefox/0.10.1'))]
        return browser

    def get_date(self, raw_strings):
        """
        ワークアウトの日付を取得
        """

        strings = raw_strings.encode("utf-8")

        year_re = re.compile(r'(\d+?)年')
        month_re = re.compile(r'(\d+?)月')
        day_re = re.compile(r'(\d+?)日')

        year_match = year_re.search(strings)
        month_match = month_re.search(strings)
        day_match = day_re.search(strings)
        year = int(year_match.group(1)) if year_match else None
        month = int(month_match.group(1)) if month_match else None
        day = int(day_match.group(1)) if day_match else None
        return datetime(year, month, day)

    def get_distance(self, strings):
        """
        ワークアウトの距離を取得
        """

        distance_re = re.compile(r'\s([0-9.]+) km')

        distance_match = distance_re.search(strings)
        distance = distance_match.group(1) if distance_match else None
        return distance

    def get_time(self, raw_strings):
        """
        ワークアウトの時間を取得
        """

        strings = raw_strings.encode('utf-8')

        hour_re = re.compile(r'(\d+?)時間')
        min_re = re.compile(r'(\d+?)分')
        sec_re = re.compile(r'(\d+?)秒')

        hour_match = hour_re.search(strings)
        min_match = min_re.search(strings)
        sec_match = sec_re.search(strings)
        hour = hour_match.group(1) if hour_match else '0'
        min = min_match.group(1) if min_match else '0'
        sec = sec_match.group(1) if sec_match else '0'
        return (hour, min, sec)

    def get_user_number(self, url):
        """
        ログイン後のURLからユーザ個別の番号を取得
        """

        num_re = re.compile(r'^%s/users/(\d+?)$' % self.TOP_URL)
        num = None
        if (num_re.search(url)):
            num = num_re.search(url).group(1)
        return num

    def init_log(self, level):
        """
        ログの設定
        """

        try:
            format = '[%(levelname)s] %(message)s'
            logging.basicConfig(level=level, format=format)
        except ValueError:
            logging.error('ログレベルが正しく指定されていません。')
            sys.exit()


def get_opt():
    """
    コマンドラインオプションの解析
    """
    parser = optparse.OptionParser()

    # ログインID
    parser.add_option ('-i', '--userid',
                       dest = 'user_id',
                       help = 'Login id at JogNote. Cannot use OpenID\'s id.'
                       )
    # ログインパスワード
    parser.add_option ('-p', '--password',
                       dest = 'user_pass',
                       help = 'Login password at JogNote. Cannot use OpenID\'s password.'
                       )
    # エクスポート開始日時
    parser.add_option ('-s', '--startdate',
                       dest = 'start_date',
                       help = 'Start date of export. Input yyyy/mm. ex) 2010/01'
                       )
    # エクスポート終了日時
    parser.add_option ('-e', '--enddate',
                       dest = 'end_date',
                       help = 'End date of export. Input yyyy/mm. ex) 2011/12'
                       )
    # 出力ファイル名
    parser.add_option ('-o', '--output',
                       dest = 'output_filename',
                       default = 'export.csv',
                       help = 'Output file name'
                       )
    # ログレベル
    parser.add_option ('-l', '--loglevel',
                       dest = 'log_level',
                       default = 'WARNING',
                       help = 'Log level'
                       )
    options, remainder = parser.parse_args()
    return options

if __name__ == '__main__':

    # オプションの解析
    options = get_opt()
    userid = options.user_id
    password = options.user_pass
    start_date = options.start_date
    end_date = options.end_date
    output_filename = options.output_filename
    log_level = options.log_level

    jog = Jognote(userid, password, start_date, 
                  end_date, log_level)
    history = jog.export()

    # CSV出力
    import csv
    writer = csv.writer(open(output_filename, 'wb'))
    for data in history:
        time = ':'.join(data.time)
        writer.writerow([data.date, data.name, data.distance, time])
