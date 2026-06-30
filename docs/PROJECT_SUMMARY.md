# 智能电子元器件料盒系统 — 项目总结

> 文档版本：2026-06-30（库存与标签单页 / 出库未登记）  
> 适用代码：smart_ee_inventory v0.1.0

---

## 一、项目目标

构建一套**单机部署、纯 Python3** 的智能料盒管理系统，用于电子元器件与电气五金件的存放、识别与库存管理。硬件为 USB 通讯的 **YZ-M40 UHF RFID 模块**，通过 PC 端软件实现：

- RFID 标签读取与实时推送
- 料盒/格位管理
- 物料主数据与库存记录
- BOM（物料清单）维护

---

## 二、已完成工作

### 2.1 项目脚手架（第 1 步）

| 内容 | 说明 |
|------|------|
| 技术选型 | pyserial + FastAPI + SQLite + NiceGUI |
| 目录结构 | `gateway/`、`backend/`、`frontend/`、`config/`、`scripts/`、`tests/` |
| 依赖管理 | `pyproject.toml`，Python ≥ 3.11 |
| 应用入口 | `main.py`：`build_app()` 集成 FastAPI + NiceGUI + Gateway 生命周期 |
| 配置 | `.env.example` + `config/settings.py` |

### 2.2 YZ-M40 协议适配（第 2 步）

依据 **YZ-M40 读写器模块规格书 V1.4** 完成二进制协议层：

**帧结构**

```
'R''F' | FrameType(1B) | Address(2B) | FrameCode(1B) | ParamLen(2B) | Parameters(NB) | Checksum(1B)
```

**关键实现**

| 模块 | 功能 |
|------|------|
| `gateway/protocol/frames.py` | 校验和、帧解码、TLV 解析（EPC/RSSI/Time）、`FrameBuffer` 粘包/半包 |
| `gateway/protocol/commands.py` | 0x21 开始盘存、0x23 停止、0x22 单次盘存、0x40 查版本 |
| `gateway/rfid_reader.py` | 512B 批量读取 + drain；连接后可选发 0x21 |
| `tests/test_gateway/test_frames.py` | 帧解析回归用例 |

**标签通知解析示例**

```
52 46 02 00 00 80 00 19 50 17 01 0C E2...7D 05 01 C3 ... 4C
       ↑通知  ↑0x80  ↑Tag TLV    ↑EPC(12B)    ↑RSSI=-61
```

用户实测短帧（28 字节，Tag TLV `0x11`，无 Time TLV）也已兼容。

### 2.3 SQLite 数据模型（第 3 步）

在 `backend/models/models.py` 设计 **12 张表**，覆盖电子元件与五金件场景：

**物料域**

- `part_categories` — 分类树（被动/主动/连接器/五金/耗材）
- `parts` — 物料主数据：封装、阻值/容值、电压电流、螺纹尺寸等
- `part_params` — EAV 扩展参数（温漂、磁介质、头型等）

**料盒域**

- `bin_cabinets` — 料盒/柜体（行列层、RFID）
- `bin_slots` — 格位（最小存储单元，可独立 RFID）

**库存域**

- `inventory_items` — 格位库存（数量、预留、最小/补货点、批次、状态）
- `inventory_transactions` — 出入库/调拨/盘点流水（底层）
- **`inventory_operations`** — **业务操作记录**（`take_out`/`return`/`register_in`；`status` pending/confirmed；使用人/项目/消耗）

**非标资产域**

- **`assets`** — 非标物件（工具、开发板等），独立 RFID，状态 `in_stock`/`checked_out`

**BOM 域**

- `boms` / `bom_lines` — BOM 头与明细（位号、用量、可选件）

**RFID 域**

- `rfid_events` — 读卡事件日志

**持久化方案**

| 项目 | 选型 |
|------|------|
| 数据库 | SQLite 文件 `./data/inventory.db` |
| ORM | SQLAlchemy 2.x 异步 + `aiosqlite` |
| 建表 | `Base.metadata.create_all` + `migrate.py` 补列（启动时 + `init_db.py`） |
| 迁移 | **无 Alembic**（大改表用 `--drop` 重建） |

**初始化脚本**

| 脚本 | 功能 |
|------|------|
| `scripts/init_db.py` | 建表、`--seed`/`--no-seed`/`--drop` |
| `scripts/seed_data.py` | **3 条测试物料**、`BIN-TEST` 料盒 1×3 格位、各格绑定实测 EPC |

