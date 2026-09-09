# -*- coding: utf-8 -*-
"""弹幕系统 API 视图（挂在 /api/ 下）。

页面视图在 apps/web/views.py（danmaku_index / danmaku_analyze / danmaku_hot）。

TODO（待自己实现）：
- POST /api/danmaku/fetch/        按用户提交的 bvid 触发爬取（后台任务）
- GET  /api/danmaku/status/       查询抓取进度
- POST /api/danmaku/hot/trigger/  手动触发热门榜 Top50 定时爬取
"""