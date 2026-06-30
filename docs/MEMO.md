# 开发备忘录 (Dev Memo)

> **写给未来的 AI / 开发者**：本文档记录项目演进中的关键决策、已踩过的坑、硬件实测数据与待办。  
> 更新日期：2026-06-30（全页 RFID 弹窗 / BOM / ESP32 方案草案）  
> 代码版本：smart_ee_inventory v0.1.0

---

## 1. 项目一句话

单机 Python3 系统：YZ-M40 UHF RFID 模块 → 串口网关 → FastAPI + NiceGUI + SQLite，管理电子元件/五金料盒与库存。

---

## 2. 硬件与环境（实测）

### 2.1 开发板

| 项目 | 值 |
|------|-----|
| 型号 | YZ-M40 UHF 读写器模块 |
| 协议规格书 | 根目录 `YZ-M40读写器模块规格书V1.4-202406(1).pdf` |
| 连接方式 | USB 虚拟串口 |
| 识别特征 | 设备管理器显示「USB 串行设备」；`VID:PID=19F5:3245`，`SER=N32G43X` |
| **当前 COM 口** | **COM11**（随机器/插口变化，勿写死；用插拔法确认） |

### 2.2 串口参数（已验证可用）

| 参数 | 值 |
|------|-----|
| 波特率 | **115200** |
| 数据位/校验/停止 | **8N1**（pyserial 默认） |
| 设备地址 | **0x0000** |
| 读超时 | 0.1～0.2 s |

**如何确认波特率**：若帧头 `52 46`（`'R''F'`）稳定出现且校验和通过，则波特率正确。用户曾在 115200 下抓到合法标签帧。

### 2.3 如何识别 COM 口

1. `python scripts/test_rfid_serial.py list`
2. 插拔 USB，看新增/消失的端口
3. 排除 `BTHENUM` 开头的蓝牙虚拟串口（COM3–COM10 等）
4. 选描述含 **USB** 且带 **VID:PID** 的端口

### 2.4 现场真实标签 EPC

用户实测标签（非规格书样例）：

```
E28068940000502244813C7D
```

完整通知帧约 **28 字节**（Tag TLV 长度 `0x11`，比规格书示例 `0x17` 短，**无 Time TLV**）。解析逻辑在 `gateway/protocol/frames.py` 已兼容。

示例帧（十六进制）：

```
52 46 02 00 00 80 00 13 50 11 01 0C E2 80 68 94 00 00 50 22 44 81 3C 7D 05 01 99 78
```

---

## 3. 协议要点 (YZ-M40)

```
帧头 'RF' (52 46) | Type | Addr(2B) | Code | ParamLen(2B) | Parameters(TLV...) | Checksum
```

| Type | 含义 |
|------|------|
| 0x00 | 命令（主机→模块） |
| 0x01 | 响应 |
| 0x02 | 通知（模块主动上报，**读卡数据在此**） |

| Code | 含义 |
|------|------|
| 0x21 | 开始连续盘存 |
| 0x22 | 单次盘存 |
| 0x23 | 停止盘存 |
| 0x40 | 查询版本 |
| **0x80** | **标签上传（通知）** |

标签通知内 TLV：`0x50`(Tag) → `0x01`(EPC) + `0x05`(RSSI，1 字节有符号)。

校验和：从 Header 到 Parameters 末字节求和，再 `~sum + 1`（见 `calculate_checksum()`）。

---

## 4. 关键代码与职责

