# B站个人视频分析系统 · Bili Video Analyzer

> 从零搭建的 **"B站观看历史 → 标签画像 → 个性化推荐 + 深度洞察"** 系统。
> 个人分析**本地秒级完成（0.02s）**，架构轻量聚焦，可平滑扩展 AI 问答层。

---

## ✨ 核心亮点

- **本地秒级分析**：纯 Python 实现，0.02s 出全部结果，不依赖大数据框架（技术选型见下文）。
- **真实数据闭环**：扫码登录 B 站，抓取真实观看历史，产出标签画像、个性化推荐与五维深度洞察。
- **画像 v2**：多因子兴趣强度（行为权重 × 时长因子 × 双时间窗衰减）+ softmax 带温度归一化，区分"当下热点"与"长期偏好"。
- **推荐 v2**：混合排序（画像匹配 + 质量分 + 时效分 + UP主偏好）+ **MMR 多样性去重**，缓解信息茧房。
- **五维深度洞察**：时间行为 / UP主关系 / 兴趣演变 / 标签共现网络 / 观众人设，从"统计"升级到"洞察"。
- **Web 可视化**：ECharts 交互图表，含 5 个独立维度页。
- **用完即弃的登录态**：分析完成自动清空 SESSDATA 断开登录，同时保留查看权限；数据按账号隔离。
- **隐私合规设计**：真实数据只做本人个人分析，遵循最小必要、匿名化、用完即弃原则；**进入平台数仓必须经用户主动授权**（登录页弹窗，`warehouse_consent` 表留痕）。
- **平台级数仓联动**：**登录页弹窗授权**，同意后分析完成自动将数据入 VM Hadoop 数仓（按 UID 隔离）；Airflow 每日 01:30 定时离线批处理，产出平台洞察页（DAU/MAU、UP 主热度、用户分群等）。

---

## 🏗️ 系统架构

```mermaid
flowchart TB
    subgraph 采集层
        A[扫码登录 B 站] --> B[Django 爬虫 / 同步]
    end
    B --> C[(SQLite/MySQL<br/>观看历史)]
    B --> D[(原始 JSON<br/>data/raw)]

    subgraph 本地轻量分析（秒级）
        C --> E[analysis 核心<br/>画像v2 + 推荐v2 + 五维洞察]
        E --> F[结果库<br/>user_tag_profile / recommend_result]
        E --> G[(data/out/dimensions<br/>维度 JSON)]
    end

    F --> H[Django Web<br/>画像 / 推荐 / 历史]
    G --> H
    H --> I[维度页<br/>人设 / 时间 / UP主 / 演变 / 共现]

    subgraph 平台级数仓（VM · 离线批处理）
        H -->|登录页授权| K[data/warehouse/<uid>]
        K --> L[(HDFS<br/>consented/uid + mock)]
        L --> M[Airflow 每日 01:30<br/>Spark ODS→DWD→DWS→ADS + DQC]
        M --> N[平台指标/画像/推荐导出]
    end
    N --> P[平台洞察页 /platform/]
    H --> J[AI 问答层<br/>规划中]
```

**数据流**：采集 → 数据库 / 原始 JSON → 本地轻量分析 → Web 展示；授权后进入平台数仓 → 离线批处理 → 平台洞察页。

---

## 📸 运行示例

![首页（未登录）](screenshots/home.png)

![扫码登录](screenshots/login.png)

![分析结果页](screenshots/dashboard.png)

![观众人设](screenshots/persona.png)

![时间行为](screenshots/time.png)

![标签共现网络](screenshots/cooccur.png)

![平台](screenshots/desk.png)
## 🧰 技术栈

| 层次 | 技术 |
|---|---|
| 采集 / 展示 | Python 3.12 · Django 5 · Celery · ECharts |
| 个人分析 | 纯 Python（多因子画像 / 混合推荐 / 五维洞察），零重型依赖，秒级 |
| 平台数仓 | Hadoop 3.3.6（HDFS/YARN/MapReduce）· Spark 3.5.1（PySpark）· Hive 3.1.3 · Airflow 2.10.4 · Parquet + Snappy |
| 存储 | SQLite（本地）/ MySQL（上线） |

---

## 📂 目录结构

