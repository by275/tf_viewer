import re
import traceback
from datetime import datetime
from urllib.parse import unquote, quote, parse_qs

# third-party
from flask import request, render_template, jsonify, Response
import requests
from lxml import html

# pylint: disable=import-error
from framework.common.plugin import LogicModuleBase

# local
from .plugin import plugin

logger = plugin.logger
package_name = plugin.package_name
ModelSetting = plugin.ModelSetting

ua = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/69.0.3497.100 Safari/537.36"
)


class LogicMain(LogicModuleBase):
    db_default = {
        "site_url": "",
        "http_proxy": "",
        "download_program": "0",
        "download_path": "",
    }

    def __init__(self, P):
        super().__init__(P, None)
        self.session = None

    def plugin_load(self):
        try:
            sess = requests.Session()
            sess.headers.update({"User-Agent": ua, "Referer": None})
            http_proxy = ModelSetting.get("http_proxy")
            if http_proxy:
                proxies = {"http": http_proxy, "https": http_proxy}
                sess.proxies.update(proxies)
            self.session = sess
        except Exception as e:
            logger.error("Exception: %s", str(e))
            logger.error(traceback.format_exc())

    def process_menu(self, sub, req):
        arg = ModelSetting.to_dict()
        if sub == "setting":
            arg["package_name"] = package_name
            return render_template(f"{package_name}_{sub}.html", sub=sub, arg=arg)
        if sub.startswith("t") or sub == "adult":
            arg.update(
                {
                    "package_name": package_name,
                    "downloader_installed": True,
                    "offcloud_installed": True,
                    "torrent_info_installed": True,
                }
            )
            try:
                import downloader
            except ImportError:
                arg["downloader_installed"] = False
            try:
                import offcloud2
            except ImportError:
                arg["offcloud_installed"] = False
            try:
                import torrent_info
            except ImportError:
                arg["torrent_info_installed"] = False
            download_path = [""] + [x.strip() for x in arg["download_path"].splitlines() if x.strip()]
            download_path = {
                f"down2path_{i}": {"name": v if v else "default", "icon": "fa-folder-o"}
                for i, v in enumerate(download_path)
            }
            return render_template(f"{package_name}_list.html", sub=sub, arg=arg, download_path=download_path)
        if sub == "down" and request.method == "GET":
            try:
                fcontent, filename = self.tf_down(
                    request.query_string.decode("utf-8"), item_no=int(request.args.get("item_no", "0"))
                )
                resp = Response(fcontent)
                resp.headers["Content-Type"] = "application/" + (
                    "x-bittorrent" if filename.endswith(".torrent") else "octet-stream"
                )
                resp.headers["Content-Disposition"] = "attachment; filename*=UTF-8''" + quote(filename.encode("utf8"))
                return resp
            except Exception as e:
                logger.error("Exception: %s", str(e))
                logger.error(traceback.format_exc())
        return render_template("sample.html", title=f"{package_name} - {sub}")

    def process_ajax(self, sub, req):
        try:
            p = request.form.to_dict() if request.method == "POST" else request.args.to_dict()
            if sub == "list":
                search = p.get("search", "")
                page = p.get("page", "1")
                b_id = p.get("b_id")

                ret = self.tf_list(b_id, page=page, search=search)
                return jsonify({"success": True, "list": ret, "nomore": len(ret) != 35})
            if sub == "get_src_url":
                href = p.get("href", "")
                if href:
                    src_url = ModelSetting.get("site_url").rstrip("/") + "/board.php?" + href.split("?")[1]
                    return jsonify({"success": True, "url": src_url})
            if sub == "get_torrent_info":
                href = p.get("href", "")
                if href:
                    query_string = href.split("?")[1]
                    item_no = int(parse_qs(query_string).get("item_no", "0"))
                    fcontent, _ = self.tf_down(query_string, item_no=item_no)
                    from torrent_info import Logic as TorrentInfoLogic

                    return jsonify({"success": True, "info": TorrentInfoLogic.parse_torrent_file(fcontent)})
            if sub == "get_more":
                href = p.get("href", "")
                if href:
                    src_url = ModelSetting.get("site_url").rstrip("/") + "/board.php?" + href.split("?")[1]
                    items = self.tf_view(src_url)["items"]
                    if items and len(items) > 0:
                        return jsonify({"success": True, "items": items})
                    return jsonify({"success": False, "log": "다운로드 가능한 링크를 찾을 수 없음"})
            if sub == "add_download":
                try:
                    import downloader

                    magnet = p.get("magnet", "")
                    path_id = p.get("download_path_id")
                    path_id = int(path_id.split("_")[1])
                    path_list = [""] + [x.strip() for x in ModelSetting.get("download_path").splitlines() if x.strip()]
                    download_path = path_list[path_id]
                    result = downloader.Logic.add_download2(
                        magnet,
                        ModelSetting.get("download_program"),
                        download_path,
                        request_type=package_name,
                        request_sub_type="",
                    )
                    logger.debug(result)
                    return jsonify({"success": True})
                except Exception as e:
                    raise e
        except Exception as e:
            logger.error("Exception: %s", str(e))
            logger.error(traceback.format_exc())
            return jsonify({"success": False, "log": str(e)})

    def tf_list(self, b_id, page="1", search=None):
        site_url = ModelSetting.get("site_url").rstrip("/")
        src_url = site_url + f"/board.php?mode=list&b_id={b_id}&page={page}"
        if search:
            src_url += f"&sc={search}&x=0&y=0"

        items = []
        res = self.session.get(src_url)
        doc = html.fromstring(res.content)

        for list_item in doc.xpath('//tr[td/div[@class="list_subject" and a[contains(@class,"stitle")]]]'):
            subject = list_item.xpath('./td/div/a[contains(@class, "stitle")]')[0]
            subtitle = list_item.xpath('./td/div/span[contains(@class, "bo_sub")]')
            dtime = list_item.xpath('./td[@class="datetime"]')
            item = {
                "title": subject.text_content().strip(),
                "link": subject.get("href").split("?")[1],
                "subtitle": subtitle[0].text_content().strip() if subtitle else "",
                "datetime": dtime[0].text_content().strip() if dtime else "",
            }
            if f"b_id={b_id}" in item["link"]:
                items.append(item)
        return items

    def tf_view(self, url):
        res = self.session.get(url)
        doc = html.fromstring(res.content)

        title_proper = doc.xpath('//div[@class="view_title"]')[0].text_content()
        title_proper = ("]".join(title_proper.split("]")[1:])).strip()

        published_at = doc.xpath('//tr/td[@class="view_t3"]')[0].text_content()
        published_at = ":".join(published_at.split(":")[1:]).strip()
        published_at = datetime.strptime(published_at, "%Y-%m-%d %H:%M:%S")

        # list up items
        items = []
        for html_item in doc.xpath('//tr/td[@class="view_t4"]'):
            item = {}
            if html_item.xpath('./a[contains(text(), ".torrent")]'):
                item["type"] = "torrent"
                item["filename"] = html_item.xpath("./a")[0].text_content().strip()
                item["url"] = html_item.xpath("./a")[0].get("href")
            elif html_item.xpath(
                './a[contains(text(), ".smi") or contains(text(), ".srt") or contains(text(), ".ass")]'
            ):
                item["type"] = "subtitle"
                item["filename"] = html_item.xpath("./a")[0].text_content().strip()
                item["url"] = html_item.xpath("./a")[0].get("href")
            elif html_item.xpath("./a"):
                item["type"] = "etc"
                item["filename"] = html_item.xpath("./a")[0].text_content().strip()
                item["url"] = html_item.xpath("./a")[0].get("href")
            else:
                continue
            items.append(item)
        logger.debug(f"Found {len(items):d} items")

        return {
            "page_url": url,
            "title_proper": title_proper,
            "published_at": published_at,
            "items": items,
        }

    def tf_down(self, query_string, item_no=0):
        src_url = ModelSetting.get("site_url").rstrip("/") + "/board.php?" + query_string

        view = self.tf_view(src_url)

        self.session.headers.update({"Referer": src_url})

        down_url = view["items"][item_no]["url"]
        filename = str(view["items"][item_no]["filename"])

        if "download.php" in down_url:
            fcontent = self.session.get(down_url).content
        else:
            fcontent = self.download_filetender(down_url, filename)

        # try:
        #     import libtorrent
        #     torrent_dict = libtorrent.bdecode(fcontent)
        #     torrent_info = libtorrent.torrent_info(torrent_dict)
        #     torrent_name = torrent_info.name()
        #     resp.headers['Content-Type'] = 'application/x-bittorrent'

        #     # 가끔 본문의 파일명에 &가 scrub 되는 경우가 있다.
        #     torrent_name_scrub = torrent_name.replace('& ', '').replace(' &', '').replace('&', ' ')
        #     filename_scrub = filename.replace('.torrent', '')
        #     chklen = int(min(len(torrent_name_scrub), len(filename_scrub))*0.4)
        #     if torrent_name_scrub[:chklen] != filename_scrub[:chklen]:
        #         # 여기서 raise Error 해주지 않으면 잘못된 torrent가 filetender로부터 유입돼도 OK됨
        #         raise ValueError('torrent filename %s is different from expected %s' % (torrent_name_scrub, filename))
        #         # filename = torrent_name + '.torrent'
        # except Exception as e:
        #     logger.error('Exception: %s', str(e))
        #     logger.error(traceback.format_exc())

        return fcontent, filename

    def download_filetender(self, ftender_short, filename):
        """download files from filetender
        :param ftender_short: http://www.filetender.com/UIj7z
        :param filename: Recoil.2011.1080p.BluRay.H264.AAC-RARBG.torrent
        :param referer: http://www.tfreeca22.com/board.php?mode=view&b_id=tmovie&id=359715&page=1
        :return:
        """
        resp = self.session.get(ftender_short)
        doc = html.fromstring(resp.content)

        form_method = doc.xpath("//form")[0].get("method")
        input_hidden = doc.xpath('//input[@type="hidden"]')
        params = {x.get("name"): x.get("value") for x in input_hidden}
        # headers = {'Referer': ftender_short, 'User-Agent': ua}

        ftender_hidden = "https://file.filetender.com/Execdownload.php"
        p = re.compile(r"(?:https?:\/\/)file\.filetender\.com\/.+\.php", re.IGNORECASE)
        for scr_element in doc.xpath("//script[not(@scr)]"):
            m = re.search(p, scr_element.text_content())
            if m:
                ftender_hidden = m[0]
                break

        if form_method.lower() == "post":
            res = self.session.post(ftender_hidden, data=params)
        else:
            res = self.session.get(ftender_hidden, params=params)
        res.raise_for_status()

        if "Content-Disposition" in res.headers:
            fname_from_header = re.findall('filename="(.+)"', res.headers["Content-Disposition"])[0]
            fname_from_header = unquote(fname_from_header)
            # 가끔 본문의 파일명에 &가 scrub 되는 경우가 있다.
            fname_from_header = fname_from_header.replace("& ", "").replace(" &", "").replace("&", " ")
            if filename.replace(" ", "") != fname_from_header.replace(" ", ""):
                raise ValueError(f"Filename mismatch: {filename} != {fname_from_header}")
        return res.content
