# -*- coding: utf-8 -*-
"""弹幕分析模块（纯 Python -> JSON）。

功能一览：
- timeline_density          时间密度（固定 10s 桶，供图表）
- hot_segments              旧版高能片段（保留，用于 A/B 对比）
- hot_segments_v2           升级版高能片段
    · 自适应窗口：按视频时长选 15/30/60s 滑窗
    · z-score 判定：z >= z_thresh 才算高能桶（替代固定 threshold）
    · 重叠容差：相距很近的片段自动合并
    · 佐证弹幕：每个片段附 3~5 条代表弹幕（观众在那一刻刷了什么）
- auto_reaction_words       自动发现"反应词"（短 + 高频 + 时间扎堆）
- top_danmaku / mode_dist / active_hours
- analyze_danmaku           汇总全部指标 -> data/out/danmaku/{bvid}.json
"""
import statistics
from datetime import datetime
from collections import Counter
from .sentiment import sentiment_analyze
from .keywords import extract_keywords, keywords_by_segment


def _load_records(bvid):
    """从数据库读一个视频的弹幕，转成轻量 dict 列表"""
    from apps.analytics.models import DanmakuRecord

    return [
        {
            "progress_ms": r.progress_ms,   # 视频内位置(毫秒)
            "mode": r.mode,
            "color": r.color,
            "content": r.content,
            "ctime": r.ctime,
            "mid_hash": r.mid_hash,
        }
        for r in DanmakuRecord.objects.filter(bvid=bvid)
    ]


BUCKET_SEC = 10


def timeline_density(records, bucket_sec=BUCKET_SEC):
    """弹幕时间密度：按固定时间桶聚合，返回 {labels, values}"""
    counter = Counter()
    for r in records:
        sec = int((r.get("progress_ms") or 0) / 1000)
        bucket = sec // bucket_sec
        counter[bucket] += 1

    # 生成完整序列（中间可能有没有弹幕的空桶，必须补 0）
    max_bucket = max(counter) if counter else 0
    labels = [f"{i * bucket_sec}-{(i + 1) * bucket_sec}s" for i in range(max_bucket + 1)]
    values = [counter.get(i, 0) for i in range(max_bucket + 1)]

    return {"labels": labels, "values": values}


def hot_segments(values, bucket_sec=BUCKET_SEC, top_k=3):
    """[旧版] 从时间密度里提取高能片段：超过阈值的连续桶合并成一个片段"""
    if not values:
        return []

    mean = sum(values) / len(values)
    std = statistics.pstdev(values) if len(values) > 1 else 0
    threshold = mean + std                     # ★ 自适应阈值

    # 1) 找出"热桶"（超过阈值的桶）
    hot = [i for i, v in enumerate(values) if v > threshold]

    # 2) 把相邻的桶合并成一个片段
    segments = []
    for i in hot:
        if segments and i == segments[-1]["end_bucket"] + 1:
            segments[-1]["end_bucket"] = i
            segments[-1]["count"] += values[i]
        else:
            segments.append({"start_bucket": i, "end_bucket": i, "count": values[i]})

    # 3) 转成秒、按弹幕数排序、取前 top_k
    result = [
        {"start": s["start_bucket"] * bucket_sec,
         "end": (s["end_bucket"] + 1) * bucket_sec,
         "count": s["count"]}
        for s in segments
    ]
    result.sort(key=lambda x: x["count"], reverse=True)
    return result[:top_k]


# ================= 升级版高能片段 hot_segments_v2 =================

def adaptive_window(duration_sec):
    """按视频时长自适应滑窗大小（秒）。

    短视频(<5min)弹幕本来就不多，窗口太大会把高潮"摊平" -> 用 15s；
    半小时内的用 30s；更长用 60s，否则单桶弹幕太少、全是噪声。
    """
    if duration_sec < 300:
        return 15
    if duration_sec <= 1800:
        return 30
    return 60


