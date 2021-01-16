# -*- coding: utf-8 -*-
#########################################################
# python
import os
import re
import sys
import traceback
from datetime import datetime

try:
    from urllib import quote, unquote  # Python 2.X
except ImportError:
    from urllib.parse import quote, unquote  # Python 3+

# third-party
import requests
from lxml import html
from flask import Response

# sjva 공용
from framework import db, scheduler, app
from framework.util import Util

# 패키지
from .plugin import logger, package_name
from .model import ModelSetting

ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) ' \
     'Chrome/69.0.3497.100 Safari/537.36'

#########################################################


class Logic(object):
    # 디폴트 세팅값
    db_default = {
        'site_url': '',
        'http_proxy': '',
    }

    session = None

    @staticmethod
    def db_init():
        try:
            for key, value in Logic.db_default.items():
                if db.session.query(ModelSetting).filter_by(key=key).count() == 0:
                    db.session.add(ModelSetting(key, value))
            db.session.commit()
        except Exception as e:
            logger.error('Exception: %s', str(e))
            logger.error(traceback.format_exc())

    @staticmethod
    def plugin_load():
        try:
            # DB 초기화
            Logic.db_init()

            # 편의를 위해 json 파일 생성
            from .plugin import plugin_info
            Util.save_from_dict_to_json(plugin_info, os.path.join(os.path.dirname(__file__), 'info.json'))

            #
            # 자동시작 옵션이 있으면 보통 여기서
            #            
            sess = requests.Session()
            sess.headers.update({'User-Agent': ua, 'Referer': None})
            http_proxy = ModelSetting.get('http_proxy')
            if http_proxy:
                proxies = {
                    'http': http_proxy,
                    'https': http_proxy
                }
                sess.proxies.update(proxies)
            Logic.session = sess
        except Exception as e:
            logger.error('Exception: %s', str(e))
            logger.error(traceback.format_exc())

    @staticmethod
    def plugin_unload():
        try:
            logger.debug('%s plugin_unload', package_name)
        except Exception as e:
            logger.error('Exception: %s', str(e))
            logger.error(traceback.format_exc())

    @staticmethod
    def setting_save(req):
        try:
            for key, value in req.form.items():
                logger.debug('Key:%s Value:%s', key, value)
                entity = db.session.query(ModelSetting).filter_by(key=key).with_for_update().first()
                entity.value = value
            db.session.commit()
            return True
        except Exception as e:
            logger.error('Exception: %s', str(e))
            logger.error(traceback.format_exc())
            return False

    # 기본 구조 End
    ##################################################################

    @staticmethod
    def tf_list(b_id, page='1', search=None):
        site_url = ModelSetting.get('site_url').rstrip('/')
        src_url = site_url + '/board.php?mode=list&b_id={}&page={}'.format(b_id, page)
        if search:
            src_url += '&sc=%s&x=0&y=0' % search

        items = []
        res = Logic.session.get(src_url)
        doc = html.fromstring(res.content)

        for list_item in doc.xpath('//div[@class="list_subject" and a[contains(@class,"stitle")]]'):
            subject = list_item.xpath('./a[contains(@class, "stitle")]')[0]
            subtitle = list_item.xpath(u'./span[contains(text(), "한글")]')
            item = {
                'title': subject.text_content().strip(),
                'link': subject.get('href').split('?')[1],
                'subtitle': bool(subtitle),
            }
            items.append(item)
        return items

    @staticmethod
    def tf_view(url):
        res = Logic.session.get(url)
        doc = html.fromstring(res.content)
        
        title_proper = doc.xpath('//div[@class="view_title"]')[0].text_content()
        title_proper = (']'.join(title_proper.split(']')[1:])).strip()

        published_at = doc.xpath('//tr/td[@class="view_t3"]')[0].text_content()
        published_at = ':'.join(published_at.split(':')[1:]).strip()
        published_at = datetime.strptime(published_at, '%Y-%m-%d %H:%M:%S')

        # list up items
        items = []
        for html_item in doc.xpath('//tr/td[@class="view_t4"]'):
            item = {}
            if html_item.xpath('./a[contains(text(), ".torrent")]'):
                item['type'] = 'torrent'
                item['filename'] = html_item.xpath('./a')[0].text_content().strip()
                item['url'] = html_item.xpath('./a')[0].get('href')
            elif html_item.xpath('./a[contains(text(), ".smi") or contains(text(), ".srt") or contains(text(), ".ass")]'):
                item['type'] = 'subtitle'
                item['filename'] = html_item.xpath('./a')[0].text_content().strip()
                item['url'] = html_item.xpath('./a')[0].get('href')
            else:
                item['type'] = 'etc'
                item['filename'] = html_item.xpath('./a')[0].text_content().strip()
                item['url'] = html_item.xpath('./a')[0].get('href')
            items.append(item)
        logger.debug('Found {} items'.format(len(items)))

        return {
            'page_url': url,
            'title_proper': title_proper,
            'published_at': published_at,
            'items': items,
        }

    @staticmethod
    def tf_down(query_string, item_no='0'):
        src_url = ModelSetting.get('site_url').rstrip('/') + '/board.php?' + query_string
        
        view = Logic.tf_view(src_url)

        Logic.session.headers.update({'Referer': src_url})
        
        item_no = int(item_no)
        down_url = view['items'][item_no]['url']
        filename = view['items'][item_no]['filename']

        if 'download.php' in down_url:
            fcontent = Logic.session.get(down_url).content
            resp = Response(fcontent)
        else:
            fcontent = Logic.download_filetender(down_url, filename)
            resp = Response(fcontent)
        resp.headers['Content-Type'] = 'application/octet-stream'
        resp.headers['Content-Disposition'] = "attachment; filename*=UTF-8''{}".format(quote(filename.encode('utf8')))
        
        try:
            import libtorrent
            torrent_dict = libtorrent.bdecode(fcontent)
            torrent_info = libtorrent.torrent_info(torrent_dict)
            torrent_name = torrent_info.name().encode()
            resp.headers['Content-Type'] = 'application/x-bittorrent'

            # 가끔 본문의 파일명에 &가 scrub 되는 경우가 있다.
            torrent_name_scrub = torrent_name.replace('& ', '').replace(' &', '').replace('&', ' ')
            filename_scrub = filename.replace('.torrent', '')
            chklen = int(min(len(torrent_name_scrub), len(filename_scrub))*0.4)
            if torrent_name_scrub[:chklen] != filename_scrub[:chklen]:
                # 여기서 raise Error 해주지 않으면 잘못된 torrent가 filetender로부터 유입돼도 OK됨
                raise ValueError('torrent filename %s is different from expected %s' % (torrent_name_scrub, filename))
                # filename = torrent_name + '.torrent'
        except Exception as e:
            logger.error('Exception: %s', str(e))
            logger.error(traceback.format_exc())

        return resp

    @staticmethod
    def download_filetender(ftender_short, filename):
        """download files from filetender
        :param ftender_short: http://www.filetender.com/UIj7z
        :param filename: Recoil.2011.1080p.BluRay.H264.AAC-RARBG.torrent
        :param referer: http://www.tfreeca22.com/board.php?mode=view&b_id=tmovie&id=359715&page=1
        :return:
        """
        resp = Logic.session.get(ftender_short)
        doc = html.fromstring(resp.content)

        form_method = doc.xpath('//form')[0].get('method')
        input_hidden = doc.xpath('//input[@type="hidden"]')
        params = {x.get('name'): x.get('value') for x in input_hidden}
        # headers = {'Referer': ftender_short, 'User-Agent': ua}

        ftender_hidden = 'https://file.filetender.net/file7.php'
        for scr_element in doc.xpath('//script[not(@scr)]'):
            script_text = scr_element.text_content()
            if 'filetender' in script_text:
                ftender_hidden = re.findall(r'(?:https?://)?[\w/\-?=%.]+\.[\w/\-?=%.]+', script_text)[0]

        if form_method.lower() == 'post':
            res = Logic.session.post(ftender_hidden, data=params)
        else:
            res = Logic.session.get(ftender_hidden, params=params)
        res.raise_for_status()

        if 'Content-Disposition' in res.headers:
            fname_from_header = re.findall('filename="(.+)"', res.headers['Content-Disposition'])[0]
            fname_from_header = unquote(fname_from_header)
            # 가끔 본문의 파일명에 &가 scrub 되는 경우가 있다.
            fname_from_header = fname_from_header.replace('& ', '').replace(' &', '').replace('&', ' ')
            if filename != fname_from_header:
                raise ValueError('Filename mismatch: {} != {}'.format(filename, fname_from_header))
        return res.content
