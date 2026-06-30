# 智能电子元器件料盒系统 — 演示 PPT 内容文档

> **用途**：将本文档逐页复制到 PowerPoint / WPS / Keynote，或交给 AI 幻灯片工具生成正式 PPT。  
> **版本**：smart_ee_inventory v0.1.0 · 2026-06-30（含实测测试数据）  
> **建议时长**：18～22 分钟（含 5～8 分钟现场演示 + 2 分钟质量保障）  
> **演示环境**：Windows PC + YZ-M40 RFID 模块（或 TCP 模拟器无硬件模式）

---

## 使用说明

| 标记 | 含义 |
|------|------|
| **【幻灯片】** | 投屏页标题与要点 |
| **【讲稿】** | 演讲者口述参考（可不投屏） |
| **【演示】** | 切换到浏览器 / 硬件操作 |
| **【配图建议】** | 建议插入的截图或示意图 |

每页建议布局：**标题 + 3～5 条要点**；架构/流程页可用全幅图。

---

## 第 1 页 · 封面

**【幻灯片】**

**智能电子元器件料盒系统**  
Smart EE Inventory

- RFID 驱动的料盒与库存管理
- 单机部署 · 纯 Python · 开箱即用
- 演示日期：____年__月__日
- 汇报人：________

**【讲稿】**  
今天介绍一套面向实验室与小型电子工坊的智能料盒系统：用 UHF RFID 标签识别元件与工具，在 PC 端完成入库、出库、借还与 BOM 取料分析，无需云端、无需复杂部署。

**【配图建议】** 料盒 + RFID 标签 + 笔记本界面合成图；或项目 Logo。

---

## 第 2 页 · 痛点与目标

**【幻灯片】**

**我们解决什么问题？**

| 传统方式 | 本系统 |
|----------|--------|
| 手工台账，易漏记 | RFID 自动感知 + 操作留痕 |
| 找料靠记忆/Excel | 货柜格位可视化 + BOM 定位 |
| 借还工具无追溯 | 使用人 / 项目 / 消耗可登记 |
| 多系统拼凑 | **一个进程**：硬件 + API + UI |

**目标**：让「贴标签 → 放格位 → 拿取/归还 → 查库存」形成闭环。

**【讲稿】**  
电子实验室常见问题是：电阻电容数量多、规格杂，开发板和工具又需要单独借还。我们希望在工位旁放一块读卡区，标签一靠近就能联动软件，减少手工录入。

---

## 第 3 页 · 系统概览（一句话）

**【幻灯片】**

**系统一句话**

> USB 连接的 **YZ-M40 UHF RFID 模块** → Python 串口网关 → **FastAPI** 后端 → **NiceGUI**  Web 界面 → **SQLite** 本地数据库

**核心价值**

1. **实时读卡**：标签进入/离开读卡区，毫秒级推送  
2. **双类型库存**：料盒格位物料 + 非标物件（工具/开发板）  
3. **待确认业务**：出库/入库需填写使用人、项目或消耗，避免误扣库存  
4. **BOM 分析**：导入 CSV，自动匹配库存并在货柜上高亮格位  

**【配图建议】** 横向四层架构条（硬件 → 网关 → 后端 → 前端）。

---

## 第 4 页 · 技术架构

**【幻灯片】**

**技术栈**

| 层级 | 技术 | 职责 |
|------|------|------|
| 硬件 | YZ-M40 + UHF 标签 | 近场识别 EPC |
| 通信 | pyserial | USB 串口、二进制帧解析 |
| 后端 | FastAPI + Uvicorn | REST API、WebSocket、业务逻辑 |
| 数据库 | SQLite + SQLAlchemy 异步 | 12 张业务表，单文件部署 |
| 前端 | NiceGUI | 仪表盘、库存、BOM 等 8 个页面 |
| 配置 | `.env` | 串口、看门狗、端口等 |

**架构示意**

```
YZ-M40 ──USB/Serial──► gateway/ ──EventBus──► backend/ ──► SQLite
                              ▲                    │
                              └──── NiceGUI frontend/
```

**【讲稿】**  
全部跑在一台 Windows 电脑上，`python main.py` 即可启动。API 文档与 Web UI 同端口，适合实验室单机演示，也便于二次开发。

**【配图建议】** 使用 README 中的 ASCII 架构图或重绘为矢量图。

---

