# -*- coding: utf-8 -*-
"""弹幕关键词分析（A3）：jieba 分词 + 停用词过滤 + 词频统计。

回答"观众在聊什么"：
  - extract_keywords(records)              全局关键词 TopN
  - keywords_by_segment(records, segments) 每个高能片段的关键词
    （segments 来自 A1 的 hot_segments_v2）

与 A1 反应词的分工：
  - 反应词 = 观众刷的短句/梗（666、苦的）
  - 关键词 = 观众聊的主题词（苦、蜥蜴、三嫂）
"""
import logging
import re
from collections import Counter

import jieba

# 抑制 jieba 首次加载时打印的 Building prefix dict 日志
jieba.setLogLevel(logging.WARNING)

# 停用词表：高频虚词 + 语气词 + 代词（这些词没有主题含义）
STOPWORDS = set("""
的 了 吗 啊 吧 呢 呀 嘛 哦 嗯 嘿 哟 哈
我 你 他 她 它 我们 你们 他们 大家 自己
这 那 这个 那个 这些 那些 这里 那里 什么 怎么 为什么 为啥 谁 哪 几 多少
是 在 有 和 与 或 就 都 也 还 又 再 很 太 真 好 不 没 别 一 一个 一下
不是 没有 这么 那么 出来 看见 知道 真的 感觉 觉得 有点 已经 然后 但是 因为 所以
""".split())

# 重复字符的语气词/笑声（哈哈哈 / 啊啊啊 / 嘿嘿嘿）——是情绪不是主题
LAUGH_PAT = re.compile(r"^([哈啊哦嗯嘿嘻哎哟])\1+$")


def _valid(word):
    """一个分词结果算不算有效关键词（word 已转小写）"""
    if not word or len(word) < 2:          # 单字大多是语气词/噪声
        return False
    if word in STOPWORDS:                  # 停用词不要
        return False
    if LAUGH_PAT.match(word):              # 哈哈哈/啊啊啊 是情绪不是主题
        return False
    if all(ch in "0123456789" for ch in word):   # 纯数字（666）交给反应词
        return False
    # 必须含汉字或字母数字，过滤纯标点/表情
    if not any("\u4e00" <= ch <= "\u9fff" or ch.isalnum() for ch in word):
        return False
    return True


def _tokenize(content):
    """一条弹幕 -> 有效关键词列表（统一转小写，OK/ok 合并）"""
    return [w.lower() for w in jieba.cut(content) if _valid(w.lower())]


def extract_keywords(records, top_n=20):
    """全局关键词 TopN：所有弹幕分词 -> 词频统计 -> 取前 top_n"""
    counter = Counter()
    for r in records:
        content = (r.get("content") or "").strip()
        if not content:
            continue
        for w in _tokenize(content):
            counter[w] += 1
    return [{"word": w, "count": c} for w, c in counter.most_common(top_n)]


def keywords_by_segment(records, segments, top_n=10):
    """每个高能片段的关键词 TopN。

    先对所有弹幕分词一次（避免每个片段重复分词），再按片段时间过滤统计。
    """
    tokenized = []
    for r in records:
        content = (r.get("content") or "").strip()
        if not content:
            continue
        sec = int((r.get("progress_ms") or 0) / 1000)
        tokenized.append((sec, _tokenize(content)))

    result = []
    for seg in segments:
        counter = Counter()
        for sec, words in tokenized:
            if seg["start"] <= sec < seg["end"]:
                for w in words:
                    counter[w] += 1
        result.append({
            "start": seg["start"],
            "end": seg["end"],
            "words": [{"word": w, "count": c} for w, c in counter.most_common(top_n)],
        })
    return result