| 路径 | 职责 |
|------|------|
| `gateway/protocol/frames.py` | 帧编解码、TLV、`FrameBuffer`（`feed` / `push`） |
| `gateway/protocol/commands.py` | 构建 0x21/0x23/0x40 等命令 |
| `gateway/rfid_reader.py` | 串口 `read_available()` 非阻塞 drain；连接时可选发 0x21 |
| `gateway/service.py` | asyncio 后台轮询；**有标签时不 sleep**，连续读 |
| `gateway/serial_port.py` | `read_available()` 用 `in_waiting`，避免空读阻塞 200ms |
| `backend/core/lifespan.py` | Gateway + 看门狗；`create_presence_pending_action()`；bootstrap 自网关就绪起算 |
| `backend/core/events.py` | 进程内 EventBus（含 `unsubscribe`） |
| `backend/services/presence_watchdog.py` | 单读卡区 appear/disappear 去抖；bootstrap 期间 tick 不判离开 |
| `backend/services/epc_binding.py` | 统一 EPC → 格位 / 非标物件 / 料盒 |
| `backend/services/operation_service.py` | 看门狗待确认、**非标手动借还**（`manual_asset_*`）、料盒状态同步 |
| `backend/services/inventory_manage_service.py` | **标签绑定/换绑/解绑**、删除库存 |
| `backend/services/bom_service.py` | **BOM CSV 解析**、导入、库存分析与格位定位 |
| `backend/services/inventory_service.py` | 料盒/库存/入库绑定；`inventory_operations` 列表 |
| `backend/db/migrate.py` | 旧库自动 `ALTER TABLE` 补列（`entity_type`、`status`、`user_name` 等） |
| `backend/api/v1/` | REST：`bins`、`components`、`categories`、`slots`、`inventory`、`assets`、`boms`、`rfid` |
| `frontend/components/presence_confirm.py` | **出库/入库确认弹窗**（使用人/项目、消耗数量） |
| `frontend/components/shelf_grid.py` | 货柜格位网格；`pending_checkout`/`checked_out` 等着色 |
| `frontend/components/asset_confirm.py` | **非标物件读卡借还弹窗** |
| `frontend/pages/dashboard.py` | 左栏：料盒货柜 + 非标物件；右栏操作记录（标题/内容上下排） |
| `frontend/pages/inventory_bom.py` | **BOM 分析**：CSV 预览/导入、缺口表、货柜格位高亮 |
| `frontend/pages/inventory_operations.py` | **操作记录管理页**（筛选、待确认、清空） |
| `frontend/pages/inventory.py` | **库存与标签管理**（料盒物料/非标物件/标签三区列表、编辑/删除、标签操作） |
| `frontend/pages/inventory_register.py` | 入库绑定；物料按**料号**展示；`bind_type`；`?epc=` 预填 |
| `frontend/constants/bin_status.py` | 料盒状态中文标签与颜色 |
| `frontend/services/api_client.py` | httpx 复用连接；`resolve_api_base_url()` |
| `frontend/services/global_inventory_events.py` | **全页 RFID 监听**：`navbar()` 挂载；出入库/借还/未登记标签弹窗 + pending 轮询 |
| `frontend/services/event_listener.py` | EventBus → NiceGUI 回调（由 global hub 使用） |
| `frontend/services/rfid_listener.py` | 入库/库存页 TAG_READ 局部订阅（听卡填 EPC） |
| `scripts/test_rfid_serial.py` | **独立串口测试 CLI**（调试硬件首选） |
| `scripts/check_rfid_health.py` | 配置 + 串口 + API 一键检查 |
| `main.py` | NiceGUI 挂载 + uvicorn；端口冲突自动 fallback |

---

## 5. ⚠️ 已踩坑（必读）

### 5.1 `FrameBuffer.feed()` vs `push()` — 监听丢数据的根因

**问题**：`test_rfid_serial.py` 的 `monitor` 曾写成：

```python
self._parser.feed(chunk)              # 消费并移除通知帧，返回 tags 但未使用
for frame, raw in drain_all_frames():  # 缓冲区已空 → 永远无输出
```

**现象**：读卡器指示灯闪、普通串口助手能读到数据，本程序无任何输出。

**修复**：使用 `push_and_drain()` = `buffer.push(chunk)` + `drain_all_frames()`，**不要**在需要打印原始帧/全部帧时先调用 `feed()`。

**注意分工**：

- `feed()` — 适合 **gateway** 只要 `RfidTag` 列表的场景（`rfid_reader.poll_tags()`）
- `push()` + 手动 drain — 适合 **测试脚本** 需要打印完整帧/响应帧的场景

### 5.2 主程序网关曾收不到标签

**原因**：单次小 buffer 读取 + 200ms 间隔，通知帧被漏读。

**修复**（`gateway/rfid_reader.py`）：512B chunk + `read_available()` 非阻塞；默认 `RFID_READ_INTERVAL_MS=20`。

### 5.3 串口独占 (PermissionError 13)

Windows 下一个 COM 口只能被一个进程打开。冲突来源：