## 第 5 页 · 硬件与 RFID

**【幻灯片】**

**RFID 硬件（实测参数）**

| 项目 | 说明 |
|------|------|
| 模块 | YZ-M40 UHF 读写器 |
| 连接 | USB 虚拟串口（如 COM11） |
| 波特率 | 115200 · 8N1 |
| 协议 | 帧头 `RF`，通知码 0x80 上报 EPC + RSSI |
| 标签 | 每格/每件可贴独立 UHF 标签 |

**读卡流程**

1. 网关连接串口，可选自动发送 **0x21 开始盘存**  
2. 模块上报标签 TLV → 解析 EPC  
3. 查表绑定格位或非标物件 → 事件总线 → UI 弹窗 / 看门狗  

**【讲稿】**  
协议层已按厂商规格书 V1.4 实现，并兼容现场 28 字节短帧。无硬件时可用 TCP 模拟器对接，方便 CI 与培训演示。

---

## 第 6 页 · 数据模型

**【幻灯片】**

**12 张核心数据表**

| 域 | 表 | 说明 |
|----|-----|------|
| 物料 | `parts` / `part_categories` / `part_params` | 料号、封装、阻值/容值等 |
| 料盒 | `bin_cabinets` / `bin_slots` | 柜体 + 行列格位，可绑 EPC |
| 库存 | `inventory_items` / `inventory_transactions` | 格位数量、流水 |
| 业务 | **`inventory_operations`** | 出库/入库/登记，含待确认状态 |
| 非标 | **`assets`** | Jetson 等工具，独立借还 |
| BOM | `boms` / `bom_lines` | CSV 导入与分析 |
| RFID | `rfid_events` | 读卡原始日志 |

**演示种子数据 `BIN-TEST`**

| 格位 | 物料 | RFID |
|------|------|------|
| T01-1-1 | 测试电阻 10kΩ ×100 | 已绑定 |
| T01-1-2 | 陶瓷电容 100nF ×200 | 已绑定 |
| T01-1-3 | 红色 LED ×150 | 未绑标签（演示贴签） |
| — | Jetson Nano（非标） | 已绑定，不进格位 |

**【配图建议】** ER 简图或格位 1×3 示意图。

---

## 第 7 页 · 功能地图（Web 页面）

**【幻灯片】**

**八大功能页面**

| 路径 | 功能 |
|------|------|
| `/` | **仪表盘**：货柜网格、统计、操作日志、读卡弹窗 |
| `/bins` | 料盒 CRUD、柜级 EPC |
| `/slots` | 格位网格、编辑 EPC/标签 |
| `/inventory` | 库存与标签：编辑/删除、绑定/换绑/解绑 |
| `/inventory/register` | **入库绑定**：新标签登记到格位或非标 |
| `/inventory/bom` | **BOM 分析**：缺口表 + 货柜高亮 |
| `/inventory/operations` | 操作记录：筛选、确认、清空 |
| `/docs` | Swagger API（开发者） |

**访问地址**：`http://127.0.0.1:8765/`（端口占用时自动 fallback）

**【讲稿】**  
导航栏统一入口；仪表盘是日常操作主界面，库存与标签合并为单页，减少跳转。

---

## 第 8 页 · 核心亮点 ① 看门狗出入库

**【幻灯片】**

**单天线「在场看门狗」（仅格位物料）**

```
标签离开读卡区 ──► 待出库确认 ──► 库存 -1，格位「已出库」
标签回到读卡区 ──► 待入库确认 ──► 库存 +1 - 消耗数量
未登记标签     ──► 引导跳转「入库绑定」页
```

**防误触设计**

- 进入/离开需连续多次检测（去抖）  
- 网关启动后 5 秒 bootstrap，避免误报离开  
- **必须弹窗确认**并填写使用人、使用项目（或消耗）  

**料盒状态示例**：正常 · 出库未登记 · 已出库 · 未登记归还

**【配图建议】** 标签拿离/放回 + 弹窗截图（出库确认、归还确认）。

**【讲稿】**  
这不是「一读卡就扣库存」，而是「感知物理在场变化 + 人工确认」，更贴近真实实验室管理。

---

## 第 9 页 · 核心亮点 ② 双类型库存

**【幻灯片】**

**两类资产，两种流程**

