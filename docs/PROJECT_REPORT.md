# 智能电子元器件料盒系统项目报告

**项目名称**：Smart EE Inventory（智能电子元器件料盒系统）  
**版本**：v0.1.0  
**完成日期**：2026 年 6 月  
**技术栈**：Python 3.11 · YZ-M40 UHF RFID · FastAPI · NiceGUI · SQLite  

---

## 摘要

本项目面向电子实验室与小型电子工坊场景，设计并实现了一套基于 UHF RFID 的元器件与工具库存管理系统。系统以 USB 连接的 YZ-M40 读写器模块为感知入口，通过 Python 串口网关解析厂商二进制协议，将标签 EPC 与料盒格位、非标资产绑定，在 PC 端提供入库登记、在场看门狗出入库、非标借还、BOM 取料分析等能力。软件采用 FastAPI + NiceGUI 同进程部署，SQLite 本地持久化，单机即可运行，无需云端依赖。项目已完成 12 张数据表建模、8 个 Web 功能页面、**78 项**自动化测试及无硬件 TCP 模拟器，可作为实验室数字化管理的原型与二次开发基础。

**关键词**：RFID；料盒管理；库存追溯；FastAPI；在场检测；BOM 分析

---

## 一、项目背景与意义

### 1.1 项目背景

电子设计与维修工作中，电阻、电容、IC 等元器件规格繁多、体积极小，传统抽屉式存放或 Excel 台账难以满足「快速找料、准确记帐、借还可追溯」的需求。与此同时，开发板、示波器探头、编程器等**非标资产**往往价值较高、流动频繁，若缺乏登记机制，容易出现「借出无记录、归还对不上」的管理盲区。

近年来，UHF RFID 标签成本持续下降，配合小型读写器模块，可在工位旁以较低成本实现「贴标即识别」。YZ-M40 等模块通过 USB 虚拟串口与 PC 通信，适合与 Python 生态结合，构建**轻量级、可本地部署**的管理软件，而无需引入大型 WMS 或 MES 系统。

### 1.2 项目意义

**实践意义**

- 将物理拿取动作与系统库存联动，减少手工录入错误；
- 通过「待确认出入库」机制，在自动化与人工审核之间取得平衡，适应实验室误读、短暂遮挡等现实干扰；
- 支持 BOM 导入与格位高亮，缩短装配前的备料时间；
- 单机部署降低使用门槛，适合课程设计、创客空间、小型 lab 快速落地。

**技术意义**

- 完整走通「硬件协议 → 异步网关 → 事件总线 → REST/Web UI」链路，为后续扩展多天线、WiFi 网关（ESP32）预留架构；
- 采用 SQLAlchemy 2.x 异步 ORM 与 NiceGUI 同进程集成方案，探索 Python 全栈单机应用的一种可行范式；
- 建立可重复的测试与种子数据体系，保证演示与回归验证的一致性。

### 1.3 需求分析

#### 1.3.1 功能性需求

| 编号 | 需求描述 | 优先级 |
|------|----------|--------|
| F1 | 读取 UHF RFID 标签 EPC，实时推送至 Web 界面 | 高 |
| F2 | 管理料盒/柜体及行列格位，支持格位级 EPC 绑定 | 高 |
| F3 | 维护物料主数据（料号、封装、规格等）与格位库存数量 | 高 |
| F4 | 新标签入库绑定：选择料盒、格位、物料，写入库存与 EPC | 高 |
| F5 | 标签离开/回到读卡区时，触发待确认出库/入库流程 | 高 |
| F6 | 登记非标物件（工具/开发板），读卡借出/归还 | 中 |
| F7 | 标签绑定、换绑、解绑及库存删除 | 中 |
| F8 | BOM CSV 导入/预览，库存缺口分析与货柜格位定位 | 中 |
| F9 | 操作记录查询、待确认处理、审计追溯 | 中 |
| F10 | 提供 REST API 与 Swagger 文档，便于集成 | 低 |

#### 1.3.2 非功能性需求

