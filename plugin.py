# -*- coding: utf-8 -*-
#########################################################
# 고정영역
#########################################################
# python
import os
import re
import traceback

try:
    from urllib import quote  # Python 2.X
    from urlparse import parse_qs
except ImportError:
    from urllib.parse import quote, parse_qs  # Python 3+

# third-party
from flask import Blueprint, request, render_template, redirect, jsonify, Response
from flask_login import login_required

# sjva 공용
from framework.logger import get_logger
from framework import app, db, scheduler, check_api

# 패키지
package_name = __name__.split('.')[0]
logger = get_logger(package_name)

from .logic import Logic
from .model import ModelSetting

blueprint = Blueprint(
    package_name, package_name,
    url_prefix='/%s' % package_name,
    template_folder=os.path.join(os.path.dirname(__file__), 'templates')
)


def plugin_load():
    Logic.plugin_load()


def plugin_unload():
    Logic.plugin_unload()


plugin_info = {
    "category_name": "torrent",
    "version": "0.0.6",
    "name": "tf_viewer",
    "home": "https://github.com/wiserain/tf_viewer",
    "more": "https://github.com/wiserain/tf_viewer",
    "description": "TF 실시간 정보를 보여주는 SJVA 플러그인",
    "developer": "wiserain",
    "zip": "https://github.com/wiserain/tf_viewer/archive/main.zip",
    "icon": "",
}
#########################################################


# 메뉴 구성.
menu = {
    'main': [package_name, '티프리카'],
    'sub': [
        ['setting', '설정'], 
        ['tmovie', '영화'], 
        ['tdrama', '드라마'], 
        ['tent', '예능'],
        ['tv', 'TV'], 
        ['tani', '애니'], 
        ['tmusic', '음악'], 
        ['log', '로그']
    ],
    'category': 'torrent',
}


#########################################################
# WEB Menu
#########################################################
@blueprint.route('/')
def home():
    return redirect('/%s/tmovie' % package_name)


@blueprint.route('/<sub>')
@login_required
def detail(sub):
    if sub == 'setting':
        arg = ModelSetting.to_dict()
        arg['package_name'] = package_name
        return render_template('%s_setting.html' % package_name, sub=sub, arg=arg)
    elif sub.startswith('t'):
        arg = ModelSetting.to_dict()
        arg.update({
            'package_name': package_name,
            'downloader_installed': True,
            'offcloud_installed': True,
            'torrent_info_installed': True,
        })
        try:
            import downloader
        except ImportError:
            arg['downloader_installed'] = False
        try:
            import offcloud2
        except ImportError:
            arg['offcloud_installed'] = False
        try:
            import torrent_info
        except ImportError:
            arg['torrent_info_installed'] = False
        download_path = [''] + [x.strip() for x in arg['download_path'].split('\n') if x.strip()]
        download_path = {'down2path_{}'.format(i): {'name': v if v else 'default', 'icon': 'fa-folder-o'} for i, v in enumerate(download_path)}
        return render_template('%s_list.html' % package_name, sub=sub, arg=arg, download_path=download_path)
    elif sub == 'down' and request.method == 'GET':
        try:
            fcontent, filename = Logic.tf_down(
                request.query_string.decode('utf-8'),
                item_no=int(request.args.get('item_no', '0'))
            )
            resp = Response(fcontent)
            resp.headers['Content-Type'] = 'application/' + ('x-bittorrent' if filename.endswith('.torrent') else 'octet-stream')
            resp.headers['Content-Disposition'] = "attachment; filename*=UTF-8''{}".format(quote(filename.encode('utf8')))
            return resp
        except Exception as e:
            logger.error('Exception: %s', str(e))
            logger.error(traceback.format_exc())
    elif sub == 'log':
        return render_template('log.html', package=package_name)
    return render_template('sample.html', title='%s - %s' % (package_name, sub))


#########################################################
# For UI                                                          
#########################################################
@blueprint.route('/ajax/<sub>', methods=['GET', 'POST'])
@login_required
def ajax(sub):
    try:
        p = request.form.to_dict() if request.method == 'POST' else request.args.to_dict()
        # 설정 저장
        if sub == 'setting_save':
            ret = Logic.setting_save(request)
            return jsonify(ret)
        elif sub == 'list':
            search = p.get('search', '')
            page = p.get('page', '1')
            b_id = p.get('b_id')

            ret = Logic.tf_list(b_id, page=page, search=search)
            return jsonify({'success': True, 'list': ret})
        elif sub == 'get_src_url':
            href = p.get('href', '')
            if href:
                src_url = ModelSetting.get('site_url').rstrip('/') + '/board.php?' + href.split('?')[1]
                return jsonify({'success': True, 'url': src_url})
        elif sub == 'get_torrent_info':
            href = p.get('href', '')
            if href:
                query_string = href.split('?')[1]
                item_no = int(parse_qs(query_string).get('item_no', '0'))
                fcontent, _ = Logic.tf_down(query_string, item_no=item_no)
                from torrent_info import Logic as TorrentInfoLogic
                return jsonify({'success': True, 'info': TorrentInfoLogic.parse_torrent_file(fcontent)})
        elif sub == 'get_more':
            href = p.get('href', '')
            if href:
                src_url = ModelSetting.get('site_url').rstrip('/') + '/board.php?' + href.split('?')[1]
                items = Logic.tf_view(src_url)['items']
                if items and len(items) > 0:
                    return jsonify({'success': True, 'items': items})
                else:
                    return jsonify({'success': False, 'log': '다운로드 가능한 링크를 찾을 수 없음'})
        elif sub == 'add_download':            
            try:
                import downloader
                magnet = p.get('magnet', '')
                path_id = p.get('download_path_id')
                path_id = int(path_id.split('_')[1])
                path_list = [''] + [x.strip() for x in ModelSetting.get('download_path').split('\n') if x.strip()]
                download_path = path_list[path_id]
                result = downloader.Logic.add_download2(
                    magnet, ModelSetting.get('download_program'), download_path, request_type=package_name, request_sub_type=''
                )
                logger.debug(result)
                return jsonify({'success': True})
            except Exception as e:
                raise e
    except Exception as e:
        logger.error('Exception: %s', str(e))
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'log': str(e)})