| 类型 | 存放 | RFID 行为 |
|------|------|-----------|
| **料盒物料** | 格位（BIN-TEST 等） | 看门狗自动待确认出库/入库 |
| **非标物件** | 独立登记（如开发板） | 仪表盘读卡 → **借出/归还**弹窗 |

**非标示例**：`AST-0001` Jetson Nano 开发板  
- 在库 → 读卡弹出借出（使用人、项目）  
- 已借出 → 读卡弹出归还  

**统一入库 API**：`POST /inventory/register`，`bind_type` = `slot_material` | `asset`

**【演示预告】** 接下来现场演示：电阻出库 → 归还 → Jetson 借还。

---

## 第 10 页 · 核心亮点 ③ BOM 取料分析

**【幻灯片】**

**BOM 能做什么？**

1. 上传 CSV（料号 + 用量 + 位号）  
2. 按套数预览：**库存够 / 缺口 / 未知料号**  
3. 保存 BOM 后，在货柜视图 **蓝色高亮** 相关格位  
4. 导出分析结果，指导现场取料  

**演示 CSV `DEMO-BOM-001`**

| 料号 | 用量 | 位号 |
|------|------|------|
| TEST-R-10K | 10 | R1;R2;R3 |
| TEST-C-100N | 5 | C1;C2 |
| TEST-LED-RED | 3 | D1;D2;D3 |

**当前限制**：仅分析与定位，**不自动扣库存**（路线图 P2）。

**【配图建议】** `/inventory/bom` 缺口表 + 货柜高亮截图。

---

## 第 11 页 · 标签与库存管理

**【幻灯片】**

**`/inventory` 一页搞定**

**统计区**：物料种类、总库存、低库存预警  

**料盒物料 / 非标物件**  
- 折叠列表、分页、低库存筛选  
- 行内 **编辑** 数量/阈值 · **删除** 记录  

**标签管理（表格）**  
- **绑定**：库存尚无 EPC 时贴新签  
- **换绑**：更换物理标签  
- **解绑**：清除 EPC，保留数量  
- 所有手动修改写入 `inventory_operations`（`manual_edit`）  

**【讲稿】**  
T01-1-3 红色 LED 格位故意未绑标签，可用于演示「现场贴签 + 绑定」。

---

## 第 12 页 · 操作记录与追溯

**【幻灯片】**

**全程可追溯**

| 字段 | 说明 |
|------|------|
| 操作类型 | 出库 / 入库 / 登记 / 手动编辑 |
| 状态 | 待确认 / 已确认 / 已取消 |
| 使用人 & 项目 | 看门狗与借还必填 |
| 消耗数量 | 归还时可扣减（如用掉 2 颗电阻） |
| 关联 | 格位、料号、EPC、时间戳 |

**管理页** `/inventory/operations`  
- 按状态/类型筛选  
- 点击待确认行补录确认  
- 支持清空（演示环境重置用）  

**【配图建议】** 操作记录列表截图。

---

## 第 13 页 · 质量保障与自动化测试

**【幻灯片】**

**测试体系概览**

| 层级 | 工具 | 覆盖 |
|------|------|------|
| 冒烟门禁 | `scripts/smoke_test.py` | 网关协议 + EPC + 种子 + 标签 + 编辑 API |
| 全量回归 | `pytest tests/`（**78** 用例） | API / 服务 / 网关 / 前端 hub / 配置 |
| 演示数据 | `scripts/verify_seed.py` | BIN-TEST 三格 + 三枚 EPC 绑定 |
| 无硬件联调 | `simulate_rfid_board.py` | TCP 模拟 YZ-M40，与主程序同跑 |

**本次实测数据（2026-06-30，本机 Windows）**

| 命令 | 结果 | 耗时 |
|------|------|------|
| `python scripts/smoke_test.py` | **35 passed** | **~1 s** |
| 鲁棒性专项（网关+看门狗+EPC+操作确认） | **30 passed** | **0.37 s** |
| `python scripts/verify_seed.py` | **全部通过** | BIN-TEST 1×3 · 2 格有 EPC · 1 格无 EPC · Jetson 非标 |
| `pytest tests -q`（全量） | **71 passed · 7 skipped** | ~5 s |

> 全量套件中 7 条 API 测试在无种子时会 `skip`；冒烟子集为**演示/发布推荐门禁**。

**测试分布（78 用例）**