| 编号 | 需求描述 | 指标/策略 |
|------|----------|-----------|
| NF1 | 单机部署 | 单进程启动，SQLite 文件库，无外部服务依赖 |
| NF2 | 读卡实时性 | 网关 20ms 级轮询；有标签时连续读；EventBus 进程内推送 |
| NF3 | 鲁棒性 | 串口粘包/半包处理；看门狗去抖与 bootstrap；重复 EPC 409 拒绝 |
| NF4 | 可测试性 | pytest 自动化；内存库隔离；TCP 模拟器无硬件调试 |
| NF5 | 可维护性 | 分层目录（gateway/backend/frontend）；`.env` 配置；开发文档 |
| NF6 | 易用性 | 中文 Web UI；仪表盘一站式操作；低库存筛选 |

#### 1.3.3 约束与假设

- 当前为**单读卡区**演示，一个时刻主要感知读卡台附近标签；
- 格位物料与读卡区物理位置需人工保证（标签随元件置于读卡区）；
- Windows 环境下 USB 串口**单进程独占**；
- v0.1 不含用户认证与多租户，面向可信单机环境。

### 1.4 项目内容

本项目主要完成以下工作：

1. **硬件接入层**：依据 YZ-M40 规格书 V1.4 实现帧编解码、TLV 解析、盘存命令及串口网关服务；
2. **数据层**：设计 12 张 SQLite 表，覆盖物料、料盒、格位、库存、操作记录、BOM、RFID 事件等；
3. **业务层**：入库绑定、EPC 解析、在场看门狗、待确认出入库、非标借还、BOM 分析、标签生命周期管理；
4. **表现层**：NiceGUI 八页（仪表盘、料盒、格位、库存与标签、入库绑定、BOM、操作记录等）；
5. **工程化**：初始化/种子脚本、串口测试 CLI、TCP 模拟器、冒烟测试、pytest 套件及项目文档。

---

## 二、项目相关概念与技术

### 2.1 核心概念

#### 2.1.1 UHF RFID 与 EPC

**射频识别（RFID）** 通过无线电场读写标签数据。本项目采用 **UHF（超高频）** 被动标签，典型存储内容为 **EPC（Electronic Product Code，电子产品代码）**——一串十六进制唯一标识，相当于物品的「数字身份证」。读写器模块（YZ-M40）在盘存过程中上报 EPC 及 **RSSI（接收信号强度）**，用于感知标签是否在场。

#### 2.1.2 料盒、格位与库存

- **料盒（Bin Cabinet）**：物理柜体或料盒，用行列层定义格位拓扑，可有柜级 RFID；
- **格位（Bin Slot）**：最小存储单元，如 `T01-1-1` 表示第 1 行第 1 列第 1 层；
- **库存项（Inventory Item）**：某格位上某物料的数量、最小库存、批次、状态及绑定的 EPC；
- **非标物件（Asset）**：不占用格位的独立资产（如 Jetson 开发板），单独绑 EPC 与借还状态。

#### 2.1.3 在场看门狗（Presence Watchdog）

区别于「每读一次卡就触发业务」，看门狗维护标签的**在场状态机**：连续多次读到判定「进入」，连续多次未读到（超过宽限时间）判定「离开」。离开触发待出库，回到触发待入库，且须用户弹窗确认后才改库存，以避免误触发。

#### 2.1.4 BOM 与取料分析

**BOM（Bill of Materials，物料清单）** 描述产品装配所需元件及用量。本系统支持 CSV 导入 BOM，按料号匹配本地 `parts` 与 `inventory_items`，计算库存是否满足指定套数，并在货柜网格上**高亮**相关格位，辅助人工取料（当前不自动扣库存）。

### 2.2 相关技术

| 技术 | 在本项目中的作用 |
|------|------------------|
| **Python 3.11** | 全栈开发语言，asyncio 并发 |
| **pyserial** | USB 串口读写，支持 `socket://` 模拟串口 |
| **FastAPI** | REST API、WebSocket、OpenAPI 文档 |
| **Uvicorn** | ASGI 服务器，托管 API 与 NiceGUI |
| **NiceGUI** | 基于 Quasar 的 Python Web UI，与 FastAPI 同进程 |
| **SQLAlchemy 2.x + aiosqlite** | 异步 ORM，SQLite 持久化 |
| **Pydantic / pydantic-settings** | 请求校验与环境配置 |
| **httpx** | 前端 ApiClient 异步 HTTP |
| **pytest / pytest-asyncio** | 单元测试与 API 测试 |

