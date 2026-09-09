# -*- coding: utf-8 -*-
"""弹幕分析页面视图（A4）。"""
import json

from django.conf import settings
from django.shortcuts import redirect, render


def _mmss(sec):
    """秒 -> mm:ss（如 75 -> 01:15）"""
    sec = int(sec or 0)
    return f"{sec // 60:02d}:{sec % 60:02d}"


def _segments_for_template(data):
    """把 hot_segments_v2 和 sentiment.by_segment 合并成模板好用的列表：
    补上情绪标签、时间字符串、佐证弹幕颜色十六进制。"""
    seg_list = data.get("hot_segments_v2", [])
    by_seg = (data.get("sentiment") or {}).get("by_segment", [])
    label_cls = {"正面": "pos", "负面": "neg", "中性": "neu"}
    result = []
    for i, s in enumerate(seg_list):
        sb = by_seg[i] if i < len(by_seg) else {}
        label = sb.get("label") or "中性"
        result.append({
            **s,
            "label": label,
            "label_class": label_cls.get(label, "neu"),
            "time_str": f"{_mmss(s['start'])} - {_mmss(s['end'])}",
            "peak_str": _mmss(s.get("peak_sec", 0)),
            "evidence": [{
                **e,
                "color_hex": f"{int(e.get('color', 0)) & 0xFFFFFF:06X}",
            } for e in s.get("evidence", [])],
        })
    return result


def danmaku_index(request):
    """输入页：拿到 bvid 就跳去分析页"""
    bvid = request.GET.get("bvid", "").strip()     # 取 URL 参数，去掉首尾空格
    if bvid:
        return redirect(f"/danmaku/analyze/?bvid={bvid}")
    return render(request, "danmaku/index.html")


def danmaku_analyze(request):
    """分析结果页：没有数据就现场爬取+分析，失败给友好错误页"""
    bvid = request.GET.get("bvid", "").strip()
    if not bvid:
        return redirect("/danmaku/")

    path = settings.DATA_ROOT / "out" / "danmaku" / f"{bvid}.json"
    if not path.exists():
        # 没分析过 -> 现场爬取入库 + 分析（首次较慢，页面会转一会儿）
        from apps.analytics.analysis.danmaku import analyze_danmaku
        from apps.fetcher.bili_api import BiliApiError
        from apps.fetcher.danmaku import fetch_and_save
        try:
            fetch_and_save(bvid)
            analyze_danmaku(bvid)
        except BiliApiError as e:
            return render(request, "danmaku/error.html",
                          {"bvid": bvid, "message": f"B站接口出错了：{e}"}, status=502)
        except ValueError as e:
            return render(request, "danmaku/error.html",
                          {"bvid": bvid, "message": str(e)}, status=404)
        except Exception as e:
            return render(request, "danmaku/error.html",
                          {"bvid": bvid, "message": f"分析失败：{e}"}, status=500)

    # 读 JSON，连同字符串一起传给模板
    data = json.loads(path.read_text(encoding="utf-8"))

    # 视频元信息（标题/UP主/分区），查不到就只显示 BV 号
    from apps.analytics.models import DanmakuVideo
    video = DanmakuVideo.objects.filter(bvid=bvid).first()
    meta = {
        "title": video.title if video else bvid,
        "up_name": video.up_name if video else "",
        "tname": video.tname if video else "",
        "duration": video.duration if video else data.get("duration_sec", 0),
    }

    return render(request, "danmaku/analyze.html", {
        "data": data,
        "meta": meta,
        "segments": _segments_for_template(data),   # 高能片段+情绪标签（模板用）
        "data_json": json.dumps(data, ensure_ascii=False),   # 图表用
    })