- PyCharm 同时跑多个 `main.py`
- `test_rfid_serial.py` 与 `main.py` 同时运行
- PyCharm Serial Monitor / 其他串口助手

**处理**：只保留一个占用 COM 的进程；调试硬件时先停 `main.py`。

### 5.4 `.env` 配置曾导致网关不工作

| 错误配置 | 后果 |
|----------|------|
| `RFID_ENABLED=false` | 主程序不启动网关 |
| `RFID_SERIAL_PORT=COM3` | COM3 是蓝牙口，非 USB 模块 |
| `RFID_AUTO_START_INVENTORY=false` 且模块未在硬件侧读卡 | 主程序不发 0x21，可能无标签上报 |

**推荐 `.env`（主程序需主动盘存、COM11）**：

```ini
RFID_SERIAL_PORT=COM11
RFID_BAUD_RATE=115200
RFID_ENABLED=true
RFID_AUTO_START_INVENTORY=true
RFID_READ_INTERVAL_MS=20
RFID_PRESENCE_ENABLED=true
RFID_PRESENCE_APPEAR_COUNT=2
RFID_PRESENCE_DISAPPEAR_COUNT=6
RFID_PRESENCE_TICK_MS=200
RFID_PRESENCE_MISS_GRACE_MS=1200
RFID_PRESENCE_BOOTSTRAP_MS=5000
DEBUG=false
APP_PORT=8765
```

若模块已在硬件侧持续读卡且与 0x21 冲突，可将 `RFID_AUTO_START_INVENTORY=false`。

### 5.5 启动入口

- `ui.run_with()` **不接受** `host`/`port`；须在之后调用 `uvicorn.run()`
- `DEBUG=true` 热重载会重启进程，可能锁死串口
- Web 默认端口 **8765**（8080 常被占用）；`config/network.py` 有 fallback
- `ApiClient` 优先用浏览器请求的 `host:port`（`resolve_api_base_url()`），减轻端口 fallback 不一致

### 5.6 NiceGUI 页面一直加载、无内容（🚨 重要）

**问题**：在 `@ui.page` 异步函数末尾连续 `await client.get_*()`（加载货架、表格、RFID），NiceGUI 需等全部 HTTP 完成才结束页面渲染；自调用 API 时易卡住，浏览器一直转圈。

**现象**：只显示标题/导航，下方无表单、无按钮（曾出现在 `/`、`/inventory/register`）。

**修复模式**（后续新页面请沿用）：

1. **先同步渲染**页面骨架（标题、按钮、容器、占位 spinner）
2. 用 **`ui.timer(0.05, load_fn, once=True)`** 在后台拉 API 并填充 UI
3. 周期性任务优先 **`EventBusListener`** 订阅；HTTP 轮询仅作兜底（仪表盘操作记录 2s）

```python
# ✗ 易卡死
await load_shelf()
await load_table()

# ✓ 推荐
ui.timer(0.05, load_shelf, once=True)
```

### 5.7 货架区定时刷新闪烁

**问题**：`load_shelf()` 开头 `container.clear()`，API 未完成时网格空白。

**修复**：`@ui.refreshable` + 先拉数据再 `.refresh()`；数据未变时用 snapshot 跳过重建。

### 5.8 RFID 到 UI 延迟偏高

**原因**：串口 `read()` 空等 200ms；网关 50ms sleep；**先写 DB 再广播**；前端 HTTP 300ms 轮询。

**修复**（2026-06-30）：

1. `serial_port.read_available()` — 无数据立即返回  
2. `lifespan` — EPC 查表后 **立即 `event_bus.publish`**，入库 `asyncio.create_task`  
3. `frontend/services/rfid_listener.py` — 仪表盘/入库页 **进程内订阅**（同进程，比 WebSocket 更简单）  
4. 默认 `RFID_READ_INTERVAL_MS=20`；有标签时网关 loop 不 sleep  

### 5.9 NiceGUI 仪表盘 500 错误

**问题**：`ui.log().classes("...", style="height: 240px")` — `.classes()` 不接受 `style` 参数。

**修复**：

```python
ui.log(max_lines=100).classes("w-full q-px-md").style("height: 240px")
```

### 5.10 argparse 子命令参数顺序