### 2.3 技术选型说明

**为何选 SQLite 而非 PostgreSQL**  
目标场景为单机 lab，SQLite 零配置、单文件备份简单，与「轻量部署」一致。

**为何选 NiceGUI 而非 Vue/React 独立前端**  
减少前后端分离的部署复杂度；Python 团队可一体维护；WebSocket 与页面逻辑同进程，RFID 低延迟推送实现简单。

**为何采用异步架构**  
串口网关、数据库写入、HTTP 请求均为 I/O 密集；asyncio 可在单进程内并发处理读卡循环与 API，避免阻塞。

---

## 三、项目系统与功能设计

### 3.1 总体架构

系统采用**四层架构**，自底向上分别为硬件通信层、网关服务层、业务 API 层、Web 表现层。

```
┌─────────────┐     USB/Serial      ┌──────────────────┐
│ YZ-M40 模块  │ ──────────────────► │  gateway/        │
│  (UHF RFID) │   RF 帧 + TLV       │  protocol/       │
└─────────────┘                     │  rfid_reader     │
                                    └────────┬─────────┘
                                             │ EventBus (asyncio)
                                             ▼
┌─────────────┐   REST / WebSocket   ┌──────────────────┐
│  NiceGUI    │ ◄──────────────────► │  backend/        │
│  frontend/  │                      │  FastAPI + ORM   │
└─────────────┘                      └────────┬─────────┘
                                              │
                                              ▼
                                     ┌──────────────────┐
                                     │  SQLite (12 表)  │
                                     │  inventory.db    │
                                     └──────────────────┘
```

**目录结构**

| 目录 | 职责 |
|------|------|
| `gateway/` | 串口、YZ-M40 协议、GatewayService 轮询、board_simulator |
| `backend/` | FastAPI 路由、ORM 模型、业务服务、生命周期与看门狗 |
| `frontend/` | NiceGUI 页面、组件、ApiClient、事件监听 |
| `config/` | pydantic-settings、端口解析 |
| `scripts/` | 建库、种子、测试 CLI、模拟器 |
| `tests/` | pytest 自动化测试 |

### 3.2 数据模型设计

共 **12 张表**，主要实体关系如下：

| 域 | 表名 | 说明 |
|----|------|------|
| 物料 | `part_categories` | 分类树 |
| 物料 | `parts` | 物料主数据 |
| 物料 | `part_params` | EAV 扩展参数 |
| 料盒 | `bin_cabinets` | 柜体 |
| 料盒 | `bin_slots` | 格位，含 `rfid_tag_epc`、状态 |
| 库存 | `inventory_items` | 格位库存数量与阈值 |
| 库存 | `inventory_transactions` | 底层流水 |
| 库存 | `inventory_operations` | 业务操作（pending/confirmed） |
| 资产 | `assets` | 非标物件 |
| BOM | `boms` / `bom_lines` | BOM 头与明细 |
| RFID | `rfid_events` | 读卡日志 |

**格位状态**（节选）：`occupied`（在库）、`pending_checkout`（待出库）、`checked_out`（已出库）、`pending_return`（待入库）等。

**料盒状态**（节选）：`active`、`checkout_unregistered`（出库未登记）、`checked_out` 等。

### 3.3 功能模块设计

#### 3.3.1 Web 功能页面

| 路径 | 模块 | 主要功能 |
|------|------|----------|
| `/` | 仪表盘 | 货柜网格、统计、操作日志（弹窗由全页 hub 提供） |
| 任意带顶栏页 | 全局 RFID | 看门狗出库/入库确认、非标借还、未登记标签 → 入库绑定 |
| `/bins` | 料盒管理 | CRUD、柜级 EPC |
| `/slots` | 格位视图 | 网格展示、编辑 EPC/标签 |
| `/inventory` | 库存与标签 | 统计卡片、料盒物料/非标列表、标签 bind/rebind/unbind |
| `/inventory/register` | 入库绑定 | 料盒物料或非标登记、RFID 听卡、`?epc=` 预填 |
| `/inventory/bom` | BOM 分析 | CSV 预览/导入、缺口表、格位高亮 |
| `/inventory/operations` | 操作记录 | 筛选、待确认、清空 |
| `/docs` | API 文档 | Swagger UI |

