# B站弹幕分析系统 · Web 后端（Django）

## 技术栈
Django 5 + SQLite(本地)/MySQL(上线) + requests(爬虫) + jieba(分词) + ECharts(图表)

## 功能
- **按 BV 号爬取全量弹幕并分析**（`manage.py bili_fetch_danmaku --bvid XXX`）
  - A1 高能片段：自适应窗口 + z-score + 重叠容差 + 佐证弹幕
  - A1 反应词：自动发现观众瞬间刷的短句
  - A2 情感分析：词典打分 + 情感传播（字面优先 + 传播兜底）
  - A3 关键词：jieba 分词 + 停用词过滤
- **报告页**：8 模块仪表盘（KPI / 时间轴 / 高能片段卡片 / 反应词云 / 关键词 / 分布 / 弹幕表）

## 快速开始（Windows 本地）
```powershell
cd E:\架构\web
# 首次装依赖（已装过可跳过）
# .venv\Scripts\python.exe -m pip install -r requirements.txt

# 初始化数据库
.venv\Scripts\python.exe manage.py migrate

# 爬取并分析一个视频（示例）
.venv\Scripts\python.exe manage.py bili_fetch_danmaku --bvid BV15BuR6MEeR

# 启动
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

## 页面
| 路径 | 说明 |
|---|---|
| /danmaku/ | 输入 BV 号 |
| /danmaku/analyze/?bvid=XXX | 单视频分析报告（8 模块） |
| /admin/ | Django 管理后台（需 createsuperuser） |

## 分析模块（apps/analytics/analysis/）
| 文件 | 职责 |
|---|---|
| danmaku.py | 高能片段 + 反应词 + 汇总入口 analyze_danmaku() |
| sentiment.py + emotion_dict.py | 情感打分 + 传播扩展 |
| keywords.py | jieba 关键词 |

每步实现文档见 `docs/steps/`（功能需求/技术选型/实现思路/具体代码/验证/踩坑）。

## 数据目录（DATA_ROOT=E:\架构\data）
- `raw/` 原始抓取数据
- `out/danmaku/{bvid}.json` 单视频分析结果（页面直接读，没有就现场算）
- `logs/` 运行日志

## 切到 MySQL（上线用）
复制 .env.example 为 .env，设置 DB_ENGINE=mysql / DB_NAME / DB_USER / DB_PASSWORD / DB_HOST / DB_PORT，然后 `python manage.py migrate`。