### 2.4 启动入口修复（第 4 步）

**问题**：`ui.run_with()` 不支持 `host`/`port`/`reload` 参数，导致 `TypeError` 无法启动。

**修复**：`main.py` 改为：

```python
ui.run_with(app, title="...")
uvicorn.run(app, host=..., port=..., reload=settings.debug)
```

**注意**：`DEBUG=true` 时热重载会占用串口，接 RFID 硬件时建议 `DEBUG=false`。

### 2.5 RFID 串口调试与修复（第 5 步）

| 内容 | 说明 |
|------|------|
| 硬件确认 | USB 模块在 **COM11**（`VID:PID=19F5:3245`），115200 8N1 |
| 实测 EPC | `E28068940000502244813C7D`（28 字节通知帧，无 Time TLV） |
| 测试工具 | `scripts/test_rfid_serial.py`（list / version / monitor / raw） |
| 健康检查 | `scripts/check_rfid_health.py` |
| 监听丢帧修复 | `feed()` + `drain_all_frames()` 连用会吞帧 → 测试脚本改 `push()` + drain |
| 主程序收卡修复 | 512B chunk + `read_available()` 非阻塞；默认 20ms 间隔 |
| 串口独占 | Windows 单 COM 单进程 |

**用户已验证**：`monitor -p COM11` 可正常显示标签 EPC 与 RSSI。

### 2.6 P1 业务骨架（第 6 步，2026-06-30）

| 内容 | 说明 |
|------|------|
| RFID 事件入库 | `lifespan._on_gateway_event` → `record_rfid_event()` |
| EPC 绑定查询 | 读 `bin_slots.rfid_tag_epc` / `bin_cabinets.rfid_tag_epc` |
| 格位 API | `GET/PATCH /api/v1/slots`（含库存摘要 JOIN） |
| 库存 API | `GET /api/v1/inventory`（只读，支持低库存筛选） |
| 料盒 API | 完整 CRUD `/api/v1/bins` |
| 物料 API | `GET/POST /api/v1/components` |
| RFID 事件 API | `GET /api/v1/rfid/events` |
| 前端五页 | `/` 仪表盘、`/bins`、`/slots`、`/inventory`、`/inventory/register` |
| 料盒 UI | 新建/编辑/删除、料盒级 EPC 绑定 |
| 格位 UI | 料盒选择 + 行列网格、格位 EPC/标签编辑 |
| 仪表盘 | HTTP 轮询 RFID 事件（0.3s）；修复 NiceGUI `.style()` 500 错误 |
| 测试 | API 测试扩展（bins / slots / inventory / rfid / register），pytest 共 ~20 例 |

### 2.7 P1+ 功能扩展（2026-06-30）

| 内容 | 说明 |
|------|------|
| 入库绑定 API | `POST /api/v1/inventory/register`：格位/EPC/库存/入库流水一次写入 |
| 入库绑定 UI | `/inventory/register`：选料盒/格位 → 物料**料号** → 听卡或手输 EPC |
| RFID 状态 API | `GET /api/v1/rfid/status`（网关 enabled/connected/port） |
| 仪表盘货架视图 | `/` 首页料盒选择 + `shelf_grid.py` 格位网格（状态/料号/数量/EPC） |
| ApiClient 改进 | `resolve_api_base_url()` 跟随浏览器 host；HTTP 10s 超时 |
| NiceGUI 加载修复 | 首页与入库页改为 timer 异步加载，避免页面一直转圈 |

### 2.8 UI/UX 与实时性（2026-06-30 续）

| 内容 | 说明 |
|------|------|
| 仪表盘双栏 | `/` 左半货柜网格、右半统计/料盒表/RFID 日志，单页展示 |
| 货柜搜索 | `shelf_grid.py` 按元件名/料号/格位/EPC 过滤，匹配格位高亮 |
| 格位卡片 | 元件**名称**为标题；RFID 已绑定仅 NFC 图标，不显示 EPC 全文 |
| 顶栏导航 | `navbar.py` Quasar 扁平按钮 + 图标 + 当前页高亮 |
| RFID 低延迟 | 先 `event_bus` 广播再异步入库；`rfid_listener` 进程内推送 |
| 货架防闪烁 | `@ui.refreshable` + 数据 snapshot，避免定时刷新空白 |
| 默认轮询 | `RFID_READ_INTERVAL_MS=20`；网关有标签时连续读 |