#### 3.3.2 核心业务流程

**流程 A：格位物料看门狗出入库**

```
标签连续读到 → 在场看门狗判定 appear（bootstrap 结束后）
标签连续未读 → 判定 disappear → 创建 pending 出库操作
    → 前端弹窗（使用人、项目）→ confirm → 库存 -1，格位 checked_out
标签再次出现 → pending 入库 → 弹窗（消耗数量）→ confirm → 库存调整
```

**流程 B：非标物件借还**

```
读卡 → EPC 查 assets 表 → 在库则借出弹窗 → 已借出则归还弹窗
（不看门狗，不占用格位）
```

**流程 C：新标签入库**

```
未绑定 EPC 读卡 → 仪表盘引导 → /inventory/register?epc=...
→ 选 bind_type、料盒/格位/物料 → POST /inventory/register → 写库存 + EPC
```

**流程 D：BOM 取料分析**

```
上传 CSV → preview/import → 按料号汇总库存 → 选料盒 → 网格高亮匹配格位
```

### 3.4 接口设计（节选）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST/PATCH/DELETE | `/api/v1/bins` | 料盒 CRUD |
| GET/PATCH | `/api/v1/slots` | 格位查询与更新 |
| GET | `/api/v1/inventory` | 库存列表 |
| POST | `/api/v1/inventory/register` | 统一入库绑定 |
| GET/POST | `/api/v1/inventory/operations/...` | 操作记录与 confirm/cancel |
| POST | `/api/v1/inventory/manage/bind-tag` 等 | 标签管理 |
| POST | `/api/v1/assets/take-out` / `return` | 非标借还 |
| GET/POST | `/api/v1/boms/...` | BOM 预览/导入/分析 |
| WS | `/ws/bin-status` | 事件广播 |

详细定义见运行时的 `/docs` OpenAPI 文档。

---

## 四、项目关键技术与实现

### 4.1 YZ-M40 协议适配

依据《YZ-M40 读写器模块规格书 V1.4》，帧结构为：

```
'R''F' | FrameType | Address(2B) | FrameCode | ParamLen(2B) | Parameters(TLV...) | Checksum
```

**实现要点**（`gateway/protocol/frames.py`）：

- **校验和**：Header 至 Parameters 末字节求和，取反加一；
- **标签通知**：FrameType=`0x02`，FrameCode=`0x80`，TLV `0x50` 内含 EPC（`0x01`）与 RSSI（`0x05`）；
- **FrameBuffer**：处理串口粘包、半包及帧头前垃圾字节；
- **兼容性**：规格书 28 字节短帧（Tag TLV `0x11`，无 Time TLV）与现场 EPC 均已验证。

**命令层**（`gateway/protocol/commands.py`）：`0x21` 开始连续盘存、`0x23` 停止、`0x22` 单次盘存、`0x40` 查询版本。

### 4.2 串口网关与低延迟推送

`GatewayService`（`gateway/service.py`）在 asyncio 后台循环中：

1. 非阻塞 `read_available()` 批量读取（避免空读长时间阻塞）；
2. `FrameBuffer` 解析出 EPC 后，**先**经 `event_bus` 广播 `TAG_READ`，**再**异步入库 `rfid_events`；
3. 有标签时缩短 sleep，提高连续盘存吞吐。

`GlobalInventoryEventHub`（`navbar()` 挂载）经 `EventBusListener` 订阅进程内事件，**所有页面**均可弹出确认对话框；各页注册 keyed 刷新回调。入库/库存页另用 `rfid_listener` 听卡填 EPC。HTTP 轮询仅作仪表盘操作日志兜底。

### 4.3 在场看门狗实现

`PresenceWatchdog`（`backend/services/presence_watchdog.py`）核心参数：

| 参数 | 默认值 | 含义 |
|------|--------|------|
| `appear_count` | 2 | 连续读到次数才触发 appear |
| `disappear_count` | 6 | 连续 miss tick 才触发 disappear |
| `miss_grace_ms` | 1200 | 未读到标签的宽限时间 |
| `bootstrap_ms` | 5000 | 网关就绪后静默期，不判离开 |