```
.
├── web/                           # Django Web 应用
│   ├── apps/analytics/analysis/   # ★ 个人分析核心
│   │   ├── profile.py             # 画像 v2：多因子 + 双时间窗 + softmax
│   │   ├── recommend.py           # 推荐 v2：混合排序 + MMR 多样性
│   │   ├── dimensions.py          # 时间行为/UP主关系/兴趣演变/标签共现
│   │   └── pipeline.py            # 个人分析管线（读库→计算→写库+JSON）
│   ├── apps/analytics/management/commands/
│   │   └── analyze_local.py       # 本地分析命令：manage.py analyze_local
│   ├── apps/fetcher/services.py   # 一键分析编排（同步→补标签→候选池→本地分析→断开）
│   └── templates/
│       ├── dashboard.html         # 结果首页（含"深度洞察"入口）
│       ├── dimension_persona.html # 观众人设页
│       ├── dimension_time.html    # 时间行为页
│       ├── dimension_up.html      # UP主关系页
│       ├── dimension_evolution.html # 兴趣演变页
│       └── dimension_cooccur.html # 标签共现网络页
├── data/
│   ├── out/dimensions/            # ★ 维度结果 JSON（本地分析生成）
│   └── raw/                       # 爬虫原始 JSON（gitignored）
├── docs/                          # 工程文档（开发日志等）
└── bigdata/                       # ★ 平台级大数据模块（VM 内独立运行）
    ├── scripts/spark_jobs/        # Spark：ODS→DWD→DWS→ADS + 平台洞察(job_06)
    ├── scripts/airflow/           # Airflow 调度 DAG
    ├── scripts/run_offline_spark.sh  # 一键离线分析（VM 执行）
    ├── configs/                   # Hadoop/Hive 配置样本
    └── docs/                      # 搭建教程 / 数仓设计 / 查错手册
```

---

## ⚡ 技术选型：为什么个人分析不用大数据框架

| 方案 | 耗时 | 说明 |
|---|---|---|
| **本地轻量分析（本项目）** | **0.02s** | 千级数据单机内存计算，纯 Python 单遍扫描 |
| 大数据框架（对比） | 1m6s | 框架启动开销（JVM + SparkContext + Executor）远大于计算本身 |

> **结论**：数据量较小时，框架启动开销 > 计算本身。本项目个人分析采用本地实现（提速约 3300 倍），
> 而 Hadoop/Spark 等大数据框架独立为仓库内 `bigdata/` 子模块（VM 内 Hadoop+Hive+Spark+Airflow），
> 通过「授权入库 → 离线批处理 → 平台洞察页」与 Web 联动，用于**多用户、百万级数据**的平台级场景。
> 这是一次完整的技术选型实践：**先看数据规模与场景，再选框架**。

---

## 🚀 快速开始（单机版）

### 1. 一键分析（推荐 · 本地秒级）

```powershell
cd web
.venv\Scripts\python.exe manage.py run_full_analysis
# 流程：同步历史 → 补标签 → 抓候选池 → 本地轻量分析（秒级） → 自动断开登录
```

数据已同步、只想重算分析时：

```powershell
.venv\Scripts\python.exe manage.py analyze_local [--account-id 1] [--top 20]
```

### 2. Web 应用

```powershell
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

访问 http://127.0.0.1:8000 ，扫码登录 B 站后点击「一键分析」，即可查看：
- 标签画像 / 推荐 Top20 / 历史记录
- **五维深度洞察**：观众人设、时间行为、UP主关系、兴趣演变、标签共现网络

### 3. 平台级分析（可选 · 需要虚拟机 Hadoop/Spark/Airflow）

生成模拟多用户数据并跑离线批处理，结果展示在平台洞察页：

```powershell
# 1) 生成模拟数据（500 用户 × 30 天，按天 JSON）并本地校验
python bigdata\scripts\gen_mock_data.py --out E:/架构/data/mock
python bigdata\scripts\check_mock_data.py --dir E:/架构/data/mock

# 2) 虚拟机内一键跑批（上传 → ODS→DWD→DWS→ADS → 平台洞察 → 导出）
bash /opt/bili/bin/run_offline_spark.sh

# 3) 或交给 Airflow 每日 01:30（北京时间）自动跑
#    Airflow UI: http://192.168.63.128:8085 （DAG: bili_offline_dag）
```

### 4. 环境准备

```powershell
cd web
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python.exe manage.py migrate
```

无需虚拟机 / 大数据环境，Windows 本地即可跑通全部功能。

---

## 🔒 隐私说明

- 真实观看历史、画像、推荐结果属于**个人隐私**，不随仓库公开（`.gitignore` 已排除 `data/raw/`、`data/out/`、`db.sqlite3` 等）。
- **合规设计**：真实数据只用于账号本人的个人分析，遵循最小必要、匿名化、用完即弃原则（参考 PIPL）。
- **授权入库**：数据加入平台数仓前，登录页弹窗征求用户同意（`warehouse_consent` 表留痕），拒绝则不入库；入库数据按 UID 隔离、仅用于聚合分析。
- 仓库内文档中的统计数字均做了脱敏描述，可放心公开。

---

## 🗺️ 未来规划

- **AI 问答层**：数据问答 Agent（自然语言 → 工具调用 → 查数据）+ RAG 知识问答（文档检索）+ AI 洞察报告。
- **分析维度扩展**：观看深度（完播/互动）、小众度/考古率，需要补充行为数据字段。
- **平台分析规模化**：造数生成器已支持 500 用户×30 天量级，可扩展到 10 万用户×亿级，跑多节点集群。
- **实时数仓**：Kafka + Flink 实时链路（平台洞察目前为离线日更）。
- **上线**：DB 切 MySQL，Web 走 Nginx + Gunicorn（见 `docs/上线改造计划书.md`）。