def _bucketize(records, window_sec):
    """按 window_sec 滑窗聚合弹幕，缺桶补 0，返回 [{start,end,count}, ...]"""
    counter = Counter()
    for r in records:
        sec = int((r.get("progress_ms") or 0) / 1000)
        counter[sec // window_sec] += 1
    max_bucket = max(counter) if counter else 0
    return [
        {"start": i * window_sec, "end": (i + 1) * window_sec, "count": counter.get(i, 0)}
        for i in range(max_bucket + 1)
    ]


def _z_hot_buckets(buckets, z_thresh=2.0, min_density=None):
    """z-score 判定高能桶。

    论文方法：对密度序列算 z = (count - mean) / std，
    只有明显高于平均的桶才算"高潮"，比固定 threshold 更能适应不同热度的视频。
    min_density 是绝对下限，防止 std 很小（弹幕均匀）时误报。
    """
    counts = [b["count"] for b in buckets]
    mean = sum(counts) / len(counts) if counts else 0
    std = statistics.pstdev(counts) if len(counts) > 1 else 0
    if min_density is None:
        min_density = max(2, round(mean))
    hot = []
    for b in buckets:
        z = (b["count"] - mean) / std if std > 0 else 0.0
        if z >= z_thresh and b["count"] >= min_density:
            hot.append(b)
    return hot, mean, std


def _segment_evidence(records, start_sec, end_sec, n=5):
    """一个片段内的"佐证弹幕"：按内容去重计数，取出现最多的前 n 条。

    返回每条弹幕：内容、次数、颜色、模式、第一次出现秒数（页面可直接展示）。
    """
    counter = Counter()
    first_seen = {}
    sample = {}
    for r in records:
        sec = int((r.get("progress_ms") or 0) / 1000)
        if start_sec <= sec < end_sec:
            content = (r.get("content") or "").strip()
            if not content:
                continue
            counter[content] += 1
            first_seen.setdefault(content, sec)
            sample.setdefault(content, r)   # 保留第一条的颜色/模式
    return [
        {
            "content": text,
            "count": cnt,
            "color": sample[text].get("color", 0),
            "mode": sample[text].get("mode", 1),
            "first_seen_sec": first_seen[text],
        }
        for text, cnt in counter.most_common(n)
    ]


def hot_segments_v2(records, duration_sec=None, z_thresh=2.0, min_density=None,
                    top_k=3, merge_gap_sec=None, evidence_n=5):
    """升级版高能片段：自适应窗口 + z-score + 重叠容差 + 佐证弹幕。

    流程：
      1. 自适应窗口：duration_sec -> 15/30/60s
      2. 按窗口聚合密度，z-score 找出高能桶
      3. 连续高能桶合成段；段间相距 <= merge_gap_sec 自动合并
         （"重叠容差"：两个挨得很近的爆发算同一个高潮，
          默认 = 半个窗口，比如 30s 窗口下 15s 内的两个爆发会合并）
      4. 每段补 peak_sec（密度最高的秒）+ 佐证弹幕
    """
    if not records:
        return []
    if duration_sec is None:
        duration_sec = max((r.get("progress_ms") or 0) for r in records) // 1000
    window_sec = adaptive_window(duration_sec)
    if merge_gap_sec is None:
        merge_gap_sec = window_sec // 2        # 默认容忍半个窗口的间隔

    buckets = _bucketize(records, window_sec)
    hot, mean, std = _z_hot_buckets(buckets, z_thresh, min_density)

    # 连续热桶 -> 桶级段
    runs = []
    for b in hot:
        if runs and b["start"] == runs[-1]["end"]:
            runs[-1]["end"] = b["end"]
            runs[-1]["count"] += b["count"]
        else:
            runs.append({"start": b["start"], "end": b["end"], "count": b["count"]})

    # 段间相距 <= merge_gap_sec 就合并（重叠容差）
    merged = []
    for s in runs:
        if merged and s["start"] - merged[-1]["end"] <= merge_gap_sec:
            merged[-1]["end"] = s["end"]
            merged[-1]["count"] += s["count"]
        else:
            merged.append(dict(s))

    # 峰值秒 + 佐证弹幕
    result = []
    for s in merged:
        in_seg = [b for b in hot if b["start"] < s["end"] and b["end"] > s["start"]]
        peak_bucket = max(in_seg, key=lambda b: b["count"]) if in_seg else s
        peak_sec = (peak_bucket["start"] + peak_bucket["end"]) // 2
        result.append({
            "start": s["start"],
            "end": s["end"],
            "peak_sec": peak_sec,
            "count": s["count"],
            "evidence": _segment_evidence(records, s["start"], s["end"], evidence_n),
        })

    result.sort(key=lambda x: x["count"], reverse=True)
    return result[:top_k]


# ================= 自动发现反应词 =================

def _max_count_in_window(times, window_sec):
    """有序时间序列里，任意 window_sec 窗口内最多出现多少次（双指针滑窗）。"""
    left = 0
    best = 0
    for right in range(len(times)):
        while times[right] - times[left] > window_sec:
            left += 1
        best = max(best, right - left + 1)
    return best


def auto_reaction_words(records, max_len=6, min_freq=3, window_sec=None,
                        duration_sec=None, min_burst=3.0, top_n=20):
    """自动发现"反应词"：短词(<=6字) + 出现>=3次 + 时间上明显扎堆。

    反应词 = 观众在某个瞬间集体刷的短句（如 "666" "苦的" "空瓶"）。
    扎堆程度 burstiness 用"密度比"衡量：
      burstiness = (峰值窗口内条数 / 窗口秒数) / (总条数 / 全片时长)
                 = 峰值窗口的密度 ÷ 全片平均密度
    比值越大说明越集中在某个瞬间刷；另要求峰值窗口内至少 2 条，
    避免"几次全分散"的低频词被误判。
    """
    # 1) 候选词 + 每次出现的时间
    times = {}                       # content -> [出现秒数, ...]
    for r in records:
        content = (r.get("content") or "").strip()
        if not content or len(content) > max_len:
            continue
        # 过滤纯标点（如 "？？？"）：要求至少含一个汉字/字母/数字
        if not any(ch.isalnum() or '\u4e00' <= ch <= '\u9fff' for ch in content):
            continue
        sec = int((r.get("progress_ms") or 0) / 1000)
        times.setdefault(content, []).append(sec)

    if not times:
        return []

    # 2) 全片时长：没传就用最后一条弹幕的时间（约等于视频长度）
    if duration_sec is None:
        duration_sec = max(max(v) for v in times.values())

    # 3) 没有指定窗口时按视频时长自适应（15/30/60s）
    if window_sec is None:
        window_sec = adaptive_window(max(duration_sec, 1))

    # 4) 频率 + 扎堆度筛选
    results = []
    for word, secs in times.items():
        if len(secs) < min_freq:
            continue
        secs.sort()
        n = len(secs)
        peak_in_window = _max_count_in_window(secs, window_sec)
        if peak_in_window < 2:                       # 峰值窗口内至少 2 条
            continue
        avg_rate = n / max(duration_sec, window_sec) # 全片平均密度
        burst = (peak_in_window / window_sec) / avg_rate
        if burst < min_burst:
            continue
        results.append({
            "word": word,
            "count": n,
            "burstiness": round(burst, 2),
            "peak_in_window": peak_in_window,
            "span_sec": secs[-1] - secs[0],          # 第一次到最后一次的时间跨度
        })

    results.sort(key=lambda x: (x["count"], x["burstiness"]), reverse=True)
    return results[:top_n]



# ================= 其它指标 =================

def top_danmaku(records, top_n=10):
    """热门弹幕 TopN：相同内容去重后按出现次数排序"""
    counter = Counter()
    for r in records:
        content = (r.get("content") or "").strip()   # 去首尾空格
        if not content:
            continue                                 # 过滤空弹幕
        counter[content] += 1

    return [
        {"content": text, "count": cnt}
        for text, cnt in counter.most_common(top_n)   # ★ 现成方法：按次数降序取前 N
    ]


MODE_NAMES = {1: "滚动弹幕", 4: "底部弹幕", 5: "顶部弹幕"}


def mode_dist(records):
    """弹幕类型分布：mode 数字 -> 名字，返回 [{name, value}]"""
    counter = Counter()
    for r in records:
        mode = r.get("mode") or 1          # 缺省按滚动算
        counter[mode] += 1

    return [
        {"name": MODE_NAMES.get(mode, f"类型{mode}"), "value": cnt}   # 未知类型兜底
        for mode, cnt in counter.most_common()
    ]


def active_hours(records):
    """弹幕发送时间活跃时段：ctime(时间戳) -> 0~23 点分布"""
    hours = [0] * 24                       # 固定 24 个位置
    for r in records:
        ts = r.get("ctime") or 0
        if not ts:
            continue
        hour = datetime.fromtimestamp(ts).hour   # 时间戳 -> 小时
        hours[hour] += 1

    return {"labels": [f"{h}时" for h in range(24)], "values": hours}


def analyze_danmaku(bvid, save_json=True):
    """汇总：读库 -> 算全部指标 -> 写 data/out/danmaku/{bvid}.json，返回结果"""
    import json
    from django.conf import settings

    records = _load_records(bvid)
    if not records:
        raise ValueError(f"没有 {bvid} 的弹幕数据")

    duration_sec = max((r.get("progress_ms") or 0) for r in records) // 1000
    window_sec = adaptive_window(duration_sec)
    density = timeline_density(records)
    unique_users = {r.get("mid_hash") for r in records if r.get("mid_hash")}

    segments_v2 = hot_segments_v2(records, duration_sec=duration_sec)
    reaction_words = auto_reaction_words(records, duration_sec=duration_sec)

    result = {
        "bvid": bvid,
        "total": len(records),
        "duration_sec": duration_sec,
        "window_sec": window_sec,
        "overview": {
            "total": len(records),
            "unique_users": len(unique_users),
            "avg_per_user": round(len(records) / len(unique_users), 2) if unique_users else 0,
            "peak_bucket": density["labels"][density["values"].index(max(density["values"]))],
        },
        "timeline_density": density,
        "hot_segments": hot_segments(density["values"]),                    # 旧版（A/B 对比）
        "hot_segments_v2": segments_v2,
        "reaction_words": reaction_words,
        "sentiment": sentiment_analyze(records, window_sec=window_sec,
                                       segments=segments_v2, reaction_words=reaction_words),
        "keywords": {
            "global": extract_keywords(records),
            "by_segment": keywords_by_segment(records, segments_v2),
        },
        "top_danmaku": top_danmaku(records),
        "mode_dist": mode_dist(records),
        "active_hours": active_hours(records),
    }
    if save_json:
        out_dir = settings.DATA_ROOT / "out" / "danmaku"
        out_dir.mkdir(parents=True, exist_ok=True)              # 没有目录就建
        path = out_dir / f"{bvid}.json"
        path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),   # ★ 中文不转义 + 缩进
            encoding="utf-8",
        )
        print(f"已写入 {path}")

    return result