### 2.9 看门狗与库存操作（2026-06-30）

| 内容 | 说明 |
|------|------|
| **PresenceWatchdog** | `presence_watchdog.py`：appear/disappear 去抖 + bootstrap |
| **待确认流程** | `operation_service.create_presence_pending_action()` → 弹窗 → `confirm` |
| **出库确认** | 使用人、使用项目；库存 -1；格位 `checked_out` |
| **入库确认** | 消耗数量（默认 0）；库存 `原值 + 1 - 消耗` |
| **操作记录** | `inventory_operations` + `inventory_transactions` |
| **API** | `GET/DELETE /inventory/operations`；`POST .../confirm` / `cancel` |
| **事件** | `PRESENCE_CONFIRM_REQUIRED`、`INVENTORY_OPERATION` |
| **测试** | `test_presence_watchdog.py`、`test_operation_confirm.py` |

### 2.10 双类型库存与操作记录页（2026-06-30 续）

| 内容 | 说明 |
|------|------|
| **双类型** | `slot_material`（格位物料）+ `asset`（非标物件） |
| **EPC 解析** | `epc_binding.lookup_epc_binding()` |
| **统一入库** | `POST /inventory/register` + `bind_type` |
| **库存 UI** | `/inventory` 三区折叠列表；`/inventory/register` 绑定类型单选 |
| **操作记录页** | `/inventory/operations`：筛选、待确认行点击、清空记录 |
| **确认弹窗** | `presence_confirm.py`（仪表盘 + 操作记录页共用） |
| **格位着色** | `shelf_grid.py`：`pending_checkout`、`checked_out` 等 |
| **种子** | `AST-0001` Jetson 演示非标物件 |
| **pytest** | ~32 例（含内存库 `conftest`） |

### 2.11 标签管理与非标借还（2026-06-30 续）

| 内容 | 说明 |
|------|------|
| **标签管理 API** | `POST .../manage/bind-tag`、`rebind-tag`、`unbind-tag`；`DELETE .../manage/{type}/{id}` |
| **删除库存** | 料盒物料删 `inventory_item` 并清空格位 EPC；非标删 `asset` 整条 |
| **管理 UI** | `/inventory` 标签管理区（表格列表）；`/inventory/manage` → 重定向 |
| **非标借还** | 仪表盘读卡弹窗 + `POST /assets/take-out|return`（`source=manual_scan`） |
| **看门狗范围** | **仅格位物料**；非标 EPC 在看门狗中忽略 |
| **料盒状态** | `checkout_unregistered`（出库未登记）← `pending_checkout` |
| **pytest** | ~38 例 |

### 2.13 库存与标签单页（2026-06-30 续）

| 内容 | 说明 |
|------|------|
| **页面** | `/inventory`：统计卡片 + 工具栏（低库存筛选、分页） |
| **料盒物料 / 非标物件** | 折叠表格；行内编辑（`PATCH items/assets`）、删除 |
| **标签管理** | 默认折叠；EPC 为主条目的表格；绑定/换绑/解绑/删除 |
| **手动编辑** | 记入 `inventory_operations`（`manual_edit`） |
| **重定向** | `/inventory/manage` → `/inventory` |

**看门狗规则（单天线，待确认版，仅格位物料）**：

- 标签**离开** → `pending_checkout` → 料盒 **出库未登记** → 弹窗 → 确认后 -1
- 标签**回到** → 创建 `pending` 的 `return`，格位 `pending_return` → **弹窗** → 确认后调整库存
- 网关就绪后 **bootstrap 5s** 内不判离开、不发出入库事件
- 未绑定 EPC：仅弹窗引导入库，不改库存

### 2.12 BOM 分析与取料（2026-06-30 续）

| 内容 | 说明 |
|------|------|
| **CSV 格式** | 演示用：`bom_code,bom_name,version` + `part_number,quantity,...`；样例 `scripts/demo_bom.csv` |
| **服务** | `backend/services/bom_service.py`：解析、按料号匹配 `parts`、汇总 `inventory_items` 格位 |
| **API** | `POST /boms/preview`、`POST /boms/import`、`GET /boms/{id}/analysis` |
| **UI** | `/inventory/bom`：预览/导入、缺口表、选择料盒后 **蓝色高亮** BOM 格位 |
| **限制** | 扁平 BOM；未知料号导入失败（预览可标 `missing_part`）；不自动领料出库 |
| **pytest** | `test_bom.py`、`test_bom_api.py` |