| 目录 | 数量 | 代表场景 |
|------|------|----------|
| `test_gateway/` | 14 | 帧校验和、粘包/半包、坏帧拒绝、模拟器 |
| `test_services/` | 35 | 看门狗、待确认出入库、BOM、EPC 冲突、标签生命周期 |
| `test_api/` | 18 | 入库、借还、BOM 导入拒绝未知料号 |
| `test_frontend/` | **9** | **全页 RFID hub** EventBus 路由与回调 |
| `test_config/` | 2 | 端口占用自动 fallback |

**【讲稿】**  
开发过程中关键路径都有自动化测试托底：协议层不依赖数据库，毫秒级跑完；业务层用内存 SQLite，不污染 `./data/inventory.db`。演示前可现场执行 `python scripts/smoke_test.py`，约 1 秒内绿灯，向听众展示「可重复验证」。

**【演示 · 可选 30 秒】** 终端运行：

```powershell
python scripts/smoke_test.py
python scripts/verify_seed.py
```

**【配图建议】** 终端绿色 `Smoke tests passed.` + verify_seed `全部通过` 截图。

---

## 第 14 页 · 鲁棒性设计

**【幻灯片】**

**我们在哪些环节做了「防呆 / 防误触」？**

**① RFID 通信层**

| 机制 | 说明 | 测试覆盖 |
|------|------|----------|
| `FrameBuffer` 粘包/半包 | 串口分片到达仍能组帧 | `test_frame_buffer_partial_reads` |
| 帧头前垃圾字节 | 自动跳过无效数据再找 `RF` | `test_frame_buffer_skips_garbage_before_header` |
| 校验和错误 | 整帧丢弃，不解析脏 EPC | `test_decode_frame_rejects_bad_checksum` |
| 非阻塞读 | `read_available()` 避免空读阻塞 200ms | 生产代码 + 模拟器 |
| 短帧兼容 | 28 字节通知帧（无 Time TLV） | `test_parse_tag_upload_notification` |

**② 在场看门狗（PresenceWatchdog）**

| 参数 | 默认 | 作用 |
|------|------|------|
| `appear_count` | 2 | 连续读到才认定「进入」 |
| `disappear_count` | 6 | 连续未读才认定「离开」 |
| `miss_grace_ms` | 1200 | 宽限期内不判离开，减少静止误报 |
| `bootstrap_ms` | 5000 | 启动后静默，不触发离开/入库 |

自动化用例验证：**bootstrap 抑制误报** · **宽限+连续 miss 才 disappear** · **间歇读卡重置 miss 计数**。

**③ 业务与数据**

| 场景 | 行为 |
|------|------|
| 出库/入库 | **待确认弹窗**（**任意带顶栏页面**），须填使用人/项目；取消可回滚 pending |
| 重复 EPC | 入库/绑标签返回 **409**，禁止一格多签 |
| 未知 BOM 料号 | 导入 **422 拒绝**；预览标 `missing_part` |
| 非标物件 | 看门狗**忽略**，仅手动读卡借还 |
| 端口被占 | `resolve_listen_port` 自动 fallback 8090/8888 等 |
| 旧数据库 | 启动时 `migrate.py` 补列，无需 Alembic |

**【讲稿】**  
鲁棒性不是单点优化，而是「通信可靠 → 感知去抖 → 人工确认 → 数据约束」四层叠加。实验室环境里标签短暂遮挡、串口噪声、误触拿放都很常见；系统默认保守，宁可多一步确认，也不 silent 改库存。

**【配图建议】** 看门狗参数 `.env` 片段 + 出库确认弹窗并列。

---

## 第 15 页 · 现场演示脚本（总览）

**【幻灯片】**

**演示流程（约 6 分钟）**

| 步骤 | 页面 | 动作 |
|------|------|------|
| 0 | — | 启动 `python main.py`，打开 `/` |
| 1 | 仪表盘 | 选择 `BIN-TEST`，展示 1×3 格位与搜索 |
| 2 | 硬件 | **拿离**电阻标签 → 出库确认 → 库存 100→99 |
| 3 | 硬件 | **放回**标签 → 归还确认（消耗 0）→ 恢复 100 |
| 4 | 硬件 | 靠近 **Jetson** 标签 → 借出 → 再读卡归还 |
| 5 | `/inventory/bom` | 导入 `demo_bom.csv`，高亮格位 |
| 6 | `/inventory/register` | 未登记标签 → 弹窗跳转，完成入库绑定 |
| 7 | `/inventory/operations` | 展示完整操作链 |

