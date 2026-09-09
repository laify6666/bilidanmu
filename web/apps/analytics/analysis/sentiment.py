# -*- coding: utf-8 -*-
"""弹幕情感分析：种子词典打分 + 情感传播扩展（A2）。

流程：
  1. score_danmaku(content)   单条弹幕打分：词根包含匹配 + 否定翻转 + 程度加权
  2. sentiment_analyze(...)   汇总四个视图：
       overall            正/负/中总体占比
       timeline           按时间轴的情绪曲线（叠加在高能片段上）
       by_segment         每个高能片段的情绪标签（正面爆点还是负面吐槽）
       reaction_sentiment 每个反应词的情绪

反应词情绪 = 两层判定（这是 A2 自动扩展词表的核心）：
  ① 字面信号：反应词自己命中词典就直接判（"苦的"含"苦" -> 负面，可解释、准）
  ② 传播信号：词典判不了（"空瓶""三嫂"），看它出现时刻周围
     其他【有情感】弹幕的正/负投票（种子词典当老师，同刻弹幕当课堂）。

注意：统计均值时只算"有情感的弹幕"（score != 0），
否则会被大量中性弹幕稀释成接近 0，失去区分度。
"""
from .emotion_dict import POSITIVE, NEGATIVE, NEGATORS, INTENSIFIERS

# 平均分超过该阈值判正面 / 低于负阈值判负面，中间算中性
POS_THRESHOLD = 0.2


def score_danmaku(content, positive=None, negative=None, negators=None, intensifiers=None):
    """给一条弹幕打分：负数负面、正数正面、0 中性。

    规则三步：
      ① 词根包含匹配：命中正面词加分、负面词减分（无命中直接 0）
      ② 程度副词加权：命中"太/超/真"等增强（>=1 取最强），
         "有点/稍微"等减弱（<1 取最弱）
      ③ 否定翻转：命中"不/没/不是"等，极性取反（"不苦" -> 正面）
    """
    positive = positive if positive is not None else POSITIVE
    negative = negative if negative is not None else NEGATIVE
    negators = negators if negators is not None else NEGATORS
    intensifiers = intensifiers if intensifiers is not None else INTENSIFIERS

    score = 0.0
    for word, val in positive.items():
        if word in content:
            score += val
    for word, val in negative.items():
        if word in content:
            score -= val
    if score == 0:
        return 0.0

    # ② 程度加权
    weight = 1.0
    for word, val in intensifiers.items():
        if word in content:
            # 增强副词(>=1)取最强，减弱副词(<1)取最弱
            weight = max(weight, val) if val >= 1 else min(weight, val)
    score *= weight

    # ③ 否定翻转（按长度降序匹配，避免"不是"被"不"先抢到）
    neg_found = any(word in content for word in sorted(negators, key=len, reverse=True))
    if neg_found:
        score = -score
    return round(score, 2)


def _label(avg):
    """平均分 -> 情绪标签"""
    if avg > POS_THRESHOLD:
        return "正面"
    if avg < -POS_THRESHOLD:
        return "负面"
    return "中性"


def _overall(scored):
    """总体占比：正/负/中计数，正负比只看有情绪的弹幕"""
    pos = sum(1 for _, sc, _ in scored if sc > 0)
    neg = sum(1 for _, sc, _ in scored if sc < 0)
    neu = len(scored) - pos - neg
    total = pos + neg
    return {
        "positive": pos,
        "negative": neg,
        "neutral": neu,
        "pos_ratio": round(pos / total, 2) if total else 0,
        "label": "正面为主" if pos > neg else ("负面为主" if neg > pos else "正负均衡"),
    }