---

## 三、当前系统能力

### ✅ 可用

| 能力 | 状态 |
|------|------|
| 本地启动 Web 服务（API + UI 同端口） | ✅ |
| Swagger 文档 `/docs` | ✅ |
| 料盒 CRUD `/api/v1/bins` + UI | ✅ |
| 格位查询/更新 `/api/v1/slots` + UI | ✅ |
| 库存查询 `/api/v1/inventory` + UI | ✅ |
| **库存入库绑定** `POST /api/v1/inventory/register` + UI | ✅ |
| **RFID 网关状态** `/api/v1/rfid/status` | ✅ |
| **仪表盘双栏 + 货柜搜索** | ✅ |
| **RFID 低延迟（event_bus + listener）** | ✅ |
| **单天线看门狗** 待确认出库/入库 | ✅ |
| **出库/入库确认弹窗**（使用人/项目、消耗） | ✅ |
| **双类型库存**（料盒物料 + 非标物件） | ✅ |
| **操作记录管理页** `/inventory/operations` | ✅ |
| **标签管理** | bind/rebind/unbind/delete；UI 在 `/inventory` 标签区 | ✅ |
| **非标物件读卡借还** | ✅ 仪表盘弹窗（已移除 `/inventory/asset-ops` 独立页） |
| **料盒状态** 出库未登记 / 已出库 | ✅ |
| **库存操作记录** API（含 confirm/cancel/clear） | ✅ |
| **仪表盘操作日志**（仅已确认记录） | ✅ |
| **未登记标签 → 入库绑定** | ✅ 仪表盘弹窗跳转 |
| **BOM 分析** CSV 导入/预览/格位定位 + `/inventory/bom` | ✅ |
| 物料列表/创建 `/api/v1/components` | ✅ |
| 分类列表 `/api/v1/categories` | ✅ |
| RFID 事件查询 `/api/v1/rfid/events` | ✅（调试） |
| YZ-M40 串口读卡 + 协议解析 | ✅ |
| RFID 事件写入 `rfid_events` 表 | ✅ |
| EPC → 格位/料盒 ID 关联 | ✅ |
| WebSocket 广播 `/ws/bin-status` | ✅ `tag_read` + `inventory_operation` |
| RFID 串口测试脚本 | ✅ 已实测 |
| 完整数据库模型 + 演示数据 | ✅ |
| 单元/API 测试 | ✅ ~45 例；见 `docs/TESTING.md` |

### ⚠️ 部分可用 / 骨架级

| 能力 | 说明 |
|------|------|
| 看门狗业务 | **仅格位物料**；待确认弹窗 + 确认后改库存 |
| 非标物件 | **手动读卡**借还；不进料盒、不看门狗 |
| 格位管理 | 含 `pending_*` / `checked_out` / 料盒 `checkout_unregistered` |
| 库存管理 | 看门狗 + register + **标签管理** + 删除库存 |
| 前端实时性 | 进程内 `EventBusListener`；HTTP 2s 兜底 |
| NiceGUI 页面加载 | 必须用 timer 异步拉 API |
| 种子 EPC | 演示 `BIN-TEST` 三格；与用户真实标签需手动对齐 |

### ❌ 尚未实现

| 能力 | 说明 |
|------|------|
| 库存数量 PATCH | 无通用改数量 API |
| 格位物料手动出库 UI | 除看门狗弹窗/register 外无独立表单 |
| BOM 领料出库 | 仅分析与定位，不扣库存 |
| 64 路射频复用 | 远期 |
| ESP32 WiFi 读卡网关 | 见 `docs/ESP32_WIFI_RFID.md`，未实现 |
| 用户认证 | 无 |
| Alembic 迁移 | 无（仅 `migrate.py` 补列） |
| 生产部署 | 无 Docker/Windows 服务/备份脚本 |

---

## 四、数据流现状