`-p COM11` 作为子命令参数（`parents=[conn]`）：

```powershell
python scripts/test_rfid_serial.py version -p COM11   # ✓
python scripts/test_rfid_serial.py monitor -p COM11 -d 15
```

### 5.11 粘包 / 半包

串口一次 `read()` 可能读到：半帧 + 完整帧、多帧拼接、帧前垃圾字节。必须用 `52 46` 找帧头，再按 `ParamLen` 算长度，**不可按固定长度切包**。

### 5.12 看门狗启动误报（bootstrap）

**现象**：启动时标签已在读卡垫上，bootstrap 结束后误触发「归还」或立刻判「离开」。

**机制**（2026-06-30 修订）：

- `RFID_PRESENCE_BOOTSTRAP_MS`（默认 **5000**）从 **RFID 网关就绪后**开始计时，非应用进程启动瞬间
- bootstrap 期间：`on_tag` 静默吸收在场 EPC；**`tick()` 完全不处理离开**
- `end_bootstrap()` 时清零 miss 计数并刷新 `last_seen`

**建议**：演示时等日志出现 `RFID presence watchdog bootstrap finished` 后再移动标签。

### 5.14 全页 RFID 弹窗（global_inventory_events）

**现象**：仅在仪表盘 `/` 能弹出看门狗出库/入库确认；切到 `/inventory` 等页面无反应。

**原因**：`EventBusListener` 原先只在 `dashboard.py` 注册，NiceGUI 切页后旧页 `on_disconnect` 会 **unsubscribe**，事件不再送达 UI。

**修复**（2026-06-30）：

1. 新增 `frontend/services/global_inventory_events.py`：`ensure_global_inventory_events()` 按 **client.id** 单例挂载。
2. `navbar()` 调用 `ensure_global_inventory_events()`，所有带顶栏页面共享同一 listener。
3. 弹窗组件：`presence_confirm`（出库/入库）、`asset_confirm`（非标借还）、未登记标签 → register。
4. 每 5s 轮询 `pending` 操作，避免漏弹窗。
5. 页面通过 `on_confirmed("page_key", cb)` 注册局部刷新，切页时 `off_confirmed` 清理。
6. **入库绑定页**：`_is_register_route()` 下不弹未登记对话框；跳转 register 或页内听卡时对 EPC `snooze_unbound_epc()`（默认 1h），避免重复干扰填表。

**测试**：`tests/test_frontend/test_global_inventory_events.py`（Mock NiceGUI，测 EventBus 路由与 snooze）。

---

### 5.13 出库确认弹窗显示不全

**原因**：NiceGUI 中 `ui.label` / `ui.column` 在 `ui.dialog()` **外**创建，再引用进 card，导致只有部分内容进入弹窗。

**修复**：`presence_confirm.py` 将所有控件建在 `with dialog:` / `with ui.card():` 内部；卡片设 `max-height: 90vh; overflow-y: auto`。

### 5.14 旧库缺列导致 API 500

**现象**：仪表盘「操作记录 API 异常」，`no such column: inventory_operations.entity_type`。

**原因**：`create_all` 不修改已有表结构。

**修复**：`backend/db/migrate.py` 在启动时 `ALTER TABLE` 补列；仍异常时可 `python scripts/init_db.py --drop` 重建。

### 5.15 新增表/列需重启应用

`assets`、`inventory_operations` 新字段由 `create_all` + `migrate` 处理。改 schema 后须**重启 `main.py`**；pytest 用内存库（`tests/conftest.py`）。

---

## 6. 调试流程（标准操作）

```powershell
cd D:\smart_ee_inventory
.\.venv\Scripts\Activate.ps1

# 1. 找端口
python scripts/test_rfid_serial.py list

# 2. 独占串口测试（先停 main.py）
python scripts/test_rfid_serial.py version -p COM11
python scripts/test_rfid_serial.py monitor -p COM11 -d 15 --no-dedupe

# 2b. 无硬件：TCP 模拟 YZ-M40 开发板（与 main.py 可同时调试）
python scripts/simulate_rfid_board.py
# 另开终端，.env 设 RFID_SERIAL_PORT=socket://127.0.0.1:9276 后 python main.py
# 在模拟器终端: hold r10k  → 持续上报电阻标签；release all → 模拟拿开

# 3. 健康检查（需释放 COM 或停其他进程）
python scripts/check_rfid_health.py

# 4. 初始化/重建数据库（可选）
python scripts/init_db.py

# 5. 启动完整应用
python main.py
```