**无硬件备选**：终端运行 `simulate_rfid_board.py`，`.env` 设 `RFID_SERIAL_PORT=socket://127.0.0.1:9276`

**【演示】** 从此页起切换全屏浏览器 + 可选第二屏显示 PPT 要点。

---

## 第 16 页 · 演示步骤详解（讲稿页，可选不投屏）

**【讲稿 · 步骤 0 准备**

```powershell
python scripts/init_db.py      # 含 BIN-TEST 种子
python main.py                 # DEBUG=false 接硬件时
# 浏览器 http://127.0.0.1:8765/
```

**【讲稿 · 步骤 2 出库**

1. 仪表盘左栏选料盒 `BIN-TEST`  
2. 将 T01-1-1 电阻标签移出读卡区  
3. 等待 1～2 秒，弹出「出库确认」  
4. 填写：使用人「张三」、项目「Demo 板卡」→ 确认  
5. 指出：格位变「已出库」，右侧操作日志新增记录，数量 -1  

**【讲稿 · 步骤 3 归还**

1. 将同一标签放回读卡区  
2. 弹出「入库归还」，消耗填 0 → 确认  
3. 格位恢复「在库」，数量恢复  

**【讲稿 · 步骤 4 非标**

1. 读取 Jetson 标签（EPC …59E）  
2. 在库 → 借出对话框 → 确认  
3. 左栏非标列表状态变为已借出；再次读卡 → 归还  

**【讲稿 · 步骤 5 BOM**

1. 打开 `/inventory/bom`  
2. 选择 `scripts/demo_bom.csv` 预览或导入  
3. 套数设为 1，展示三行物料均「充足」  
4. 选择 `BIN-TEST`，格位 R1/C1/C2 蓝色高亮  

**【讲稿 · 步骤 6 新标签入库**

1. 模拟器 `emit` 未绑定 EPC，或贴新标签  
2. 仪表盘提示「未登记」→ 跳转 `/inventory/register?epc=...`  
3. 选料盒、格位 T01-1-3、物料「红色 LED」→ 确认绑定  

---

## 第 17 页 · 开发与扩展

**【幻灯片】**

**开放能力**

- **REST API** 完整 CRUD + 入库/标签/BOM/操作确认  
- **WebSocket** `/ws/bin-status` 广播读卡与库存事件  
- **测试体系**：pytest **78** 用例 + 冒烟门禁（**35 例 / ~1s**）+ RFID 模拟器  
- **文档**：`README` · `TESTING.md` · `MEMO.md` · `PROJECT_SUMMARY.md`  

**路线图（节选）**

| 优先级 | 内容 | 状态 |
|--------|------|------|
| P2 | BOM 领料自动出库 | 规划中 |
| P2 | 通用手动出入库表单 | 规划中 |
| P3 | 用户认证、Docker 部署 | 规划中 |
| P4 | 64 路天线复用（多格位） | 设计稿已有 |

**【讲稿】**  
当前版本定位 **本地开发演示版**，架构已为多天线、WiFi 网关（ESP32 方案草案）留扩展空间。

---

## 第 18 页 · 部署与运维要点

**【幻灯片】**

**快速部署（3 步）**

```powershell
pip install -e ".[dev]"
Copy-Item .env.example .env    # 配置 COM 口
python scripts/init_db.py && python main.py
```

**运维提示**

| 场景 | 建议 |
|------|------|
| 接 RFID | `DEBUG=false`，避免热重载占串口 |
| COM 口冲突 | 测试脚本与主程序勿同时运行 |
| 端口占用 | 自动尝试 8090、8888 等 |
| 数据重置 | `init_db.py --drop` 重建 |
| 健康检查 | `python scripts/check_rfid_health.py` |
| 发布前自检 | `python scripts/smoke_test.py` + `verify_seed.py --strict` |

**【配图建议】** `.env` 关键项截图（RFID + 看门狗参数）。

---

## 第 19 页 · 总结

**【幻灯片】**

**我们交付了什么**

✅ YZ-M40 协议适配 + 低延迟读卡网关  
✅ 料盒/格位/库存/BOM 全链路 Web 管理  
✅ RFID 看门狗 + 待确认出入库（可追溯）  
✅ 非标物件借还 + 标签全生命周期管理  
✅ 单机 SQLite，零外部依赖启动  
✅ **78 项自动化测试** + 冒烟门禁 + 种子校验脚本  

