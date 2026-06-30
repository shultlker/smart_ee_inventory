# 智能电子元器件料盒系统 (Smart EE Inventory)

单机部署的 RFID 料盒管理系统：USB RFID 开发板 (YZ-M40) → Python 网关 → FastAPI 后端 → NiceGUI 前端。

## 技术栈

| 层级 | 技术 | 职责 |
|------|------|------|
| 硬件通信层 | Python + **pyserial** | USB 串口读写、YZ-M40 二进制帧解析 |
| 后端 API | **FastAPI** + **Uvicorn** | RESTful CRUD、WebSocket 实时推送 |
| 数据库 | **SQLite** + SQLAlchemy (async) | 物料、格位、库存、操作记录、BOM、RFID 事件 |
| 前端 UI | **NiceGUI** | 仪表盘、料盒/格位/库存（与 FastAPI 同进程）；**全页全局 RFID 弹窗** |
| 配置 | pydantic-settings + `.env` | 端口、串口、数据库路径等 |

### 直接依赖（实测版本 · Python 3.11.5）

| 包 | 版本 | 说明 |
|----|------|------|
| fastapi | 0.138.1 | REST / WebSocket API |
| uvicorn[standard] | 0.49.0 | ASGI 服务 |
| nicegui | 3.13.0 | Web UI |
| sqlalchemy | 2.0.51 | ORM（异步 + greenlet） |
| aiosqlite | 0.22.1 | SQLite 驱动 |
| pydantic / pydantic-settings | 2.13.4 / 2.14.2 | 模型与配置 |
| pyserial | 3.5 | RFID 串口 |
| httpx | 0.28.1 | 前端 HTTP 客户端 |
| python-dotenv | 1.2.2 | `.env` 加载 |

开发：`pytest` 9.1.1 · `pytest-asyncio` 1.4.0 · `ruff` 0.15.20  

完整说明、传递依赖与锁定安装见 **[docs/DEPENDENCIES.md](docs/DEPENDENCIES.md)**。