**Web 页面**：

| 路径 | 功能 |
|------|------|
| `/` | **仪表盘**：上=货柜网格，下=非标物件表；读卡弹窗借还 |
| `/bins` | 料盒 CRUD、料盒级 EPC 绑定 |
| `/slots` | 格位网格、格位 EPC/标签/状态编辑 |
| `/inventory` | **库存与标签管理**：统计卡片；三区折叠列表（编辑/删除、标签绑定） |
| `/inventory/register` | 入库绑定；物料下拉显示**元件名称**（`name`）；`?epc=` 预填 |
| `/inventory/manage` | 重定向至 `/inventory`（标签管理已合并） |
| `/inventory/bom` | **BOM 分析**：CSV 导入/预览、库存匹配、格位高亮 |
| `/inventory/operations` | **操作记录管理**（筛选、待确认、清空） |

---

## 7. 业务闭环现状（2026-06-30）

### ✅ 已完成

| 能力 | 实现位置 |
|------|----------|
| RFID 事件入库 | `lifespan` → `record_rfid_event()` |
| EPC 统一解析 | `epc_binding.lookup_epc_binding()`（格位 → 非标 → 料盒） |
| **双类型库存** | `assets` 表；`bind_type: slot_material \| asset` |
| **单天线看门狗** | 仅 **格位物料**；`create_presence_pending_action()`（非标 EPC 忽略） |
| **料盒状态** | `checkout_unregistered`（出库未登记）· `return_unregistered`（未登记归还） |
| **非标借还** | 仪表盘读卡 → `asset_confirm` 弹窗 + `POST /assets/take-out|return` |
| **标签管理** | `bind-tag` / `rebind-tag` / `unbind-tag` / `DELETE .../manage/...` |
| **待确认出库** | 弹窗填**使用人、使用项目** → `POST .../confirm` → 库存 -1 |
| **待确认入库** | 弹窗填**消耗数量**（默认 0）→ 库存 `+1 - 消耗` |
| 格位/料盒状态 | `occupied`（**在库**）/ `checkout_unregistered` / `return_unregistered` / `pending_*` / `checked_out` |
| **库存操作记录** | `inventory_operations`（`status`: pending/confirmed/cancelled） |
| **操作记录页** | `/inventory/operations`；`DELETE /inventory/operations` 清空 |
| 仪表盘 | `PRESENCE_CONFIRM_REQUIRED` 弹窗 + 已确认操作日志（**任意页面均可弹窗**，仪表盘负责日志展示） |
| 未登记标签引导 | **全页**弹窗 → `/inventory/register?epc=` |
| 入库绑定 | `POST /inventory/register`；料盒物料或非标物件 |
| **BOM 分析** | `POST /boms/preview`、`POST /boms/import`、`GET /boms/{id}/analysis`；演示 CSV：`scripts/demo_bom.csv` |

**BOM 演示**（需种子数据 `TEST-R-10K` 等）：

1. 打开 `/inventory/bom`，默认已填演示 CSV
2. 点击 **预览分析** → 查看需求/可用/缺口与各格位
3. 选择料盒 `BIN-TEST` → 货柜视图**蓝色高亮** BOM 相关格位
4. **导入并保存** 可将 BOM 写入 `boms` / `bom_lines` 表

**看门狗演示**（`BIN-TEST` 已绑定**格位物料**标签）：

1. 标签**拿离** → 弹出**出库确认** → 料盒状态 **出库未登记** → 确认后库存 -1
2. 标签**放回** → 弹出**归还确认** → 可填消耗 → 库存按规则调整
3. **未绑定**标签 → 仪表盘入库引导（不改库存）

**非标物件**（如 Jetson `AST-0001`）：

1. 首次：`/inventory/register` 选非标物件 + 读卡登记
2. 借出/归还：在**仪表盘**读卡 → 弹窗确认（**不经过看门狗**）

**标签管理**（`/inventory` 页面「标签管理」区）：

