# WorkBuddy 开发对话上下文

本文件记录本项目在 WorkBuddy 中的开发过程，用于核验是否符合 WorkBuddy 专项奖励条件。

---

## 项目信息

| 项目 | 内容 |
|---|---|
| 作品名称 | 麦麦免开口 (mcd-quiet-order) |
| 一句话定位 | 从下单到取餐，不用跟任何人说一句话 |
| 开发工具 | WorkBuddy（Skill 开发 + 麦当劳 MCP 连接器调试） |
| 开发周期 | 2026-10-15 起 |
| 仓库结构 | Skill 本体 + 赛事必备文档（README / CONTEST_DECLARATION / MCP_INTEGRATION） |

---

## 使用 WorkBuddy 开发的关键环节

### 1. 赛事与接口调研

- 通过 WorkBuddy 读取活动仓库 `M-China/mcd-developer-innovation-challenge` 的 README、活动规则与参赛声明，确认提交物要求。
- 读取 `M-China/mcd-mcp-server` 的接入文档，梳理出 MCP Server 的 8 大类、33 个工具及其参数规则。
- 直接用 WorkBuddy 拉取 Tool 的完整 schema（`create-order`、`calculate-price`、`query-meal-detail`、`query-meals`），据此确认「订单备注仅外送可用」「到店场景无备注通道」等关键约束——这些是从文档标题看不出来、只有读参数定义才能发现的细节。

### 2. 连接器配置与排障

- 在 WorkBuddy 的【自定义连接器】中接入麦当劳 MCP。
- 遇到 `Authorization` 缺少 `Bearer ` 前缀导致 401、界面显示「需要认证」的问题，通过直接向 `https://mcp.mcd.cn` 发初始化请求定位并修复。

### 3. 需求与赛道调研

- 通过 WorkBuddy 拉取赛事排行榜与报名 Issue 列表，梳理已有项目覆盖的功能方向，据此确认本项目的定位与边界。
- 检索「听障」「社恐」「无障碍」「老年人」等关键词，确认沟通不便场景下的真实需求与现有方案覆盖情况。
- 阅读同赛道公开实现（MIT 许可）的说明与源码，学习其「本地穷举 + MCP 核价」的架构思路，并**独立完成实现**；许可与来源说明见 `THIRD_PARTY_NOTICES.md`。

### 4. Skill 开发

- 编写 `SKILL.md` 技能定义与五条工作流。
- 编写 `references/` 下的工具速查与优惠策略。
- 编写 `scripts/best_coupon_calc.py`（本地优惠组合优化器），并在本地用示例数据完成两阶段验证。
- 编写 `scripts/preference_store.py`（偏好本地档案），实测 `order-list` 返回结构后确定「可推断 / 不可推断」边界。
- 编写 `scripts/demo.py` 全流程模拟演示：不联网、不下单、不动真实档案，让无 Token 的用户也能看清完整链路。
- 编写 `assets/quiet-card.html` 零开口沟通卡模板。
- 生成 `assets/cover.png` 项目封面。

---

## 关键决策记录

| 决策 | 结论 | 理由 |
|---|---|---|
| 产品定位 | 沟通无障碍（选品到取餐的静默链路） | 面向沟通不便人群，把诉求前置到订单里 |
| 核心链路 | 下单 → 取餐全程静默 | `remark`、特制与取餐柜码都在 `create-order` 环节 |
| 是否下单 | 下单但不代付 | 付款仍由用户完成，责任边界清晰 |
| 优惠计算定位 | 辅助能力 | 服务于「不必为了省钱去问店员」 |
| 优惠搜索架构 | 本地穷举 + MCP 核价 | 避开 600 次/分钟限流，同时保证金额真实 |
| 受众模式 | 自动适配，不分模式 | 降低使用门槛，避免让用户先做一道选择题 |

---

## 说明

本项目为「麦当劳程序员节创意开发大赛」参赛作品，由参赛者使用 WorkBuddy 独立开发，非麦当劳官方产品。
