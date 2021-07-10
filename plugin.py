# -*- coding: utf-8 -*-
import os

# third-party
from flask import Blueprint

# app common
from framework.logger import get_logger
from framework.common.plugin import get_model_setting, Logic, default_route_single_module


class PlugIn(object):
    package_name = __name__.split('.')[0]
    logger = get_logger(package_name)
    ModelSetting = get_model_setting(package_name, logger, table_name=f'plugin_{package_name}_setting')

    blueprint = Blueprint(
        package_name, package_name,
        url_prefix=f'/{package_name}',
        template_folder=os.path.join(os.path.dirname(__file__), 'templates')
    )

    plugin_info = {
        "category_name": "torrent",
        "version": "0.1.0",
        "name": "tf_viewer",
        "home": "https://github.com/wiserain/tf_viewer",
        "more": "https://github.com/wiserain/tf_viewer",
        "description": "TF 실시간 정보를 보여주는 플러그인",
        "developer": "wiserain",
        "zip": "https://github.com/wiserain/tf_viewer/archive/main.zip",
        "icon": "",
    }

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
    home_module = 'tmovie'

    module_list = None
    logic = None

    def __init__(self):
        from framework import app, path_data
        db_file = os.path.join(path_data, 'db', f'{self.package_name}.db')
        app.config['SQLALCHEMY_BINDS'][self.package_name] = f'sqlite:///{db_file}'

        from framework.util import Util
        Util.save_from_dict_to_json(self.plugin_info, os.path.join(os.path.dirname(__file__), 'info.json'))


plugin = PlugIn()

from .logic import LogicMain
plugin.module_list = [LogicMain(plugin)]

# (logger, package_name, module_list, ModelSetting) required for Logic
plugin.logic = Logic(plugin)
# (;ogger, package_name, module_list, ModelSetting, blueprint, logic) required for default_route
default_route_single_module(plugin)