```
                    ┌─────────────────────────────────────────┐
  YZ-M40 ──串口──►  │ gateway/service.py → TAG_READ         │
                    └──────────────────┬──────────────────────┘
                                       │
                    ┌──────────────────▼──────────────────────┐
                    │ lifespan：EPC 查表 → event_bus(TAG_READ) │
                    │          → create_presence_pending_action() │
                    │          → PRESENCE_CONFIRM_REQUIRED → 弹窗 │
                    │          → confirm → INVENTORY_OPERATION   │
                    │          → rfid_events 异步入库          │
                    └──────────┬───────────────┬──────────────┘
                               │               │
              ┌────────────────▼──────┐  ┌─────▼──────────────┐
              │ EventBusListener      │  │ ws/bin-status      │
              │ 确认弹窗 + 操作日志 ✅  │  │ WebSocket          │
              └───────────────────────┘  └────────────────────┘
                               │
              ┌────────────────▼──────────────────────────────┐
              │ dashboard：左货柜网格 │ 右：统计+料盒+操作日志 ✅ │
              └─────────────────────────────────────────────┘
                               │
              ┌────────────────▼──────────────────────────────┐
              │ /inventory/register：双类型入库 ✅              │
              │ /inventory/operations：记录管理 ✅            │
              └─────────────────────────────────────────────┘
```

---

## 五、演示数据概览

初始化后（`python scripts/init_db.py`）包含：

**物料（3 条，测试用）**

| 料号 | 类型 |
|------|------|
| T-R-10K | 测试电阻 10kΩ |
| T-C-100N | 陶瓷电容 100nF |
| T-LED-RED | 红色 LED |

**料盒**

- `BIN-TEST`：1×3 格位，各格绑定实测 EPC 与库存
- 格位 EPC 见 [MEMO.md §8](MEMO.md) 或 `scripts/seed_data.py`

---

## 六、部署建议

### 本地演示（当前即可）

```powershell
Copy-Item .env.example .env
# 编辑：RFID_ENABLED、DEBUG=false、COM 口
python scripts\init_db.py
python main.py
```

浏览器访问：

| URL | 页面 |
|-----|------|
| http://127.0.0.1:8765/ | 仪表盘（货柜 + 非标物件 + 读卡弹窗借还） |
| http://127.0.0.1:8765/bins | 料盒管理 |
| http://127.0.0.1:8765/slots | 格位视图 |
| http://127.0.0.1:8765/inventory | 库存与标签（三区列表、编辑/删除） |
| http://127.0.0.1:8765/inventory/register | 入库绑定（物料按料号选择） |
| http://127.0.0.1:8765/inventory/manage | 重定向至 `/inventory` |
| http://127.0.0.1:8765/inventory/bom | BOM 分析（CSV / 格位高亮） |
| http://127.0.0.1:8765/inventory/operations | 操作记录管理 |
| http://127.0.0.1:8765/docs | API 文档 |

### 接 RFID 硬件

1. `python scripts/test_rfid_serial.py list` 确认 COM 口（USB 设备，非蓝牙）
2. `.env`：`RFID_SERIAL_PORT=COM11`，`RFID_ENABLED=true`，`DEBUG=false`
3. 主程序需发 0x21：`RFID_AUTO_START_INVENTORY=true`（默认）
4. 先测串口：`python scripts/test_rfid_serial.py monitor -p COM11 -d 10`
5. 再启主程序：`python main.py`（勿与测试脚本同时占 COM）
6. 格位物料 EPC 绑定后，看门狗会对**料盒格位**自动待确认出库/入库
7. **非标物件**在仪表盘读卡 → 弹窗借出/归还
8. `/inventory` 可编辑/删除库存，标签区可换绑、解绑、删除
9. 未登记标签在仪表盘弹窗 → **入库绑定**（EPC 自动预填）

### 看门狗演示脚本（约 5 分钟）

1. 打开 `/`，选 `BIN-TEST`
2. 拿离 **电阻** 标签 → **出库确认弹窗** → 填使用人/项目 → 库存 -1
3. 放回标签 → **归还弹窗** → 填消耗（可 0）→ 库存调整
4. 换**未绑定**标签 → 弹窗 → 跳转入库页
5. `/inventory/operations` 查看全部记录，可筛选/清空

### 生产环境（待完善后）

- 增加 Alembic 迁移与定时备份
- 通用手动出入库 UI（看门狗弹窗/register 之外）
- 封装 Windows 计划任务或 Docker

---

## 七、后续路线图