`lifespan.py` 中定时 `tick`，触发 `create_presence_pending_action()`；**非标 asset 的 EPC 被忽略**，避免误走格位出库逻辑。

### 4.4 EPC 绑定与冲突检测

`epc_binding.lookup_epc_binding()` 统一查询 EPC 对应：

- 格位 `bin_slots.rfid_tag_epc`；
- 柜体 `bin_cabinets.rfid_tag_epc`；
- 非标 `assets.rfid_tag_epc`。

入库与绑标签时 `check_epc_available()` 防止同一 EPC 重复绑定，冲突返回 HTTP 409。

### 4.5 待确认操作与库存一致性

`inventory_operations` 表记录业务语义（`take_out` / `return` / `register_in` / `manual_edit`），`status` 为 `pending` 时仅改变格位/料盒展示状态，**用户 confirm 后**才更新 `inventory_items.quantity` 并写 `inventory_transactions`。取消 pending 不会自动恢复在库，须 RFID 再次确认入库——避免状态与物理不一致。

### 4.6 BOM 服务

`bom_service.py` 支持两种 CSV 格式（带 BOM 头或扁平料号列表），解析后：

1. 按 `part_number` 关联 `parts`；
2. 汇总各格位 `inventory_items` 数量；
3. 计算缺口（`kit_qty` 套数放大）；
4. 返回格位坐标供前端 `shelf_grid` 蓝色高亮。

未知料号在 import 时拒绝，preview 时标记 `missing_part`。

### 4.7 全页 RFID 事件 hub

`frontend/services/global_inventory_events.py` 在 `navbar()` 中按浏览器标签页单例挂载：

- `PRESENCE_CONFIRM_REQUIRED` → 出库/入库确认弹窗；
- `TAG_READ`（asset）→ 非标借还弹窗；
- 未绑定 EPC → 跳转入库绑定引导；
- 每 5s 轮询 pending 操作，防止漏弹窗；
- 页面通过 `on_confirmed("key", callback)` 注册局部刷新，切页时 `off_confirmed` 清理。

自动化测试见 `tests/test_frontend/test_global_inventory_events.py`。

### 4.8 前端工程实践

- **异步加载**：`@ui.page` 入口避免连续 `await` 多个 API，用 `ui.timer(0.05, load_fn, once=True)` 先渲染骨架；
- **防闪烁**：货柜区 `@ui.refreshable` + 数据 snapshot，避免 `clear()` 整页空白；
- **NiceGUI Select**：选项字典格式为 `{value: label}`，绑定值为 id，显示为元件名称。

### 4.9 无硬件调试能力

`gateway/board_simulator.py` + `scripts/simulate_rfid_board.py` 在 TCP 9276 端口模拟 YZ-M40 协议；`.env` 设置 `RFID_SERIAL_PORT=socket://127.0.0.1:9276` 即可与 `main.py` 联调，预设别名 `r10k` / `c100n` / `jetson` 对应种子 EPC。

---

## 五、项目部署与测试

### 5.1 部署环境

| 项目 | 要求 |
|------|------|
| 操作系统 | Windows 10/11（项目主要开发与实测环境） |
| Python | ≥ 3.11 |
| 硬件 | YZ-M40 USB 模块（可选，可用模拟器替代） |
| 浏览器 | Chrome / Edge 等现代浏览器 |

### 5.2 部署步骤

```powershell
# 1. 创建虚拟环境并安装
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 2. 配置环境变量
Copy-Item .env.example .env
# 编辑 RFID_SERIAL_PORT、RFID_ENABLED、DEBUG=false（接硬件时）

# 3. 初始化数据库
python scripts/init_db.py

# 4. 启动服务
python main.py
```

访问 `http://127.0.0.1:8765/`（端口占用时自动 fallback）。

**RFID 硬件部署要点**

1. `python scripts/test_rfid_serial.py list` 确认 COM 口（USB 设备，非蓝牙虚拟口）；
2. 测试脚本与主程序**不可同时占用**同一 COM 口；
3. 推荐 `RFID_AUTO_START_INVENTORY=true`，由网关发送 0x21 开始盘存；
4. 看门狗参数可在 `.env` 中按现场调整。

### 5.3 演示数据

