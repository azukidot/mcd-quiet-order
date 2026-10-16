# MCP 集成说明

本文档说明「麦麦免开口」实际使用的麦当劳 MCP Server、Tool、调用流程与业务价值。

---

## 1. 使用的 MCP Server

| 项目 | 值 |
|---|---|
| 服务名称 | 麦当劳中国 MCP Server（`mcd-mcp`） |
| 接入地址 | `https://mcp.mcd.cn` |
| 传输协议 | Streamable HTTP |
| 鉴权方式 | 请求头 `Authorization: Bearer <MCP_TOKEN>` |
| 限流 | 每 Token 600 次/分钟（超出返回 429） |
| Token 获取 | <https://open.mcd.cn/mcp> → 手机号登录 → 控制台 → 激活 |

> 本 Skill 不读取、不存储、不输出 Token；Token 由用户在 MCP 客户端侧自行配置。

---

## 2. 使用的 Tool 清单

本 Skill 共调度 **17 个** MCP Tool。

### 2.1 下单（核心）

| Tool | 用途 | 在本 Skill 中的角色 |
|---|---|---|
| `create-order` | 创建订单，返回订单详情与支付链接 | **核心**：把「要吸管」「不要冰」「放门口别敲门」写进订单，让订单替用户说话 |

`create-order` 中被本 Skill 重点使用的字段：

| 字段 | 无障碍语境下的用途 |
|---|---|
| `remark` | 订单备注（最长 50 字）——承载外送场景的全部口头诉求，官方示例即「无接触配送」 |
| `modification` | 商品特制（去冰、少酱、换品）——把口味诉求结构化，无需口头说明 |
| `needTableware` | 是否需要餐具——把「要餐具」变成一次勾选 |
| `beType` | 取餐方式：1 到店自取 / 2 麦乐送 / 5 得来速 / 6 团餐 |
| `reservationDate` | 预约时间——可提前下单，避免到店等待时的沟通 |
| 返回的取餐柜二维码 | 到店场景扫码自取，**不需要找店员拿餐** |

### 2.2 订单查询

| Tool | 用途 | 在本 Skill 中的角色 |
|---|---|---|
| `query-order` | 查询订单状态、内容、配送信息 | 用户支付后确认订单是否生效、餐品是否备好 |
| `cancel-order` | 取消订单 | 仅在用户明确要求时调用 |

### 2.3 商品与价格

| Tool | 用途 | 在本 Skill 中的角色 |
|---|---|---|
| `query-meals` | 门店在售餐品列表 | 把自然语言需求映射为 `productCode`，流程起点 |
| `query-meal-detail` | 餐品详情、套餐组成、特制选项 | 获取 `modification` 选项，支撑「去冰」「少酱」等诉求 |
| `calculate-price` | 计算金额、配送费、优惠额、应付总价 | 逐券试算，产出最省方案；同时返回 `takeWayList` 供下单使用 |

### 2.4 优惠券

| Tool | 用途 | 在本 Skill 中的角色 |
|---|---|---|
| `query-my-coupons` | 账户下所有可用券 | 券池之一：已拥有的券 |
| `query-store-coupons` | 当前门店可用券 | 券池之二：门店专属券 |
| `available-coupons` | 麦麦省可领取券 | 券池之三：可领取的券 |
| `auto-bind-coupons` | 一键领取麦麦省全部可用券 | 用户确认后扩充券池 |

### 2.5 门店与地址

| Tool | 用途 | 在本 Skill 中的角色 |
|---|---|---|
| `query-nearby-stores` | 附近餐厅 | 到店 / 得来速的 `storeCode` 与 `beCode` 来源 |
| `delivery-query-stores` | 收货地址附近可配送门店 | 麦乐送 / 团餐的 `storeCode` 与 `beCode` 来源 |
| `delivery-query-addresses` | 用户已创建的配送地址 | 外送下单的 `addressId` 来源 |