| 优先级 | 任务 | 状态 |
|--------|------|------|
| ~~**P1**~~ | RFID 事件入库 + EPC 匹配 | ✅ 已完成 |
| ~~**P1**~~ | 格位/库存 REST API + 前端页 | ✅ 骨架已完成 |
| ~~**P1**~~ | 料盒 CRUD + EPC 绑定 UI | ✅ 已完成 |
| ~~**P1+**~~ | 仪表盘货柜搜索 + 双栏布局 | ✅ 已完成 |
| ~~**P1+**~~ | RFID 低延迟（event_bus listener） | ✅ 已完成 |
| ~~**P1+**~~ | 入库绑定 register API + UI | ✅ 已完成 |
| ~~**P1+**~~ | 读卡后更新格位/库存状态（单天线看门狗） | ✅ 已完成 |
| ~~**P-Demo**~~ | 单天线看门狗 + 待确认弹窗 | ✅ 已完成 |
| ~~**P2**~~ | 看门狗借还对话框（使用人/项目/消耗） | ✅ 已完成 |
| ~~**P2**~~ | 双类型库存 + 操作记录管理页 | ✅ 已完成 |
| ~~**P2**~~ | 标签管理（绑定/换绑/解绑/删除） | ✅ 已完成 |
| ~~**P2**~~ | 非标物件手动借还（不看门狗） | ✅ 已完成 |
| ~~**P2**~~ | 料盒状态「出库未登记」 | ✅ 已完成 |
| **P2** | 库存数量 PATCH API | 待做 |
| **P1+** | 新建料盒自动生成格位 | 待做 |
| **P2** | BOM API + 领料 UI | 待做 |
| **P2** | 前端 WebSocket 客户端（替代 event_bus，多进程部署时） | 可选 |
| **P3** | SQLite WAL + RFID 写库去重 | 待做 |
| **P4** | **64 路天线复用**（远期） | 设计稿见 `RFID_MULTIPLEXER_WATCHDOG.md` §4 |
| **P3** | Docker / Windows 服务 | 待做 |
| **P3** | 用户认证 | 待做 |

---

## 八、关键文件索引

| 文件 | 用途 |
|------|------|
| `main.py` | 应用入口 |
| `backend/models/models.py` | ORM 模型（权威定义） |
| `backend/db/session.py` | 异步引擎与会话 |
| `backend/services/presence_watchdog.py` | 单区 appear/disappear 去抖 |
| `backend/services/operation_service.py` | 看门狗待确认、非标手动借还、料盒状态同步 |
| `backend/services/inventory_manage_service.py` | 标签 bind/rebind/unbind、删除库存 |
| `backend/core/lifespan.py` | Gateway + 看门狗 tick + RFID 入库 |
| `backend/services/epc_binding.py` | EPC 统一解析 |
| `frontend/components/navbar.py` | 顶栏导航 |
| `frontend/components/shelf_grid.py` | 货柜格位网格（搜索、元件名标题） |
| `frontend/pages/dashboard.py` | 双栏仪表盘 + 操作记录 + 未登记弹窗 |
| `frontend/pages/` | dashboard / bins / slots / inventory / bom / register / operations |
| `frontend/services/api_client.py` | HTTP 客户端 |
| `frontend/services/event_listener.py` | event_bus 多事件订阅 |
| `frontend/services/rfid_listener.py` | 入库页 RFID 听卡 |
| `gateway/protocol/frames.py` | YZ-M40 帧解析 / 组帧 |
| `gateway/board_simulator.py` | RFID 开发板协议模拟（测试 + debug CLI 共用） |
| `scripts/init_db.py` | 数据库初始化 |
| `scripts/seed_data.py` | 演示种子数据 |
| `scripts/simulate_rfid_board.py` | TCP 模拟读卡器 |
| `scripts/verify_seed.py` | 种子数据校验 |
| `scripts/smoke_test.py` | 冒烟测试入口 |
| `scripts/test_rfid_serial.py` | RFID 串口测试 CLI |
| `scripts/check_rfid_health.py` | 健康检查 |
| `docs/TESTING.md` | 测试与调试指南 |
| `docs/MEMO.md` | 开发备忘录（踩坑、硬件实测） |
| `.env.example` | 环境变量模板 |

---

## 九、结论

项目已完成**架构搭建、协议适配、12 表数据建模、RFID 低延迟、格位物料待确认看门狗、双类型库存、标签管理、仪表盘非标读卡借还、BOM 分析、操作记录管理页与 NiceGUI 八页**，可作为**本地开发演示版**运行。

距离**完整业务系统**尚差：**手动出入库表单、BOM 管理、64 路复用、SQLite WAL、生产运维**。建议下一步：新建料盒自动生成格位 + 通用手动出入库 API。
