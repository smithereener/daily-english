# 📋 迭代变更记录

## [v0.2] — 2026-06-15

### Added
- `publish.py`：完全重写，零外部依赖
  - 完整 Markdown 渲染（表格、引用、代码块、有序/无序列表）
  - 封面图生成（6 套配色，macOS qlmanage → sips → 默认封面）
  - API 重试（3 次指数退避）+ token 自动续期
  - 发布归档到 `published/index.json`
  - `--dry-run` 预览模式
- `generate.py`：基于 DeepSeek Chat API 的内容生成器
  - 25 个外企场景，轮换不重复
  - `--mock` 离线测试模式
  - `--list-scenarios` 列出所有场景
- `daily_pipeline.py`：生成→发布→归档 全自动管线
- `requirements.txt`：可选依赖清单
- `references/`：内容参考与迭代记录目录

### Fixed
- `.env.example` 移除真实凭据（占位符替代）
- `.env`/`.env.example` 解析优先级：先读 `.env`，`.env.example` 不覆盖
- 标题渲染层级优化：`###` → 映射为 H2 级别样式（更大字号 + 下划线）
- 有序列表：跨空行连续编号，不再碎片化
- HTML 模板标题去重（模板不再重复嵌入标题）
- `.gitignore`：补充 `.scenarios_state.json`、`references/`

### Changed
- **内容生成 Prompt 重大改进（v2）**
  - 去除固定模版结构（不再用 emoji 分段）
  - 语言从"说明书风"改为"朋友聊天风"
  - 开头用具体场景画面抓住读者
  - 正文自然地融入 2-3 个最实用表达
  - 穿插简短真实对话（4-6 轮）
  - 结尾有行动建议 + 互动引导
  - 总字数从 600-1000 缩到 500-800，更精炼
- Markdown renderer：无序列表子项（`- *...*`）渲染为缩进圆圈样式

### Published
- ✅ **Morning Standup Meeting** — 首次发布（v1 prompt）
- ✅ **Brainstorming Session** — 改进后发布（v2 prompt）

### 待优化 (Backlog)
- [ ] 优质内容案例收集（小红书/公众号）
- [ ] 多图文（一次发布多篇文章）支持
- [ ] 历史内容数据统计（阅读量、转发）
- [ ] 读者评论管理
- [ ] Linux 跨平台封面生成（cairosvg）

## [v0.3] — 2026-06-19

### Added — Content Structure
- **三大尾栏板块**：每篇文章末尾固定三个板块
  - 📖 今天学到的词 — 3-5 个核心单词，含词性标注 + 地道例句
  - 🔧 今天能用的句子 — 2-3 个高频句型，含中文说明 + 使用场景
  - ✍️ 小练习 — 场景化写作任务，引导读者在留言区互动
- **表达深度分析**：每个表达拆解三层（字面含义 → 语气潜台词/文化差异 → 进阶用法），从"知道"到"会用"
- **开头画面感升级**：3句话→4-6句话，加入时间/地点/动作/心理活动等感官细节

### Added — Scene Library
- 4 个轻松话题场景（3:1 实用:轻松配比）：
  - 办公室闲聊 (Water Cooler Chat)
  - 入职第一天 (First Day Onboarding)
  - 团队聚餐社交 (Team Bonding Activities)
  - 出差归来闲谈 (Back from Business Trip)
- 总计：25 → **29 个场景**

### Fixed — List Rendering (Critical)
- **完全重写**列表渲染：弃用 `<ol>/<ul>/<li>` 标签，改用 `display:flex` div 布局
- 序号/圆点由 CSS 精确控制（`font-size:15px`），不受 WeChat 移动端默认样式覆盖
- `flex-shrink:0` 防止序号被压缩，`flex:1` 让正文填满剩余空间
- 子项缩进仅在有序列表（OL）内部触发，无序列表所有项等宽
- 清理所有残留 `</ul>/</ol>` 闭合标签

### Changed — Prompt (P1 + P2)
- 字数上限：800-1200 → 1200-1500 字（v3 prompt）
- `max_tokens`：3072 → 4096
- 段落长度限制：每段不超过 3-4 行（移动端可读性）
- 输出格式精确化：三大尾栏用 `##` 分隔、`###` 标题

### Published
- ✅ **Your Exit Interview: Don't Burn the Bridge** — 首个三大板块版本
- ✅ **Morning Standup Meeting** — v3 prompt 完整版 + flex 列表渲染
