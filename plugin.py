from pathlib import Path

# third-party
from flask import Blueprint

# pylint: disable=import-error
from framework import app, path_data
from framework.util import Util
from framework.logger import get_logger
from framework.common.plugin import get_model_setting, Logic, default_route_single_module


class PlugIn:
    package_name = __name__.split(".", maxsplit=1)[0]
    logger = get_logger(package_name)
    ModelSetting = get_model_setting(package_name, logger, table_name=f"plugin_{package_name}_setting")

    blueprint = Blueprint(
        package_name,
        package_name,
        url_prefix=f"/{package_name}",
        template_folder=Path(__file__).parent.joinpath("templates"),
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
        "main": [package_name, "티프리카"],
        "sub": [
            ["setting", "설정"],
            ["tmovie", "영화"],
            ["tdrama", "드라마"],
            ["tent", "예능"],
            ["tv", "TV"],
            ["tani", "애니"],
            ["tmusic", "음악"],
            ["log", "로그"],
        ],
        "category": "torrent",
    }
    home_module = "tmovie"

    module_list = None
    logic = None

    def __init__(self):
        db_file = Path(path_data).joinpath("db", f"{self.package_name}.db")
        app.config["SQLALCHEMY_BINDS"][self.package_name] = f"sqlite:///{db_file}"

        Util.save_from_dict_to_json(self.plugin_info, Path(__file__).parent.joinpath("info.json"))


plugin = PlugIn()

from .logic import LogicMain

plugin.module_list = [LogicMain(plugin)]

# (logger, package_name, module_list, ModelSetting) required for Logic
plugin.logic = Logic(plugin)
# (;ogger, package_name, module_list, ModelSetting, blueprint, logic) required for default_route
default_route_single_module(plugin)
