# MCP 工具速查

本文件是「麦麦免开口」调用的麦当劳中国 MCP Tool 的字段与顺序速查。
服务地址 `https://mcp.mcd.cn`，Streamable HTTP，鉴权头 `Authorization: Bearer <token>`，限流 600 次/分钟。

---

## 1. 工具总览

| Tool | 类别 | 关键入参 | 关键返回 |
|---|---|---|---|
| `now-time-info` | 辅助 | — | 当前完整时间 |
| `query-nearby-stores` | 门店 | 地址 | `storeCode`、得来速 `beCode` |
| `delivery-query-addresses` | 地址 | — | `addressId`、`beCode` |
| `delivery-query-stores` | 门店 | 地址 | `storeCode`、`beCode` |
| `query-meals` | 商品 | `storeCode`、`orderType`、`beType` | 商品列表、`productCode`、随单购 |
| `query-meal-detail` | 商品 | 上列 + `code` | 套餐组成、`modification`、`selectedKey`/`unselectedKey` |
| `calculate-price` | 价格 | 上列 + `items[]` | 金额（分）、`takeWayList[].code` |
| `create-order` | 下单 | 上列 + 取餐方式与 `takeWayCode` | 订单号、支付链接、取餐柜二维码 |
| `query-order` | 订单 | 订单标识 | 订单状态、内容、配送信息 |
| `cancel-order` | 订单 | 订单标识 | 取消结果 |
| `query-my-coupons` | 券 | — | 账户券列表 |
| `query-store-coupons` | 券 | `storeCode` | 门店可用券 |
| `available-coupons` | 券 | — | 麦麦省可领券 |
| `auto-bind-coupons` | 券 | — | 一键领券结果 |
| `list-nutrition-foods` | 营养 | — | 能量、蛋白质、脂肪、碳水、钠、钙 |
| `campaign-calendar` | 活动 | 月份 | 进行中 / 往期 / 未来活动 |
| `query-my-account` | 积分 | — | 可用 / 累计 / 冻结 / 即将过期积分 |

---

## 2. 取餐方式参数矩阵（最重要）

`query-meals`、`query-meal-detail`、`calculate-price`、`create-order` 四个工具共享同一套取餐方式规则。

| 场景 | `beType` | `orderType` | `beCode` | 额外必填 |
|---|---|---|---|---|
| 到店自取 | 1 | 1 | **不传**（传了报错） | `create-order` 需 `takeWayCode` |
| 得来速 DT | 5 | 1 | 必传，来自 `query-nearby-stores` | `create-order` 需 `takeWayCode` |
| 麦乐送 | 2 | 2 | 必传，来自 `delivery-query-stores` | `addressId` |
| 企业团餐 | 6 | 2 | 必传，来自 `delivery-query-stores` | `gmServiceCode` |

补充说明：

- `query-meal-detail` 的说明中强调「到店自提场景 `beCode` 是无效参数，不要传，传了会报错」。
- `reservationDate` 为预约场景必填，非预约不传，格式 `yyyy-MM-dd HH:mm`。
- `takeWayCode` 取自 `calculate-price` 返回的 `data.takeWayList[].code`，仅 `orderType=1` 时传给 `create-order`。

---

## 3. 下单相关字段

### 3.1 `items[]`

| 字段 | 说明 |
|---|---|
| `productCode` | 商品编码，必填 |
| `quantity` | 数量，必填，≥1 |
| `couponId` / `couponCode` | 使用的优惠券，选填 |
| `modification.values[]` | 特制项：`code`、`key`、`quantity` |
| `roundList` | 套餐子项，含 `round` 与 `comboItemList` |

### 3.2 特制 `modification` 的 key 规则（易错）

- 用户**选中**的特调项：`key` = `query-meal-detail` 返回的 `selectedKey`
- 用户**未选中**的特调项：若该项 `unselectedKey` 不为空，`key` = `unselectedKey`，**也必须传入**
- 即：**对于包含 `unselectedKey` 的特调组，组内所有特调项都必须传入**

漏传会造成配置与预期不符，进而影响价格或出品。

### 3.3 订单级字段

| 字段 | 说明 | 本 Skill 的用法 |
|---|---|---|
| `remark` | 订单备注，最长 50 字，**仅 `orderType=2` 引导填写** | 承载「无接触配送」「放门口别敲门」等交付诉求 |
| `needTableware` | 是否需要餐具 | 承载餐具诉求 |
| `withOrder` | 随单购商品（`cardId` / `cardType` / `membershipCode` / `membershipSpecId`） | 可选，随单购有专属优惠 |
| `reservationDate` | 预约时间 | 提前备餐，减少到店等待与沟通 |

### 3.4 下单后的引导话术

`create-order` 的说明中给出的标准流程是：
引导用户「可以通过支付链接扫码或者打开麦当劳 App 完成支付，支付完成后请回复『支付完成』或『支付失败』」，随后查询最新订单状态。

---

## 4. 金额单位

`calculate-price` 与订单相关返回中的价格字段**单位为「分」**，展示时必须除以 100 转为「元」。

示例：返回 `3350` → 展示为 `¥33.50`。

---

## 5. 典型调用顺序

### 到店自取

```
now-time-info → query-nearby-stores → query-meals → query-meal-detail
→ [券池: query-my-coupons / query-store-coupons / available-coupons]
→ calculate-price（逐券试算，beType=1, orderType=1）
→ create-order（takeWayCode, needTableware, items）
→ 支付 → query-order
```

### 麦乐送

```
now-time-info → delivery-query-addresses → delivery-query-stores
→ query-meals → query-meal-detail
→ [券池三路]
→ calculate-price（逐券试算，beType=2, orderType=2, beCode）
→ create-order（addressId, remark, items）
→ 支付 → query-order
```

---

## 6. 错误码

| code | 原因 | 处理 |
|---|---|---|
| 401 | Token 无效、已过期或未提供 | 检查 `Authorization` 是否为 `Bearer <token>` |
| 429 | 超过 600 次/分钟限流 | 降低请求频率，串行化试算调用 |