1. 已有库存无 EPC → **绑定标签**
2. 换物理标签 → **换绑**；仅清除 EPC → **解绑**
3. 不再需要该条库存 → **删除**（料盒物料/非标列表行内亦可删除）

**入库绑定**：

1. `/inventory/register` 选择 **料盒物料** 或 **非标物件**
2. 料盒物料：选料盒、格位、**物料（元件名称）**、数量 + EPC
3. 非标物件：填名称/类别 + EPC（编号可自动生成）

### ❌ 尚未实现 / 待细化

| 能力 | 说明 |
|------|------|
| 库存数量 PATCH | 无通用改数量 API（删除/重入库/register 代替） |
| 格位物料手动出库 UI | 除看门狗弹窗/register 外无独立表单 |
| 新建料盒自动生成格位 | 新建后网格显示「未配置」 |
| BOM 领料出库 | 仅分析与定位，不自动扣库存 |
| 64 路射频复用 | 远期 |
| ESP32 WiFi 读卡 | 方案见 `docs/ESP32_WIFI_RFID.md`，尚未实现 |
| Alembic 迁移 | 仅 `create_all` + `migrate.py` 补列 |

数据流（当前）：

```
串口 → Gateway → lifespan
         ├→ TAG_READ → event_bus → 仪表盘（未登记弹窗）
         ├→ PresenceWatchdog → create_presence_pending_action()  [仅 slot_material]
         │                      → PRESENCE_CONFIRM_REQUIRED → 确认弹窗
         ├→ 非标借还：POST /assets/take-out|return（手动读卡，不经看门狗）
         ├→ 标签管理：POST /inventory/manage/* 
         │                      → POST .../confirm → INVENTORY_OPERATION
         └→ rfid_events 异步入库（调试）
```

---

## 8. 数据库速查

**方案**：SQLite 文件 `./data/inventory.db`，SQLAlchemy 2.x **异步**（`aiosqlite`）。

| 项目 | 说明 |
|------|------|
| 连接串 | `sqlite+aiosqlite:///./data/inventory.db`（`.env` → `DATABASE_URL`） |
| 模型 | `backend/models/models.py`（**12 表**，含 `assets`、`inventory_operations`） |
| 迁移 | 启动时 `migrate.py` 补列；重建：`python scripts/init_db.py --drop` |
| 种子 | `scripts/seed_data.py`：**3 物料**、`BIN-TEST` 1×3 格位、演示非标 `AST-0001`（Jetson） |

**EPC 绑定（种子数据）**：三个现场标签分别绑定如下：

| 类型 | 位置 | 条目 | EPC |
|------|------|------|-----|
| 料盒物料 | T01-1-1 | 测试电阻 10kΩ | `E28011704000021CCCF9A58E` |
| 料盒物料 | T01-1-2 | 陶瓷电容 100nF | `E28068940000502244813C7D` |
| 料盒物料 | T01-1-3 | 红色 LED | （无标签，仅库存） |
| 非标物件 | AST-0001 | Jetson Nano 开发板 | `E28011704000021CCCF9A59E` |

重建库：`python scripts/init_db.py --drop`

---

## 9. 测试

```powershell
pytest                    # 当前约 38 例
pytest tests/test_services  # 看门狗、操作确认、标签管理、EPC 绑定、种子数据
python scripts/smoke_test.py
python scripts/verify_seed.py --strict  # 需本地 inventory.db
```

新增协议解析时，在 `tests/test_gateway/test_frames.py` 加入用户真实帧 hex 作为回归用例。

---

## 10. 文档索引

| 文件 | 内容 |
|------|------|
| `README.md` | 快速开始、环境变量、API 列表 |
| `docs/PROJECT_SUMMARY.md` | 阶段总结与路线图 |
| **`docs/RFID_MULTIPLEXER_WATCHDOG.md`** | **64 路（远期）+ 单天线演示（§3）** |
| **`docs/ESP32_WIFI_RFID.md`** | **ESP32 + WiFi 读卡** 可行性与需求 |
| **`docs/MEMO.md`** | **本文 — 踩坑与硬件实测** |
| `.env.example` | 配置模板 |

---

## 11. 变更日志（备忘）