`scripts/seed_data.py` 初始化后包含：

| 类型 | 内容 |
|------|------|
| 料盒 | `BIN-TEST`，1 行 × 3 列 |
| 物料 | 测试电阻 10kΩ、陶瓷电容 100nF、红色 LED |
| 格位 EPC | T01-1-1、T01-1-2 已绑定；T01-1-3 故意无 EPC（演示贴签） |
| 非标 | `AST-0001` Jetson Nano 开发板，独立 EPC |

校验命令：`python scripts/verify_seed.py`

### 5.4 测试方案

#### 5.4.1 测试分层

| 层级 | 工具 | 说明 |
|------|------|------|
| 单元/服务测试 | pytest + 内存 SQLite | 看门狗、BOM、EPC、操作确认等 |
| API 测试 | FastAPI TestClient | REST 端到端 |
| 协议测试 | 纯 bytes 断言 | 不依赖数据库 |
| 冒烟门禁 | `scripts/smoke_test.py` | 发布/演示前快速回归 |
| 集成调试 | 模拟器 + 浏览器 | 看门狗、借还、入库绑定人工走查 |

#### 5.4.2 实测结果（2026-06-30，本机 Windows）

| 命令 | 结果 | 耗时 |
|------|------|------|
| `python scripts/smoke_test.py` | **35 passed** | **~1 s** |
| 鲁棒性专项（gateway + 看门狗 + EPC + 操作确认） | **30 passed** | **~0.4 s** |
| `python scripts/verify_seed.py` | **全部通过** | BIN-TEST 与 EPC 绑定一致 |
| `python -m pytest tests -q` | **71 passed, 7 skipped** | **~5 s**（共 **78** 用例） |

7 条 skip 为 API 测试在无种子数据时的预期跳过；冒烟 **35** 例为演示推荐门禁。

#### 5.4.3 鲁棒性测试覆盖（节选）

| 测试文件 | 验证行为 |
|----------|----------|
| `test_frames.py` | 校验和、粘包/半包、坏帧拒绝 |
| `test_presence_watchdog.py` | 去抖、bootstrap、宽限、间歇读重置 |
| `test_operation_confirm.py` | 待确认出库/入库、消耗、取消 |
| `test_epc_binding.py` | EPC 冲突、未知 EPC |
| `test_bom.py` | 空 CSV 拒绝、未知料号 |
| `test_board_simulator.py` | TCP 模拟 hold/emit |
| `test_global_inventory_events.py` | 全页 hub EventBus 路由、回调注册 |

#### 5.4.4 现场演示测试脚本（约 5 分钟）

1. 打开 `/inventory` 或仪表盘，选择 `BIN-TEST`（若在仪表盘），展示格位；
2. 拿离电阻标签 → 出库确认 → 库存减 1；
3. 放回标签 → 归还确认 → 库存恢复；
4. Jetson 标签 → 借出 → 再读卡归还；
5. `/inventory/bom` 导入 `demo_bom.csv`，格位高亮；
6. `/inventory/operations` 查看操作链。

### 5.5 已知限制与后续改进

| 项目 | 说明 |
|------|------|
| 单读卡区 | 多格位并行感知需 64 路天线方案（设计稿已有） |
| 无用户认证 | 面向单机可信环境 |
| BOM 不自动出库 | 当前仅分析与定位 |
| 全量测试隔离 | 已修复 `test_seed_data` 对累计数据的脆弱断言；API 测试顺序仍建议独立 session |
| 无 Alembic | 大版本 schema 变更需 `--drop` 重建或 `migrate.py` 补列 |

---

## 六、参考文献

1. YZ-M40 读写器模块规格书 V1.4（202406）. 项目根目录：`YZ-M40读写器模块规格书V1.4-202406(1).pdf`.

2. EPCglobal. *EPC Radio-Frequency Identity Protocols Class-1 Generation-2 UHF RFID Protocol for Communications at 860 MHz–960 MHz Version 2.0*. GS1, 2013.（UHF 标签 EPC 编码通用背景）

3. FastAPI Documentation. https://fastapi.tiangolo.com/ .（Web API 框架）

4. NiceGUI Documentation. https://nicegui.io/ .（Python Web UI 框架）

