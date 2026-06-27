# AI WeChat English Learning Publisher

一个开箱即用的 **AI 英语学习内容生成与公众号发布平台**。每天自动生成一篇场景化英语学习文章，排版后发布到微信公众号草稿箱。你只需要审核一下就能群发。

## 你能用它做什么

这个项目不绑定任何特定领域——修改场景库，就能适配不同的受众：

| 方向 | 示例场景 |
|------|----------|
| **外企职场英语**（默认） | 晨会 Standup、面试、Code Review、离职面谈 |
| **考研英语** | 阅读精读、长难句分析、翻译技巧、作文模板 |
| **旅游英语** | 出入境、酒店入住、餐厅点餐、问路打车 |
| **商务英语** | 邮件写作、商务谈判、会议主持、报价谈判 |
| **雅思/托福口语** | Part 1/2/3 话题演练、地道表达替换 |
| **日常生活英语** | 点咖啡、看病、租房、社交聚会 |

核心代码不变，只需修改 `scripts/generate.py` 中的场景列表和内容提示词。

---

## 每日内容安排

管线根据星期几自动选择内容类型：

| 星期 | 内容类型 | 说明 |
|------|----------|------|
| 周一至周五 | 职场进阶话题 | 从 29 个场景中随机轮换，覆盖外企工作全场景 |
| 周六 | 轻松话题 | 从 4 个轻松场景中选择（闲聊、入职、团建、出差） |
| 周日 | 本周回顾 | 自动生成周总结文章，回顾一周学过的英语表达精华 |

## 快速开始

### 前置条件

