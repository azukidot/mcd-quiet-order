# 第三方资源说明

本项目在设计与实现过程中参考了以下开源作品。所有被参考的内容均已遵守其许可条款。

---

## mcd-saver-strategist

- **仓库**：https://github.com/hujjun/mcd-saver-strategist
- **许可**：MIT License
- **版权**：Copyright (c) 2026 mcd-saver-strategist contributors
- **参考内容**：优惠券组合的**架构思路**——将优惠券归一化为若干类型（单品改价 / 折扣 / 满减 / 组合价 / 赠品），在本地穷举菜篮与券的组合，再交由 MCP 接口核价，从而规避接口限流并保证金额准确。
- **使用方式**：**仅参考架构思路，代码为独立重写**。本项目的 `scripts/best_coupon_calc.py` 未复制其源代码，在数据结构（金额统一使用整数「分」）、互斥规则、搜索流程与输出契约上均为独立实现。

### MIT License 全文

```
MIT License

Copyright (c) 2026 mcd-saver-strategist contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## 麦当劳中国 MCP Server

- **仓库**：https://github.com/M-China/mcd-mcp-server
- **用途**：本项目的数据能力来源，按官方《使用条款》与《麦当劳 MCP 服务规则》使用。
- 本项目不复制该仓库的任何代码；公开平台地址 `https://mcp.mcd.cn` 为官方提供。

---

## 其他

本项目的 `scripts/sample_data/` 中的菜单与优惠券数据为**自行编写的示例数据**，仅用于本地演示与测试，不代表任何真实门店的在售商品与优惠规则。