| 日期 | 变更 |
|------|------|
| 2026-06-29 | 项目脚手架、YZ-M40 协议、SQLite 10 表 |
| 2026-06-29 | 修复 `main.py` ui.run_with + uvicorn；默认端口 8765 |
| 2026-06-29 | `test_rfid_serial.py`：`push_and_drain` 修复监听丢帧 |
| 2026-06-29 | 用户验证：monitor 可显示 EPC `E28068940000502244813C7D` |
| 2026-06-29 | 网关批量 drain + 自动 0x21；RFID 事件入库 + EPC 查表 |
| 2026-06-29 | 仪表盘 HTTP 轮询 RFID 事件（替代未接 WebSocket） |
| 2026-06-30 | **P1**：格位/库存 API；料盒 CRUD UI；格位网格；库存页修复 |
| 2026-06-30 | 修复仪表盘 500：`.classes().style()` 写法 |
| 2026-06-30 | API 测试扩展至 slots/inventory（共 ~18 例 pytest） |
| 2026-06-30 | **入库绑定**：`POST /inventory/register` + `/inventory/register` 页 |
| 2026-06-30 | `GET /api/v1/rfid/status`；`ApiClient.resolve_api_base_url()` |
| 2026-06-30 | 修复 NiceGUI 页面无限加载：timer 异步加载（`/`、`/inventory/register`） |
| 2026-06-30 | **仪表盘货架视图**：`shelf_grid.py`，格位状态/内容物网格 |
| 2026-06-30 | 同步更新 `README.md`、`PROJECT_SUMMARY.md` 文档 |
| 2026-06-30 | RFID 低延迟：先广播后入库、`rfid_listener`、非阻塞串口 |
| 2026-06-30 | 货架刷新防闪烁：`@ui.refreshable` + snapshot |
| 2026-06-30 | **仪表盘双栏布局**；`navbar` 美化 |
| 2026-06-30 | 货柜视图：**搜索高亮**、元件名为标题、格位不显示 EPC 全文 |
| 2026-06-30 | **看门狗**：`presence_watchdog` + `inventory_operations`（初版自动 ±1，后改为待确认） |
| 2026-06-30 | 仪表盘改显示**库存操作记录**；`GET /inventory/operations` |
| 2026-06-30 | 未登记标签弹窗 → `/inventory/register?epc=`；`EventBusListener` |
| 2026-06-30 | `RFID_PRESENCE_*` 配置；pytest 扩展至 ~27 例 |
| 2026-06-30 | **双类型库存**：`assets` + `bind_type`；`epc_binding` |
| 2026-06-30 | **待确认出入库**：弹窗（使用人/项目、消耗）+ `operation_service` |
| 2026-06-30 | **操作记录页** `/inventory/operations`；清空 API |
| 2026-06-30 | bootstrap 修复（网关就绪后 5s；tick 期间不判离开） |
| 2026-06-30 | `migrate.py` 旧库补列；pytest 内存库 ~32 例 |
| 2026-06-30 | 料盒状态 **出库未登记**（`checkout_unregistered`） |
| 2026-06-30 | 非标物件改 **手动读卡借还**（`/asset-ops`）；看门狗仅格位物料 |
| 2026-06-30 | **标签管理**：绑定/换绑/解绑/删除库存 + `/inventory/manage` |
| 2026-06-30 | pytest 扩展至 ~38 例 |
| 2026-06-30 | **BOM 分析**：`bom_service` + `/api/v1/boms` + `/inventory/bom`；`scripts/demo_bom.csv` |
| 2026-06-30 | 仪表盘移除右下角重复链接（入库绑定/操作记录/料盒管理），统一顶栏导航 |
| 2026-06-30 | **全页 RFID**：`global_inventory_events.py` + `navbar` 挂载；修复非仪表盘页无法出入库确认 |
| 2026-06-30 | 入库绑定页：物料下拉显示元件 **name**（如「红色 LED」）；区块标题去掉序号 |
| 2026-06-30 | **库存页合并**：`/inventory` 集成标签管理；`/inventory/manage` 重定向；三区折叠列表 + 统计卡片 |
| 2026-06-30 | 库存页：料盒/非标行内**删除**；标签管理改为表格列表；`PATCH` 手动编辑记入操作记录 |

---

*下次接手时：先读本文 §5 踩坑，再跑 `test_rfid_serial.py monitor`，确认 COM 口与 EPC，最后动业务代码。*