5. SQLAlchemy 2.0 Documentation. https://docs.sqlalchemy.org/ .（异步 ORM）

6. pyserial Documentation. https://pythonhosted.org/pyserial/ .（串口通信）

7. Quasar Framework — QSelect Component. https://quasar.dev/vue-components/select .（前端下拉组件行为参考）

8. 项目内部文档：
   - `README.md` — 快速开始与 API 索引；
   - `docs/MEMO.md` — 硬件实测、踩坑与开发备忘录；
   - `docs/TESTING.md` — 测试与调试指南；
   - `docs/PROJECT_SUMMARY.md` — 能力清单与路线图；
   - `docs/RFID_MULTIPLEXER_WATCHDOG.md` — 看门狗与多天线扩展设计；
   - `docs/ESP32_WIFI_RFID.md` — WiFi 读卡网关可行性分析。

---

## 七、总结与感悟

### 7.1 项目总结

本项目从实验室真实需求出发，完成了「RFID 硬件 → 协议网关 → 业务后端 → Web 前端 → 本地数据库」的完整闭环。相比传统 Excel 或纯手工台账，系统在读卡实时性、格位可视化、出入库待确认追溯、BOM 取料辅助等方面提供了可落地的软件能力。v0.1 版本已具备料盒与格位管理、双类型库存、标签全生命周期、看门狗出入库、非标借还、BOM 分析及 **78 项**自动化测试，可作为课程设计、毕设原型或小型 lab 数字化管理的起点。

### 7.2 技术收获

1. **协议层与业务层分离**：二进制 RFID 帧解析独立于 FastAPI，通过 EventBus 解耦，便于模拟器替换真实硬件；
2. **自动化与人工确认的平衡**：看门狗解决「感知」，弹窗确认解决「责任」，比单纯自动扣库存更符合实验室管理习惯；
3. **异步 Python 全栈**：SQLAlchemy async + asyncio 网关 + NiceGUI 同进程，在单机场景下结构清晰、部署简单；
4. **测试驱动信心**：协议测试不依赖 DB、冒烟 0.6 秒门禁、verify_seed 保证演示数据一致，显著降低演示翻车概率。

### 7.3 不足与展望

当前系统仍是**单读卡区演示版**，距离生产级 WMS 尚缺：多用户权限、BOM 领料出库、通用 PATCH 改库存 UI、Alembic 迁移、Docker/Windows 服务化、SQLite WAL 与 RFID 写库去重等。路线图已规划 64 路射频复用与 ESP32 WiFi 网关，可在保持后端 API 稳定的前提下扩展感知层。

若继续迭代，建议优先：**新建料盒自动生成格位**、**通用手动出入库 API/UI**、**修复全量 pytest 隔离**，再逐步对接 MES/ERP 或移动端。

### 7.4 个人感悟

本项目让我体会到，**物联网类软件的价值不仅在于「读到 ID」**，更在于 ID 与业务对象（格位、物料、操作记录）的稳定绑定，以及在噪声环境下仍可信的状态机设计。硬件规格书与现场实测往往存在差异（如短帧、无 Time TLV），保留 FrameBuffer 与兼容逻辑、编写可重复的串口测试 CLI，是项目能走通的关键。

同时，**文档与测试与代码同等重要**：MEMO 记录踩坑、TESTING 约定 fixture、种子脚本保证演示可复现——这些「看不见的工作」决定了项目能否被他人接手、能否在答辩或汇报中稳定演示。智能料盒管理的方向是正确的；随着标签成本下降与 lab 数字化需求上升，类似轻量、开源、可扩展的本地方案将有持续的应用空间。

---

**附录：项目仓库结构（精简）**

```
smart_ee_inventory/
├── main.py                 # 应用入口
├── gateway/                # RFID 网关与协议
├── backend/                # API、模型、服务、看门狗
├── frontend/               # NiceGUI 页面与组件
├── scripts/                # init_db、seed、测试 CLI、模拟器
├── tests/                  # pytest（78 用例，含 test_frontend）
├── data/inventory.db       # SQLite（运行后生成）
└── docs/                   # 项目文档
```

---

*报告编写依据项目代码与文档，版本 smart_ee_inventory v0.1.0，2026 年 6 月。*