- **Python 3.10+**
- **一个微信公众号**（个人订阅号即可，[mp.weixin.qq.com](https://mp.weixin.qq.com)）
- **DeepSeek API 密钥**（免费注册：[platform.deepseek.com](https://platform.deepseek.com/api_keys)）

### 1. 克隆项目

```bash
git clone https://github.com/<你的用户名>/daily-english.git
cd daily-english
```

> **首次克隆后建议清理示例数据：**
> ```bash
> rm -rf covers/ drafts/ published/
> mkdir covers drafts published
> ```

### 2. 配置密钥

```bash
cp .env.example .env
```

编辑 `.env`，填入以下三个必填项：

| 变量 | 说明 | 获取地址 |
|------|------|----------|
| `WECHAT_APP_ID` | 微信公众号 AppID | 公众号后台 → 设置与开发 → 基本配置 |
| `WECHAT_APP_SECRET` | 微信公众号 AppSecret | 同上（需扫码获取） |
| `DEEPSEEK_API_KEY` | DeepSeek API 密钥 | [platform.deepseek.com](https://platform.deepseek.com/api_keys) |

> **重要：** 在公众号后台 → 设置与开发 → 基本配置 → IP 白名单中，添加你服务器的公网 IP。否则 API 调用会被拒绝。

### 3. 安装依赖（可选）

脚本使用 Python 标准库 + macOS 系统工具，零外部依赖即可运行。如需 Linux 部署：

```bash
pip install -r requirements.txt
```

### 4. 自定义场景（可选）

编辑 `scripts/generate.py`，找到 `WORKPLACE_SCENARIOS` 列表，增删改为你需要的场景：

```python
WORKPLACE_SCENARIOS = [
    # 考研英语示例
    {"zh": "阅读理解精读", "en": "Reading Comprehension",
     "desc": "如何分析长难句、定位关键信息"},
    {"zh": "作文模板应用", "en": "Essay Template Application",
     "desc": "大作文和小作文的常用句型与框架"},
    # ... 按需添加
]
```

同时也建议修改 `SYSTEM_PROMPT` 中的语气和风格定义，让它更像你目标受众的调性。

### 5. 测试生成

```bash
python3 scripts/generate.py
```

这会在 `drafts/` 目录生成一篇 Markdown 草稿。不指定 `--topic` 时随机选题。

指定主题：
```bash
python3 scripts/generate.py --topic "英语面试"
```

列出所有场景：
```bash
python3 scripts/generate.py --list-scenarios
```

### 6. 发布到草稿箱

```bash
python3 scripts/publish.py drafts/2026-06-20-xxxxx.md --author "你的公众号名"
```

发布成功后，到公众号后台 → 草稿箱，检查排版后手动群发。

预览不上传：
```bash
python3 scripts/publish.py drafts/my-article.md --dry-run
```

### 7. 设置定时任务（macOS）

项目包含两套定时任务：
- **每天 18:00** 生成明天的文章
- **每天 09:00** 自动发布（如果当天未手动发布）

```bash
# 一键安装
bash .install-and-run.sh
```

Linux 用户请使用 cron：
```bash
# 每天 18:00 生成
0 18 * * * cd /path/to/daily-english && python3 scripts/generate.py >> /tmp/english-generate.log 2>&1

# 每天 09:00 发布
0 9 * * * cd /path/to/daily-english && python3 scripts/publish.py $(ls -t drafts/*.md | head -1) --author "你的公众号名" >> /tmp/english-publish.log 2>&1
```

---

## 项目结构

```
daily-english/
├── .env.example             ← 密钥模板（.env 是真实密钥，不上传）
├── .gitignore
├── README.md
├── requirements.txt
├── assets/                  ← 默认封面等静态资源
├── covers/                  ← 自动生成的封面图（不上传）
├── drafts/                  ← 待发布草稿 Markdown（不上传）
├── published/               ← 已发布归档 + index.json（不上传）
├── references/              ← 内容参考与迭代记录
│   ├── README.md
│   ├── changelog.md         ← 版本迭代日志
│   └── feedback/            ← 内容优化反馈意见
└── scripts/
    ├── generate.py          ← AI 内容生成器（DeepSeek API）
    ├── publish.py           ← 微信公众号发布脚本
    ├── daily_pipeline.py    ← 全自动管线
    └── daily_pipeline.sh    ← 定时任务入口
```

---

## 自定义指南

### 修改场景库

编辑 `scripts/generate.py` 的 `WORKPLACE_SCENARIOS`。每个场景三种字段：

```python
{"zh": "中文名称", "en": "English Name",
 "desc": "场景说明（用于指导 AI 生成方向）"}
```

场景会自动轮换，状态保存在 `.scenarios_state.json`（不上传 Git）。

### 修改内容风格

编辑 `scripts/generate.py` 的 `SYSTEM_PROMPT` 和 `build_prompt()`：

- **SYSTEM_PROMPT** — 定义 AI 的写作风格、语气、结构
- **build_prompt()** — 每篇文章的具体指令（字数、板块要求等）

比如把"职场英语"改成"考研英语"，你只需要：
1. 替换 `WORKPLACE_SCENARIOS` 为考研场景
2. 修改 `SYSTEM_PROMPT` 中的语气（从"外企同事聊天"改成"老师讲解"）
3. 调整 `build_prompt()` 中的字数要求

### 修改封面样式

编辑 `scripts/publish.py` 的 `COVER_PALETTES` 列表，每项为三色渐变元组：

```python
COVER_PALETTES = [
    ("#1a365d", "#2b6cb0", "#3182ce"),  # 深蓝系
    ("#22543d", "#276749", "#38a169"),  # 绿色系
    # ... 按需添加
]
```

### Markdown → WeChat 排版

`publish.py` 内置完整的 Markdown 渲染器，支持：
- 标题（`#` → `##`）
- 粗体、斜体、行内代码
- 有序/无序列表（flex 布局，手机端不丢失序号样式）
- 引用块
- 表格
- 代码块
- 图片（`![]()` 语法）

---

## 技术架构

```
generate.py                      publish.py
    │                                │
    ▼                                ▼
DeepSeek API ──→ Markdown ──────→ 公众号 HTML
    │                                │
    ▼                                ▼
 drafts/*.md                 SVG ─→ 封面 PNG
                                      │
                                      ▼
                                上传永久素材
                                      │
                                      ▼
                                创建微信草稿
                                      │
                                      ▼
                               published/index.json
```

### 关键设计

- **零外部依赖**：HTTP 用 Python 标准库 `urllib`，环境变量手动解析
- **无数据库**：所有状态存 JSON 文件（`published/index.json` 发布记录、`.scenarios_state.json` 轮换状态）
- **自动重试**：API 调用 3 次指数退避，token 过期自动续期
- **自动摘要**：不传 `--digest` 时从正文前 120 字自动提取
- **封面图**：macOS 用 `qlmanage` + `sips` 生成；Linux 需安装 `cairosvg`

---

## 如何贡献

1. Fork 这个项目
2. 添加你的场景库和 prompt 改进
3. 提交 Pull Request（包含 `references/changelog.md` 的更新）

---

## 许可

MIT
