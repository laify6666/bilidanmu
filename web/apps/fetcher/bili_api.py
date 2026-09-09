"""B 站 Web API 封装（自维护，不依赖已关停的第三方库）。

重要：非官方接口存在合规与风控风险，仅限本人账号、限速、不公开分发。
接口可能随时变更，所有请求集中在类内便于维护。
"""
import random
import time

import requests


class BiliApiError(Exception):
    pass


class BiliApi:
    """B 站 Web API 客户端。"""

    UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
    BASE = "https://api.bilibili.com"

    def __init__(self, sessdata: str = "", bili_jct: str = "", min_interval: float = 0.3):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.UA, "Referer": "https://www.bilibili.com/"})
        if sessdata:
            self.session.cookies.set("SESSDATA", sessdata, domain=".bilibili.com")
        if bili_jct:
            self.session.cookies.set("bili_jct", bili_jct, domain=".bilibili.com")
        self.min_interval = min_interval   # 限速：两次请求最小间隔
        self._last = 0.0
        self._cache = {}  # 请求缓存去重（view/tags）

    def _get(self, url: str, params=None) -> dict:
        # 随机抖动：请求间隔不规律，降低被风控识别的概率
        elapsed = time.time() - self._last
        wait = max(0.0, self.min_interval - elapsed) + random.uniform(0, 0.2)
        if wait > 0:
            time.sleep(wait)
        self._last = time.time()
        last_exc = None
        for attempt in range(3):
            resp = self.session.get(url, params=params, timeout=15)
            data = resp.json()
            code = data.get("code")
            if code == 0:
                return data.get("data") or {}
            if code in (-101, -401, 62002):  # 登录失效 / 稿件不可见：直接失败，不重试
                raise BiliApiError(f"B站接口错误 code={code} msg={data.get('message')}")
            if code in (-352, -400):         # 风控 / 请求被限：冷却后重试（10/20/30 秒），平时不降速
                last_exc = BiliApiError(f"风控 code=-352 msg={data.get('message')}")
                time.sleep(10 * (attempt + 1))
                continue
            last_exc = BiliApiError(f"B站接口错误 code={code} msg={data.get('message')}")
            time.sleep(2 * (attempt + 1))
        raise last_exc or BiliApiError("B站接口重试后仍失败")

    # ---------- 扫码登录 ----------
    @staticmethod
    def qrcode_generate() -> dict:
        """生成登录二维码，返回 {url, qrcode_key}"""
        resp = requests.get(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
            headers={"User-Agent": BiliApi.UA}, timeout=15,
        )
        return resp.json().get("data", {})

    @staticmethod
    def qrcode_poll(qrcode_key: str):
        """轮询扫码状态。

        返回 (json, cookies)。json.data 语义：
          code=0 且 data.url 存在 = 登录成功（cookies 里含 SESSDATA/bili_jct）
          code=0  未扫码；86090 已扫未确认；86038 二维码已过期
        """
        session = requests.Session()
        session.headers.update({"User-Agent": BiliApi.UA, "Referer": "https://www.bilibili.com/"})
        # 注意：B 站该接口当前只接受 GET（POST 会返回 Method Not Allowed）
        resp = session.get(
            "https://passport.bilibili.com/x/passport-login/web/qrcode/poll",
            params={"qrcode_key": qrcode_key}, timeout=15,
        )
        return resp.json(), dict(resp.cookies)

    # ---------- 历史记录 ----------
    def history_cursor(self, max_id: int = 0, view_at: int = 0, ps: int = 20) -> dict:
        """获取一页观看历史。

        分页必须同时传 max 和 view_at（cursor 返回的 view_at），否则会重复返回同一页。
        返回 {list: [...], cursor: {max: ..., view_at: ...}}。
        """
        params = {"max": max_id, "ps": ps}
        if view_at:
            params["view_at"] = view_at
        return self._get(f"{self.BASE}/x/web-interface/history/cursor", params=params)



    # ---------- 视频详情 / 标签 ----------
    def video_view(self, bvid: str) -> dict:
        """视频详情（含 tname 分区、owner、stat 等），带内存缓存去重"""
        key = f"view:{bvid}"
        if key in self._cache:
            return self._cache[key]
        data = self._get(f"{self.BASE}/x/web-interface/view", params={"bvid": bvid})
        self._cache[key] = data
        return data

    def video_tags(self, bvid: str) -> list:
        """视频标签列表，返回 [{tag_id, tag_name, ...}, ...]"""
        key = f"tags:{bvid}"
        if key in self._cache:
            return self._cache[key]
        data = self._get(f"{self.BASE}/x/tag/archive/tags", params={"bvid": bvid})
        self._cache[key] = data
        return data

    # ---------- 候选池：热门榜 / 分区榜 ----------
    def popular_list(self, ps: int = 20, pn: int = 1) -> list:
        """热门视频列表。返回 [{bvid,title,owner,stat,tname,...}, ...]"""
        data = self._get(f"{self.BASE}/x/web-interface/popular", params={"ps": ps, "pn": pn})
        return data.get("list") or []

    def partition_rank(self, rid: int) -> list:
        """分区排行榜。rid: 0=全站 1=动画 4=游戏 36=知识 188=科技 160=生活 5=娱乐 3=音乐 129=舞蹈 119=鬼畜 155=时尚 181=影视 17=单机 234=运动 211=美食 95=数码"""
        data = self._get(f"{self.BASE}/x/web-interface/ranking/v2",
                         params={"rid": rid, "type": "all"})
        return data.get("list") or []





