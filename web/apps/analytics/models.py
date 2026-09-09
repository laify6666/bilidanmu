# -*- coding: utf-8 -*-
"""弹幕分析系统数据模型。

TODO（）——规划表结构：
DanmakuVideo    视频+抓取任务元数据：bvid, cid, title, up_mid, up_name, tname,
                duration, danmaku_count, source(manual/hot50), fetch_status, fetched_at
DanmakuRecord   弹幕明细：bvid, cid, dmid, progress_ms, mode, fontsize, color,
                mid_hash, content, ctime, weight, pool, attr, source, fetched_at
                unique_together = (bvid, dmid)
DanmakuAnalysis 分析结果：bvid, snapshot(JSON: 时间密度/热门弹幕/高能片段/活跃时段), created_at

（原 watch_history / user_tag_profile / recommend / warehouse_consent 相关模型已移除）
"""
# -*- coding: utf-8 -*-
"""弹幕分析系统数据模型。"""
from django.db import models


class DanmakuVideo(models.Model):
    """视频 + 抓取任务元数据：一个视频一条"""

    bvid = models.CharField("BV号", max_length=32, unique=True)
    cid = models.BigIntegerField("视频cid", default=0)
    title = models.CharField("标题", max_length=500)
    up_mid = models.BigIntegerField("UP主ID", default=0)
    up_name = models.CharField("UP主", max_length=100, blank=True)
    tname = models.CharField("分区", max_length=100, blank=True)
    duration = models.IntegerField("时长(秒)", default=0)
    danmaku_count = models.IntegerField("弹幕数", default=0)
    source = models.CharField("来源", max_length=20, default="manual")  # manual=手动 / hot50=热门榜
    fetch_status = models.CharField("抓取状态", max_length=20, default="pending")
    fetched_at = models.DateTimeField("抓取时间", null=True, blank=True)
    created_at = models.DateTimeField("创建时间", auto_now_add=True)

    class Meta:
        db_table = "danmaku_video"
        verbose_name = "弹幕视频"
        verbose_name_plural = verbose_name
        ordering = ["-created_at"]

    def __str__(self):
        return self.title[:30]


class DanmakuRecord(models.Model):
    """弹幕明细：一条弹幕一行"""

    video = models.ForeignKey(DanmakuVideo, null=True, blank=True,
                              on_delete=models.CASCADE, related_name="danmakus",
                              verbose_name="视频")
    bvid = models.CharField("BV号", max_length=32, db_index=True)
    cid = models.BigIntegerField("视频cid", default=0)
    dmid = models.BigIntegerField("弹幕ID", default=0)      # 去重键
    progress_ms = models.BigIntegerField("弹幕位置(毫秒)", default=0)
    mode = models.IntegerField("模式", default=1)           # 1滚动 4底部 5顶部
    fontsize = models.IntegerField("字号", default=25)
    color = models.BigIntegerField("颜色", default=0)       # RGB 整数
    mid_hash = models.CharField("用户哈希", max_length=32, blank=True)
    content = models.TextField("弹幕内容")
    ctime = models.BigIntegerField("发送时间戳", default=0, db_index=True)
    weight = models.IntegerField("权重", default=0)
    pool = models.IntegerField("弹幕池", default=0)
    attr = models.BigIntegerField("属性", default=0)
    source = models.CharField("来源", max_length=20, default="manual")
    fetched_at = models.DateTimeField("抓取时间", auto_now_add=True)

    class Meta:
        db_table = "danmaku_record"
        verbose_name = "弹幕记录"
        verbose_name_plural = verbose_name
        unique_together = [("bvid", "dmid")]   # ★ 同一视频内弹幕ID唯一 = 天然去重
        ordering = ["progress_ms"]
        indexes = [models.Index(fields=["bvid", "progress_ms"])]  # 按视频查弹幕更快

    def __str__(self):
        return self.content[:30]


class DanmakuAnalysis(models.Model):
    """单视频弹幕分析结果（JSON 快照，页面直接读）"""

    video = models.ForeignKey(DanmakuVideo, null=True, blank=True,
                              on_delete=models.CASCADE, related_name="analyses",
                              verbose_name="视频")
    bvid = models.CharField("BV号", max_length=32, db_index=True)
    snapshot = models.JSONField("分析结果", default=dict, blank=True)
    created_at = models.DateTimeField("生成时间", auto_now_add=True)

    class Meta:
        db_table = "danmaku_analysis"
        verbose_name = "弹幕分析"
        verbose_name_plural = verbose_name
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.bvid} 分析"