**一句话总结**

> **贴标签、放格位、拿取确认、BOM 找料** —— 实验室元器件管理的数字化闭环。

**感谢聆听 · Q&A**

**【配图建议】** 仪表盘全页截图作为背景淡图。

---

## 第 20 页 · Q&A 备答（附录，可不投屏）

**【讲稿】**

**Q：没有 RFID 硬件能演示吗？**  
A：可以。运行 `scripts/simulate_rfid_board.py`，配置 `RFID_SERIAL_PORT=socket://127.0.0.1:9276`，用 `hold r10k` / `release all` 等命令模拟标签在场。

**Q：为什么出库要弹窗确认，不自动扣库存？**  
A：UHF 读卡存在误读、短暂离开等情况；待确认 + 使用人/项目登记符合实验室 accountability 需求。

**Q：多格位、多天线怎么办？**  
A：当前为单读卡区演示；`docs/RFID_MULTIPLEXER_WATCHDOG.md` 描述 64 路复用远期方案。

**Q：能否对接 MES/ERP？**  
A：REST API 已暴露主要能力，可在外部系统调用 register、operations、inventory 等接口集成。

**Q：数据安全与多用户？**  
A：v0.1 无登录鉴权，面向单机可信环境；多用户与权限在路线图 P3。

**Q：BOM 支持嵌套吗？**  
A：当前为扁平 CSV；复杂 BOM 需后续扩展。

**Q：如何保证演示环境数据正确？**  
A：演示前跑 `verify_seed.py`，校验 BIN-TEST 三格库存与 EPC；需要重置时 `init_db.py --drop`。

**Q：没有硬件怎么做回归测试？**  
A：`pytest tests/test_gateway` 纯协议；`board_simulator.py` + socket 串口联调 UI 与看门狗。

---

## 附录 A · 幻灯片清单（复制用）

| 序号 | 标题 | 类型 |
|------|------|------|
| 1 | 封面 |  intro |
| 2 | 痛点与目标 | 问题 |
| 3 | 系统概览 | 价值 |
| 4 | 技术架构 | 架构 |
| 5 | 硬件与 RFID | 技术 |
| 6 | 数据模型 | 数据 |
| 7 | 功能地图 | 产品 |
| 8 | 看门狗出入库 | 亮点 |
| 9 | 双类型库存 | 亮点 |
| 10 | BOM 取料分析 | 亮点 |
| 11 | 标签与库存管理 | 功能 |
| 12 | 操作记录与追溯 | 功能 |
| 13 | **质量保障与自动化测试** | 质量 |
| 14 | **鲁棒性设计** | 质量 |
| 15 | 现场演示脚本 | **演示** |
| 16 | 演示步骤详解 | 讲稿（可选） |
| 17 | 开发与扩展 | 路线 |
| 18 | 部署与运维 | 实施 |
| 19 | 总结 & Q&A | 结尾 |
| 20 | Q&A 备答 | 附录 |

**精简版（12 页）**：保留 1、2、3、4、8、9、10、**13、14**、15、18、19。

**质量侧重版（14 页）**：在精简版基础上加 12（操作追溯）+ 16（演示步骤）。

---

## 附录 B · 建议截图清单

演示前在本地截屏，插入对应幻灯片：

| 文件名建议 | 内容 | 对应页 |
|------------|------|--------|
| `demo_dashboard.png` | 仪表盘双栏 + BIN-TEST 格位 | 7、13 |
| `demo_checkout_dialog.png` | 出库确认弹窗 | 8 |
| `demo_return_dialog.png` | 入库归还弹窗 | 8 |
| `demo_asset_dialog.png` | 非标借还弹窗 | 9 |
| `demo_bom_highlight.png` | BOM 格位蓝色高亮 | 10 |
| `demo_inventory.png` | 库存与标签三区 | 11 |
| `demo_operations.png` | 操作记录列表 | 12 |
| `demo_register.png` | 入库绑定页 | 15 |
| `demo_smoke_test.png` | 终端 smoke_test + verify_seed 通过 | 13 |
| `demo_pytest_gateway.png` | `pytest tests/test_gateway -q` 全绿 | 13、14 |

截图命令：浏览器全屏 F11，`Win+Shift+S` 区域截图，建议宽度 ≥ 1920px。

---