> 前端 [NiceGUI](https://nicegui.io/) 与 FastAPI 同进程：`ui.run_with(app)` + `uvicorn.run()`。

## 架构

```
┌─────────────┐     USB/Serial      ┌──────────────────┐
│ YZ-M40 模块  │ ──────────────────► │  gateway/        │
└─────────────┘   RF 帧 + TLV       │  protocol/       │
                                    └────────┬─────────┘
                                             │ EventBus (asyncio)
                                             ▼
┌─────────────┐   event_bus / REST   ┌──────────────────┐
│  NiceGUI    │ ◄──────────────────► │  backend/        │
│  frontend/  │                      │  (FastAPI)       │
└─────────────┘                      └────────┬─────────┘
                                              │
                                              ▼
                                     ┌──────────────────┐
                                     │  SQLite (12表)   │
                                     └──────────────────┘
```

## 快速开始

### 环境要求

- **Python 3.11+**（推荐 3.11 或 3.12）
- **pip** 23+（安装 editable 包需 **hatchling**，会自动拉取）

### 安装依赖

```powershell
# 1. 创建并激活虚拟环境
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 2. 升级 pip 并安装项目（含 pytest / ruff）
python -m pip install -U pip
pip install -e .

# 仅在本机开发、需要跑测试 / ruff 时再装（其它 PC 部署可跳过）：
# pip install -r requirements-dev-lock.txt

# 若仍习惯一条命令装 dev，也可（已收窄 ruff 版本范围，不再从 0.8 回溯）：
# pip install -e ".[dev]"
```

Linux / macOS 将激活命令改为 `source .venv/bin/activate`。

**锁定版本安装**（与开发机一致）：见 [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) 与根目录 `requirements-lock.txt`。

### 配置与启动

```powershell
# 3. 配置环境变量
Copy-Item .env.example .env
# 编辑 .env（见下方「RFID 硬件」）

# 4. 初始化数据库（含演示数据）
python scripts/init_db.py

# 5. 启动服务
python main.py
```

**验证安装**（可选）：

```powershell
python -c "import fastapi, nicegui, sqlalchemy, serial; print('dependencies OK')"
python scripts/smoke_test.py
```

**访问地址**

| 地址 | 说明 |
|------|------|
| http://127.0.0.1:8765/ | 仪表盘（**左栏**：料盒货柜 + 非标物件；**右栏**：统计/操作记录；读卡弹窗借还） |
| http://127.0.0.1:8765/bins | 料盒管理（CRUD + EPC 绑定） |
| http://127.0.0.1:8765/slots | 格位网格（EPC/标签编辑） |
| http://127.0.0.1:8765/inventory | **库存与标签管理**（统计卡片、折叠列表、编辑/删除、标签列表） |
| http://127.0.0.1:8765/inventory/register | **入库绑定**（料盒/格位/物料料号 + RFID；支持 `?epc=` 预填） |
| http://127.0.0.1:8765/inventory/bom | **BOM 分析**（CSV 导入、库存匹配、货柜格位高亮） |
| http://127.0.0.1:8765/inventory/operations | **库存操作记录**（筛选、待确认、清空） |
| http://127.0.0.1:8765/docs | Swagger API 文档 |
| ws://127.0.0.1:8765/ws/bin-status | 事件 WebSocket（`tag_read` / `presence_confirm_required` / `inventory_operation`） |

> 若 `APP_PORT` 被占用，`main.py` 自动尝试 8090、8888 等备选端口。

## RFID 硬件

### 识别 COM 口

```powershell
python scripts/test_rfid_serial.py list
```

- 选 **USB 串行设备**（非蓝牙 `BTHENUM` 虚拟口）
- 插拔 USB 对比前后端口变化
- 本机实测模块：**COM11**（`VID:PID=19F5:3245`）

### 推荐 `.env`

```ini
RFID_SERIAL_PORT=COM11
RFID_BAUD_RATE=115200
RFID_ENABLED=true
RFID_AUTO_START_INVENTORY=true   # 主程序发 0x21；硬件已读卡且冲突时 false
RFID_READ_INTERVAL_MS=20         # 网关轮询间隔（settings 默认 20）
# 看门狗：单天线读卡区 → 待确认出库/入库对话框
RFID_PRESENCE_ENABLED=true
RFID_PRESENCE_APPEAR_COUNT=2
RFID_PRESENCE_DISAPPEAR_COUNT=6
RFID_PRESENCE_TICK_MS=200
RFID_PRESENCE_MISS_GRACE_MS=1200
RFID_PRESENCE_BOOTSTRAP_MS=5000   # 网关就绪后再计时；期间不判离开
DEBUG=false                       # 避免热重载占用串口
APP_PORT=8765
```

### 看门狗演示（已绑定标签）

1. 启动 `main.py`，打开任意页面（如 `/` 或 `/inventory`），仪表盘可选 `BIN-TEST`
2. 将种子标签**拿离**读卡区 → 弹出**出库确认**（使用人、使用项目）→ 确认后库存 -1，格位 `checked_out`
3. 将标签**放回**读卡区 → 弹出**入库归还**（可填消耗数量）→ 确认后库存按 `+1 - 消耗` 调整
4. 未登记标签靠近 → 弹窗「跳转入库绑定」→ `/inventory/register?epc=...`

> **出入库/借还弹窗**由顶栏 `navbar()` 挂载的 **全局 EventBus 监听**驱动，在库存、BOM、入库绑定等**任意页面**均可响应，不仅限于仪表盘。

> **非标物件**不进料盒格位，**不使用看门狗**。读卡后弹出**借出/归还**对话框；仪表盘左栏下半区可查看全部非标物件列表。

### 非标物件借还（读卡弹窗）

1. 打开任意带顶栏的页面，将已登记的非标物件标签靠近读卡器
2. **在库** → 弹出借出对话框，填写使用人、使用项目后确认
3. **已借出** → 弹出归还对话框，确认后入库

### 库存与标签管理

在 `/inventory` 单页完成库存维护与 RFID 标签操作：

**料盒物料 / 非标物件**（可折叠列表，支持分页与低库存筛选）：

- **编辑**：修改数量、阈值或物件信息（记入 `manual_edit` 操作记录）
- **删除**：删除 `inventory_item` 或整条 `asset` 记录（需确认）

**标签管理**（默认折叠，表格列表）：

- **绑定标签**：库存尚无 EPC 时贴签
- **换绑**：更换 RFID 标签
- **解绑**：清除 EPC，保留库存数量
- **删除**：同上方删除库存

> `/inventory/manage` 已合并至本页，访问时自动跳转到 `/inventory`。


```powershell
# 先停止 main.py，确保 COM 口未被占用

python scripts/test_rfid_serial.py list
python scripts/test_rfid_serial.py version -p COM11
python scripts/test_rfid_serial.py monitor -p COM11 -d 15 --no-dedupe
python scripts/check_rfid_health.py
```

**无硬件调试**（TCP 模拟 YZ-M40，可与 `main.py` 同时运行）：

```powershell
# 终端 1
python scripts/simulate_rfid_board.py

# 终端 2 — .env 或环境变量
# RFID_SERIAL_PORT=socket://127.0.0.1:9276
python main.py

# 终端 1 交互示例
# rfid> hold r10k          # 持续上报测试电阻标签
# rfid> release all        # 模拟标签离开读卡区
# rfid> emit jetson        # 单次上报 Jetson 标签
```

预设别名 `r10k` / `c100n` / `jetson` 对应种子库三枚 EPC。详见 `scripts/simulate_rfid_board.py`。

`monitor` 流程：发送 0x21 开始盘存 → 监听解析 → 0x23 停止。

### 协议摘要

- 帧头：`52 46` (`'R''F'`)
- 标签通知：Type=`0x02`，Code=`0x80`，TLV `0x50` → EPC + RSSI
- 默认波特率：**115200 8N1**
- 用户实测 EPC：`E28068940000502244813C7D`（28 字节帧，无 Time TLV）
- 详见 [docs/MEMO.md](docs/MEMO.md)（含踩坑记录）

## 数据库

**方案**：SQLite 单文件 + SQLAlchemy 2.x 异步（`aiosqlite`），路径 `./data/inventory.db`。

```powershell
python scripts/init_db.py          # 建表 + 演示数据
python scripts/init_db.py --no-seed  # 仅建表
python scripts/init_db.py --drop     # 清空重建
```

应用启动时 `create_all` + **轻量 schema 迁移**（`backend/db/migrate.py`，补全新列）；无 Alembic。旧库升级后重启 `main.py` 即可。

**数据表（12 张）**：`part_categories`、`parts`、`part_params`、`bin_cabinets`、`bin_slots`、`inventory_items`、`inventory_transactions`、**`inventory_operations`**、**`assets`**、`boms`、`bom_lines`、`rfid_events`

模型：`backend/models/models.py` · 种子数据：`scripts/seed_data.py`

## API 端点（当前已实现）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST/PATCH/DELETE | `/api/v1/bins` | 料盒 CRUD |
| GET/POST | `/api/v1/components` | 物料列表与创建 |
| GET/PATCH | `/api/v1/slots` | 格位列表与更新（EPC/标签/状态） |
| GET | `/api/v1/inventory` | 料盒物料库存（`cabinet_id`/`slot_id`/`low_stock_only`） |
| GET | `/api/v1/assets` | 非标物件列表 |
| POST | `/api/v1/inventory/register` | 统一入库绑定（`bind_type`: `slot_material` \| `asset`） |
| PATCH | `/api/v1/inventory/items/{id}` | 手动修改料盒物料库存（记入 `manual_edit` 操作） |
| PATCH | `/api/v1/assets/{id}` | 手动修改非标物件信息 |
| POST | `/api/v1/inventory/manage/bind-tag` | 为现有库存**绑定** EPC |
| POST | `/api/v1/inventory/manage/rebind-tag` | **换绑** EPC |
| POST | `/api/v1/inventory/manage/unbind-tag` | **解绑** EPC（保留库存） |
| DELETE | `/api/v1/inventory/manage/{entity_type}/{record_id}` | **删除**库存（`slot_material` 用 `inventory_item.id`，`asset` 用 `asset.id`） |
| POST | `/api/v1/assets/take-out` | 非标物件**借出**（手动读卡，`rfid_tag_epc` + 使用人/项目） |
| POST | `/api/v1/assets/return` | 非标物件**归还**（手动读卡） |
| GET | `/api/v1/inventory/operations` | 操作记录（`status`/`operation`/`limit`/`after_id`） |
| POST | `/api/v1/inventory/operations/{id}/confirm` | 确认待处理出库/入库（使用人/项目或消耗数量） |
| POST | `/api/v1/inventory/operations/{id}/cancel` | 取消待确认操作 |
| DELETE | `/api/v1/inventory/operations` | 清空全部操作记录（并重置待确认格位状态） |
| GET | `/api/v1/rfid/events` | RFID 读卡原始事件（调试） |
| GET | `/api/v1/rfid/status` | RFID 网关状态（enabled/connected/port） |
| GET/POST | `/api/v1/boms` | BOM 列表 / 导入（`POST /boms/import`） |
| POST | `/api/v1/boms/preview` | CSV 预览分析（不保存；`kit_qty` 套数） |
| GET | `/api/v1/boms/{id}/analysis` | 已保存 BOM 库存分析与格位定位 |
| WS | `/ws/bin-status` | RFID 事件广播 |

**手动编辑**：料盒物料 `PATCH /api/v1/inventory/items/{id}`、非标 `PATCH /api/v1/assets/{id}`（记入 `manual_edit`）。其余通用库存 PATCH 能力见 [docs/PROJECT_SUMMARY.md](docs/PROJECT_SUMMARY.md)。

**料盒状态**（自动同步）：`active` 正常 · `checkout_unregistered` **出库未登记** · `return_unregistered` **未登记归还** · `checked_out` 已出库

**格位状态**：`occupied` **在库** · `pending_checkout` 待出库 · `checkout_unregistered` 出库未登记 · `checked_out` 已出库 · `pending_return` 待入库 · `return_unregistered` 未登记归还。取消待确认操作**不会**自动回到在库；仅 **RFID 读到标签并确认入库** 后恢复在库。

## 前端页面

| 路径 | 功能 |
|------|------|
| `/` | **仪表盘**：左=料盒货柜 + 非标物件；右=统计/料盒表/操作日志 |
| 任意页 | **全局 RFID**：看门狗出库/入库确认、非标借还、未登记标签引导（经 `navbar` 挂载） |
| `/bins` | 新建/编辑/删除料盒，料盒级 EPC 绑定 |
| `/slots` | 选择料盒 → 行列格位网格 → 编辑格位 EPC |
| `/inventory` | **库存与标签**：统计卡片；料盒物料/非标物件/标签管理三区折叠列表；行内编辑与删除；标签绑定/换绑/解绑 |
| `/inventory/register` | 入库绑定；物料下拉显示**料号**（如 `TEST-LED-RED`）；`?epc=` 预填 |
| `/inventory/bom` | BOM：CSV 导入/预览、库存缺口分析、货柜格位蓝色高亮 |
| `/inventory/operations` | 操作记录管理：筛选、点击待确认行处理、**清空记录** |

> **NiceGUI 页面加载**：新页面勿在 `@ui.page` 入口连续 `await` 多个 API；先渲染骨架，再用 `ui.timer(0.05, load_fn, once=True)` 异步拉数据。货架区用 `@ui.refreshable` 更新，避免 `clear()` 导致闪烁。详见 [docs/MEMO.md §5.6–5.10](docs/MEMO.md)。

## 项目目录

```
smart_ee_inventory/
├── main.py                     # build_app() + uvicorn，端口 fallback
├── config/                     # settings.py, network.py
├── gateway/                    # 串口 + YZ-M40 协议 + board_simulator
├── backend/
│   ├── api/v1/                 # bins, slots, inventory, assets, boms, components, rfid
│   ├── services/               # inventory_service, bom_service, operation_service, …
│   ├── models/                 # ORM 12 表
│   ├── db/migrate.py           # 启动时补全缺失列
│   └── core/lifespan.py        # Gateway + 看门狗 + 待确认操作
├── frontend/
│   ├── components/
│   │   ├── navbar.py
│   │   ├── shelf_grid.py       # 含 pending / checked_out 等状态色
│   │   ├── presence_confirm.py # 格位出库/入库确认弹窗
│   │   └── asset_confirm.py    # 非标物件读卡借还弹窗
│   ├── pages/                  # dashboard, bins, slots, inventory, bom, register, operations
│   └── services/
│       ├── api_client.py
│       ├── event_listener.py
│       ├── global_inventory_events.py  # 全页 RFID：出入库/借还/未登记标签
│       └── rfid_listener.py
├── scripts/
│   ├── init_db.py
│   ├── seed_data.py
│   ├── demo_bom.csv            # BOM 演示 CSV
│   ├── test_rfid_serial.py     # RFID 串口测试 CLI
│   ├── simulate_rfid_board.py  # TCP 模拟 YZ-M40（无硬件调试）
│   ├── verify_seed.py          # 校验 BIN-TEST 种子与 EPC
│   ├── smoke_test.py           # 核心 pytest 冒烟
│   └── check_rfid_health.py    # 健康检查
├── tests/                      # gateway + api + services
└── docs/
    ├── DEPENDENCIES.md         # 依赖清单与安装说明
    ├── TESTING.md              # 测试与调试指南
    ├── PROJECT_SUMMARY.md
    └── MEMO.md                 # 开发备忘录（踩坑 / 硬件实测）
```

## 开发

```powershell
ruff check .
python scripts/smoke_test.py    # 核心组件冒烟
python -m pytest tests -q       # 全量
```

测试与调试脚本说明见 [docs/TESTING.md](docs/TESTING.md)。

## 文档

| 文档 | 说明 |
|------|------|
| [docs/DEPENDENCIES.md](docs/DEPENDENCIES.md) | **依赖与安装** — 直接/传递依赖、锁定版本、常见问题 |
| [docs/TESTING.md](docs/TESTING.md) | **测试与调试** — pytest、模拟器、种子校验 |
| [docs/MEMO.md](docs/MEMO.md) | **开发备忘录** — 硬件参数、踩坑、看门狗、仪表盘 UI |
| [docs/PROJECT_SUMMARY.md](docs/PROJECT_SUMMARY.md) | 项目总结与路线图 |
| [docs/RFID_MULTIPLEXER_WATCHDOG.md](docs/RFID_MULTIPLEXER_WATCHDOG.md) | 看门狗出入库设计：**当前单天线演示** + 远期 64 路 |
| [docs/ESP32_WIFI_RFID.md](docs/ESP32_WIFI_RFID.md) | **ESP32 + WiFi 读卡** 可行性分析与需求草案 |

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `APP_HOST` | 127.0.0.1 | 监听地址 |
| `APP_PORT` | 8765 | Web 端口（占用时自动 fallback） |
| `DEBUG` | true | 热重载；接 RFID 时建议 false |
| `DATABASE_URL` | sqlite+aiosqlite:///./data/inventory.db | 数据库 |
| `RFID_ENABLED` | true | 是否启动 RFID 网关 |
| `RFID_SERIAL_PORT` | COM11 | 串口号 |
| `RFID_BAUD_RATE` | 115200 | 波特率 |
| `RFID_DEVICE_ADDRESS` | 0 | 模块地址 |
| `RFID_AUTO_START_INVENTORY` | true | 连接后发 **0x21 开始盘存** |
| `RFID_READ_INTERVAL_MS` | 20 | 网关轮询间隔（ms）；有标签时连续读不等待 |
| `RFID_PRESENCE_ENABLED` | true | 启用单天线看门狗 |
| `RFID_PRESENCE_APPEAR_COUNT` | 2 | 标签进入读卡区确认次数 |
| `RFID_PRESENCE_DISAPPEAR_COUNT` | 6 | 标签离开确认次数（连续 miss tick） |
| `RFID_PRESENCE_TICK_MS` | 200 | 看门狗 tick 间隔（ms） |
| `RFID_PRESENCE_MISS_GRACE_MS` | 1200 | 未读到标签的宽限时间（ms），减少静止误报 |
| `RFID_PRESENCE_BOOTSTRAP_MS` | 5000 | 网关就绪后静默期（不判离开、不发出入库事件） |
