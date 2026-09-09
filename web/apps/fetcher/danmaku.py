# -*- coding: utf-8 -*-
"""B站弹幕爬取核心：seg.so protobuf 解析 + 全量分页抓取。

TODO：
1. 把 web/spider_dm.py 里的 protobuf 解析（parse_fields / parse_dm_elem）迁移到本模块；
2. 实现 fetch_danmaku_all(cid)：循环 segment_index 分段 + ps/pe 页内分页取全量；
3. 弹幕字段：id(1) progress_ms(2) mode(3) fontsize(4) color(5) mid_hash(6)
   content(7) ctime(8) weight(9) action(10) pool(11) id_str(12) attr(13)；
4. 风控退避复用 apps.fetcher.bili_api.BiliApi._get；WBI 签名见 wbi.py。
"""
# -*- coding: utf-8 -*-
"""Bilibili 弹幕 seg.so 接口爬虫（protobuf 解析版）"""
import requests
import struct


def read_varint(buf, pos):
    """从 pos 开始读一个 varint，返回 (数值, 新位置)"""
    result = 0
    shift = 0
    while True:
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift   # 取低7位，按位拼上去
        if not (b & 0x80):              # 最高位=0 说明这是最后一个字节
            return result, pos
        shift += 7                      # 每字节贡献 7 位


def parse_fields(buf):
    """把一段 protobuf 消息解析成 {字段号: [(wire_type, 值), ...]}"""
    fields = {}
    pos = 0
    while pos < len(buf):
        key, pos = read_varint(buf, pos)
        field_no, wire_type = key >> 3, key & 0x07    # 拆出字段号和类型
        if wire_type == 0:                             # varint
            value, pos = read_varint(buf, pos)
        elif wire_type == 1:                           # 64位定长
            value = buf[pos:pos + 8]; pos += 8
        elif wire_type == 2:                           # 长度前缀（字符串/嵌套消息）
            length, pos = read_varint(buf, pos)
            value = buf[pos:pos + length]; pos += length
        elif wire_type == 5:                           # 32位定长
            value = struct.unpack("<I", buf[pos:pos + 4])[0]; pos += 4
        else:
            raise ValueError(f"unsupported wire_type={wire_type}")
        fields.setdefault(field_no, []).append((wire_type, value))
    return fields

def _decode(v):
    """字符串字段是 bytes，转成可读文本"""
    if isinstance(v, bytes):
        try:
            return v.decode("utf-8")
        except UnicodeDecodeError:
            return v.hex()
    return v


def parse_dm_elem(raw):
    """把一条弹幕的嵌套消息字节，映射成易懂的 dict"""
    f = parse_fields(raw)
    def first(num):
        vals = f.get(num)
        return vals[0][1] if vals else None
    return {
        "dmid": first(1),            # 弹幕ID（去重用）
        "progress_ms": first(2),     # 在视频中的位置（毫秒）
        "mode": first(3),            # 1滚动 4底部 5顶部
        "fontsize": first(4),
        "color": first(5),           # RGB 整数，如 16777215=白色
        "mid_hash": _decode(first(6)),  # 用户ID哈希
        "content": _decode(first(7)),   # ★ 弹幕文本
        "ctime": first(8),           # 发送时间戳
        "weight": first(9),
    }

SEG_API = "https://api.bilibili.com/x/v2/dm/web/seg.so"   # 老接口，免签名
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
}
def fetch_danmaku_all(cid, max_segments=20):
   session=requests.session()
   session.headers.update(HEADERS)

   results = []
   for segment_index in range(1, max_segments + 1):
      resp = session.get(SEG_API,params={
         "type":1,
         "oid":cid,
         "segment_index":segment_index,
         "ps":0,
         "pe":120000,
      })        # 1. 请求 SEG_API，参数 type/oid/segment_index/ps/pe
      if resp.status_code!=200:           # 2. 非 200 怎么办？
         break
      top = parse_fields(resp.content)         # 3. 用什么函数解析 resp.content？
      elems = [v for wt,v in top.get(1,[]) if wt==2]      # 4. 怎么从 top 里取字段1、且只要 wire_type==2 的值？
      results.extend(parse_dm_elem(e) for e in elems)  # 5. 每条弹幕字节怎么转成 dict？
      has_next=[v for wt ,v in top.get(2,[]) if wt==0]
      if  has_next and has_next[0]==0: 
         break
      # 6. 怎么判断该 break？（提示：字段2 has_next）
   return results

def fetch_and_save(bvid, api=None):
    """爬取一个视频的全量弹幕并入库（管理命令和页面共用）。

    返回 (video, created, dms)；
    无弹幕抛 ValueError；B站接口失败抛 BiliApiError。
    """
    from django.utils import timezone

    from apps.analytics.models import DanmakuRecord, DanmakuVideo
    from apps.fetcher.bili_api import BiliApi, BiliApiError

    api = api or BiliApi()
    info = api.video_view(bvid)          # 可能抛 BiliApiError（无效BV/风控/接口挂了）
    cid = info["cid"]
    owner = info.get("owner") or {}

    dms = fetch_danmaku_all(cid)
    if not dms:
        raise ValueError(f"视频 {bvid} 没有爬到弹幕（可能已删除或无弹幕）")

    # 按 dmid 去重：B站分段接口在段边界可能重复返回同一条弹幕，
    # 不去重的话 danmaku_count 和实际入库条数会对不上
    seen, uniq = set(), []
    for d in dms:
        dmid = d.get("dmid")
        if dmid in seen:
            continue
        seen.add(dmid)
        uniq.append(d)
    dms = uniq
    if not dms:
        raise ValueError(f"视频 {bvid} 去重后没有弹幕")

    video, created = DanmakuVideo.objects.update_or_create(
        bvid=bvid,
        defaults={
            "cid": cid,
            "title": info.get("title", ""),
            "up_mid": owner.get("mid", 0),
            "up_name": owner.get("name", ""),
            "tname": info.get("tname_v2") or info.get("tname") or "",
            "duration": info.get("duration", 0),
            "danmaku_count": len(dms),
            "source": "manual",
            "fetch_status": "success",
            "fetched_at": timezone.now(),
        },
    )
    DanmakuRecord.objects.bulk_create([
        DanmakuRecord(
            video=video, bvid=bvid, cid=cid,
            dmid=d["dmid"], progress_ms=d["progress_ms"], mode=d["mode"],
            fontsize=d["fontsize"], color=d["color"], mid_hash=d["mid_hash"],
            content=d["content"], ctime=d["ctime"], weight=d["weight"],
            source="manual",
        )
        for d in dms
    ], ignore_conflicts=True)
    return video, created, dms