### 2.6 辅助信息

| Tool | 用途 | 在本 Skill 中的角色 |
|---|---|---|
| `list-nutrition-foods` | 营养成分（能量、蛋白质、脂肪、碳水、钠、钙） | 支撑「低钠」「控糖」等筛选 |
| `campaign-calendar` | 当月营销活动日历 | 提示当期活动，与券叠加后给更优方案 |
| `query-my-account` | 积分账户信息 | 提示即将过期积分的机会成本 |
| `now-time-info` | 当前时间 | 判断券有效期、活动状态、预约时间合法性 |

---

## 3. 典型调用流程

### 3.1 流程 A：静默下单（麦乐送外送）

```
用户：帮我点个麦乐送，我不想跟骑手说话，放门口就行
  │
  ├─ 1. now-time-info              → 当前时间
  ├─ 2. delivery-query-addresses   → 取 addressId（无地址则引导用户自行添加）
  ├─ 3. delivery-query-stores      → 取 storeCode 与 beCode
  ├─ 4. query-meals                → 取商品 productCode
  ├─ 5. query-meal-detail          → 取特制选项（去冰 / 少酱）
  ├─ 6. 汇总券池：query-my-coupons / query-store-coupons / available-coupons
  ├─ 7. best_coupon_calc.py --plan → 生成试算计划
  ├─ 8. calculate-price × N        → 逐方案试算
  │      参数：beType=2、orderType=2、beCode=<delivery-query-stores 返回>
  ├─ 9. best_coupon_calc.py --choose → 选出最省方案
  │
  ├─ 10. 【用户确认】商品 / 门店 / 地址 / 备注内容 / 实付金额
  │
  ├─ 11. create-order              → 提交订单
  │      参数：beType=2、orderType=2、beCode、addressId、
  │            items[]（含 couponId / modification）、
  │            remark="无接触配送，请放门口，不用敲门"
  │
  ├─ 12. 返回支付链接 → 引导用户「扫码或打开麦当劳 App 完成支付，完成后回复『支付完成』」
  ├─ 13. query-order               → 确认订单状态
  └─ 14. 输出取餐 / 送达指引卡
```

**关键点**：`remark` **仅在外送（`orderType=2`）场景可用**。这正是本流程把「不想和骑手打交道」的诉求一次写清、此后全程无需通话的原因。

### 3.2 流程 B：静默下单（到店取餐）

```
用户：到店取餐，不好意思跟店员要吸管
  │
  ├─ 1. query-nearby-stores        → 取 storeCode（到店自取不传 beCode）
  ├─ 2. query-meals                → 取 productCode
  ├─ 3. query-meal-detail          → 取特制选项
  ├─ 4. 券池汇总 → best_coupon_calc.py --plan
  ├─ 5. calculate-price            → beType=1、orderType=1（不传 beCode）
  │      返回中的 data.takeWayList[].code 即下一步需要的 takeWayCode
  ├─ 6. best_coupon_calc.py --choose → 选最省方案
  │
  ├─ 7. 【用户确认】
  ├─ 8. create-order               → beType=1、orderType=1、takeWayCode、items[]、needTableware
  │      注意：到店场景**没有 remark 通道**，诉求改由「特制 + 餐具 + 沟通卡」承载
  ├─ 9. 返回支付链接 + 取餐柜二维码 → 扫码自取，无需找店员
  └─ 10. 若仍需临时诉求（吸管 / 手套）→ 生成沟通卡
```

**关键点**：到店场景的取餐柜二维码，把「取餐」这一步的对话也消掉了。

### 3.3 流程 C：优惠试算（辅助）

与流程 A/B 的第 6–9 步同构，可独立触发（用户只问「怎么买最省」而不下单）。

支持**跨场景比价**：对同一份餐品分别以 `beType=1`（到店）和 `beType=2`（麦乐送）试算，输出含配送费的到手价差异。