## 附录 C · 演示前检查清单

- [ ] `python scripts/smoke_test.py` 通过（约 1 秒）  
- [ ] `python scripts/verify_seed.py` 全部通过  
- [ ] `python scripts/init_db.py` 已执行，种子数据正常  
- [ ] `.env` 中 `RFID_SERIAL_PORT` 正确，`DEBUG=false`  
- [ ] 主程序已启动，浏览器打开 `/` 无报错  
- [ ] 三枚演示标签（或模拟器 alias）可稳定读取  
- [ ] PPT 与浏览器分屏或双显示器就绪  
- [ ] 备用：无硬件时已验证 `simulate_rfid_board.py`  
- [ ] 演示后如需重置：`init_db.py --drop` 或清空 operations  

---

## 附录 D · 一页纸 Handout（可打印发放）

**智能电子元器件料盒系统 Smart EE Inventory**

- **定位**：RFID + 料盒 + 库存 + BOM 分析，单机 Python 部署  
- **硬件**：YZ-M40 UHF，USB 串口 115200  
- **启动**：`python main.py` → http://127.0.0.1:8765/  
- **演示料盒**：BIN-TEST（1×3 格位）  
- **核心流程**：标签离开/回到读卡区 → 确认出库/入库；非标读卡借还  
- **质量门禁**：冒烟 35 例 / ~1s · 全量 78 例 · verify_seed 校验演示库  
- **文档**：`docs/TESTING.md` · `docs/DEMO_PPT.md` · API `/docs`  
- **联系/仓库**：___________（按实际填写）

---

## 附录 E · 测试运行数据（实测，2026-06-30）

> 在 `D:\smart_ee_inventory`、Python 3.11.5、Windows 10 上执行。演示前可复跑并更新本表日期。

### E.1 冒烟门禁（推荐现场展示）

```powershell
python scripts/smoke_test.py
```

```
35 passed, 1 warning in ~1s
Smoke tests passed.
```

覆盖路径：`test_gateway/` · **`test_frontend/`** · `test_epc_binding` · `test_seed_data` · …

### E.2 鲁棒性专项子集

```powershell
python -m pytest tests/test_gateway tests/test_services/test_presence_watchdog.py tests/test_services/test_operation_confirm.py tests/test_services/test_epc_binding.py -q
```

```
30 passed, 1 warning in 0.37s
```

### E.3 演示库校验

```powershell
python scripts/verify_seed.py
```

| 检查项 | 结果 |
|--------|------|
| 料盒 BIN-TEST id=1 (1×3) | OK |
| T01-1-1 TEST-R-10K qty=100 EPC=…58E | OK |
| T01-1-2 TEST-C-100N qty=200 EPC=…3C7D | OK |
| T01-1-3 TEST-LED-RED qty=150 EPC=无 | OK |
| AST-0001 Jetson EPC=…59E | OK |

### E.4 全量回归

```powershell
python -m pytest tests -q
```

```
71 passed, 7 skipped, 2 warnings in ~5s
（78 collected；7 条 API 测试在无种子时 skip）
```

### E.5 关键鲁棒性用例 ↔ 代码映射

| 用例文件 | 验证的行为 |
|----------|------------|
| `test_frames.py` | 规格书命令帧、EPC 解析、坏校验和拒绝、粘包 |
| `test_board_simulator.py` | TCP 模拟器 hold/emit、盘存启停 |
| `test_presence_watchdog.py` | appear/disappear 去抖、bootstrap、宽限、间歇读 |
| `test_operation_confirm.py` | 待确认出库/入库、消耗、取消、出库未登记 reconciliation |
| `test_epc_binding.py` | EPC→格位/非标/料盒、冲突检测 |
| `test_bom.py` | 空 CSV 拒绝、未知料号 preview/import |
| `test_inventory_register.py` | 重复 EPC 409 |
| `test_global_inventory_events.py` | 全页 hub：TAG_READ / PRESENCE 路由、回调 keyed 注册 |
| `test_network.py` | 端口占用 fallback |

### E.6 演示时可口述的一行话

> 「核心链路有 **35 项冒烟测试约 1 秒跑完**，全页 RFID hub 另有 **9 项用例**；演示库 `verify_seed` 保证 BIN-TEST 与三枚标签绑定一致。」

---

*文档维护：功能或测试变更时请同步更新第 13、14 页与附录 E。*