def _timeline(scored, window_sec):
    """时间轴情绪曲线：每窗口的"有情绪弹幕"平均分 + 正/负条数。
    有情绪弹幕 < 3 条时均值不稳，score 置 None（页面不画点）。
    """
    buckets = {}
    for sec, sc, _ in scored:
        buckets.setdefault(sec // window_sec, []).append(sc)
    max_bucket = max(buckets) if buckets else 0

    labels, score, positive, negative = [], [], [], []
    for i in range(max_bucket + 1):
        vals = buckets.get(i, [])
        sent = [v for v in vals if v != 0]      # 只取有情感的
        labels.append(f"{i * window_sec}-{(i + 1) * window_sec}s")
        positive.append(sum(1 for v in vals if v > 0))
        negative.append(sum(1 for v in vals if v < 0))
        if len(sent) >= 3:
            score.append(round(sum(sent) / len(sent), 2))
        else:
            score.append(None)
    return {"labels": labels, "score": score, "positive": positive, "negative": negative}


def _segment_sentiment(scored, seg, window_sec):
    """一个高能片段的情绪：正/负/中计数 + 有情绪弹幕的平均分 + 标签"""
    vals = [sc for sec, sc, _ in scored if seg["start"] <= sec < seg["end"]]
    sent = [v for v in vals if v != 0]
    n = len(vals)
    score = round(sum(sent) / len(sent), 2) if len(sent) >= 3 else None
    return {
        "start": seg["start"],
        "end": seg["end"],
        "peak_sec": seg.get("peak_sec"),
        "count": n,
        "positive": sum(1 for v in vals if v > 0),
        "negative": sum(1 for v in vals if v < 0),
        "neutral": n - sum(1 for v in vals if v != 0),
        "score": score,
        "label": _label(score) if score is not None else "中性",
    }


def _reaction_sentiment(scored, reaction_word, window_sec):
    """给一个反应词定情绪：①字面信号优先 ②传播信号兜底。"""
    word = reaction_word["word"]
    radius = window_sec // 2

    occur_times = []      # 含该词的弹幕时间点
    ctx = []              # 不含该词且【有情感】的弹幕 (sec, score)
    for sec, sc, content in scored:
        if word in content:
            occur_times.append(sec)
        elif sc != 0:
            ctx.append((sec, sc))

    # ① 字面信号：词本身命中词典（"苦的"含"苦"）
    literal = score_danmaku(word)
    if literal != 0:
        return {
            "word": word,
            "count": reaction_word["count"],
            "method": "词典",
            "literal_score": literal,
            "score": literal,
            "label": _label(literal),
        }

    # ② 传播信号：词典判不了，看它出现时刻周围有情感弹幕的正/负投票
    votes = [sc for sec, sc in ctx if any(abs(sec - t) <= radius for t in occur_times)]
    pos = sum(1 for v in votes if v > 0)
    neg = sum(1 for v in votes if v < 0)
    n = len(votes)
    # 多数人情绪才代表这个词：正面占比 >= 60% 判正面，<= 40% 判负面
    if n >= 3:
        ratio = pos / (pos + neg)
        label = "正面" if ratio >= 0.6 else ("负面" if ratio <= 0.4 else "中性")
    else:
        label = "中性"
    avg = sum(votes) / n if n else 0.0
    return {
        "word": word,
        "count": reaction_word["count"],
        "method": "传播",
        "positive_votes": pos,
        "negative_votes": neg,
        "context_samples": n,
        "score": round(avg, 2) if n else None,
        "label": label,
    }


def sentiment_analyze(records, window_sec=30, segments=None, reaction_words=None):
    """汇总弹幕情感。

    records         A1 的轻量 dict 列表（progress_ms / content）
    window_sec      时间轴窗口（与 A1 自适应窗口保持一致）
    segments        A1 hot_segments_v2 的结果（给每个高潮打情绪标签）
    reaction_words  A1 auto_reaction_words 的结果（给反应词定情绪）
    """
    scored = []
    for r in records:
        sec = int((r.get("progress_ms") or 0) / 1000)
        content = (r.get("content") or "").strip()
        if content:
            scored.append((sec, score_danmaku(content), content))

    return {
        "overall": _overall(scored),
        "timeline": _timeline(scored, window_sec),
        "by_segment": [_segment_sentiment(scored, s, window_sec) for s in (segments or [])],
        "reaction_sentiment": [_reaction_sentiment(scored, w, window_sec)
                               for w in (reaction_words or [])],
    }