### 3.4 流程 D：沟通卡

```
用户：不好意思跟店员说要一副手套
  ├─ 1. 识别诉求类型：物品索取 / 口味调整 / 服务询问
  ├─ 2. 若为口味类 → query-meal-detail 确认是否为标准特制项，是则优先走订单
  ├─ 3. 规范化为 ≤15 字短句（店员一眼可读）
  ├─ 4. 套用 assets/quiet-card.html 注入文本
  └─ 5. 输出：大字展示 / 一键朗读
```

---

## 4. 关键参数规则（实现要点）

以下规则来自 Tool 定义，是本 Skill 稳定运行的前提，已固化在 `references/` 中：

1. **`beType` 与 `orderType` 组合规则**

   | 场景 | beType | orderType | beCode | 其他必填 |
   |---|---|---|---|---|
   | 到店自取 | 1 | 1 | **不传**（传了会报错） | `takeWayCode` |
   | 得来速 DT | 5 | 1 | 必传（`query-nearby-stores`） | `takeWayCode` |
   | 麦乐送 | 2 | 2 | 必传（`delivery-query-stores`） | `addressId` |
   | 企业团餐 | 6 | 2 | 必传（`delivery-query-stores`） | `gmServiceCode` |

2. **`takeWayCode` 的来源**：`calculate-price` 返回的 `data.takeWayList[].code`，仅在 `orderType=1` 时传给 `create-order`。

3. **价格单位为「分」**：`calculate-price` 与订单返回的金额均以分为单位，展示前必须除以 100 转为「元」。

4. **特制 `modification` 的 key 传递规则**：对包含 `unselectedKey` 的特调组，**组内所有特调项都必须传入**——选中项用 `selectedKey`，未选中项用 `unselectedKey`。漏传会导致配置与预期不符。

5. **`remark` 仅限外送**：`orderType=2` 场景下引导用户填写，最长 50 字；到店与得来速不可用。

6. **支付后置**：`create-order` 只生成订单与支付链接，**付款由用户本人完成**；之后用 `query-order` 确认状态。

---

## 5. 业务价值

1. **让订单成为用户的「代言人」**
   把 `remark`（交付方式）、`modification`（口味）、`needTableware`（餐具）用起来，让多数口头诉求在下单那一刻就被写清楚；再用取餐柜码把「取餐」也变成扫码自取，不需要找人；最后由沟通卡兜住剩下传不进去的部分。

2. **对官方能力的编排**
   `remark` 与取餐柜码都是麦当劳 MCP 已提供的能力。本 Skill 做的是**编排**——把它们按「沟通不便用户的完整动线」串起来，让原本零散的能力组合成一条可以走通的链路。

3. **同一套输出适配三类差异极大的用户**
   听障不需要语音、长辈不需要读小字、社恐不需要开口——输出形态自适应，而不需要用户先学会使用工具。

4. **优惠试算作为辅助，而非卖点**
   把最省方案算清楚是基础能力，本 Skill 将其置于「静默链路」之中，服务于「不用为了省钱而被迫去问店员」这一目标。

---

## 6. 未使用的工具及原因

| 未使用 | 原因 |
|---|---|
| `mall-create-order` / `mall-order-list` / `mall-order-detail` | 麦麦商城与核心点餐链路无关 |
| `party-order-create` / `query-party-*` | 主题活动预约属独立场景，不在本期范围 |
| `draw-lottery` / `query-lottery-info` / `query-my-prizes` | 抽奖为高风险操作，不适合代为执行 |
| `delivery-create-address` | 涉及用户地址写入，交由用户自行完成 |
| `query-meal-assistance` | 仅企业团餐场景，非目标用户 |
| `order-list` | 历史订单分析属于「省钱」方向已有作品的主场，非本项目差异化点 |

以上工具可在后续版本按需开放，当前默认保持「点餐闭环所需的最小集合」。
