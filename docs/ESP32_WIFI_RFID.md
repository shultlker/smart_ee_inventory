# ESP32 + WiFi RFID 读卡方案 — 可行性与需求草案

> 文档版本：2026-06-30  
> 状态：**需求分析 / 未实现**  
> 关联：`gateway/`（当前 PC 串口网关）、`backend/core/lifespan.py`、`docs/MEMO.md`

---

## 1. 背景与动机

### 1.1 现状

当前架构为 **PC 直连 YZ-M40 UHF 模块（USB 虚拟串口）**：

```
YZ-M40 ──USB/COM──► gateway/GatewayService ──► lifespan._on_gateway_event
                                              ├─ EventBus (TAG_READ)
                                              ├─ PresenceWatchdog
                                              └─ rfid_events 入库
```

优点：协议已在 Python 完整实现（`gateway/protocol/`）、延迟低、调试方便。  
缺点：

| 问题 | 说明 |
|------|------|
| USB 线缆长度 | 读卡器必须靠近 PC，料盒/货架部署不灵活 |
| COM 口独占 | 测试脚本与主程序不能同时打开串口 |
| 单机绑定 | 每套料盒若需独立读卡区，需多 USB 口或多 PC |
| 电气环境 | 工控机/笔记本与天线区域分离时布线成本高 |

### 1.2 目标架构（提议）

将 **RFID 模块 + 串口协议栈** 下沉到 **ESP32 边缘节点**，通过 **WiFi** 将标签事件推送到 PC 上的 Python 服务：

```
┌──────────────────── 料盒/读卡区（边缘） ────────────────────┐
│  UHF 模块 ◄─UART─► ESP32 (固件)                            │
│                      │ WiFi (TCP/UDP/MQTT/HTTP)            │
└──────────────────────┼─────────────────────────────────────┘
                       ▼
              ┌────────────────────┐
              │  PC: FastAPI 应用   │
              │  WifiRfidGateway   │  ← 替代或并存 GatewayService
              │  (同 EventBus API) │
              └────────────────────┘
```

**核心原则**：PC 端业务层（看门狗、入库绑定、仪表盘）**尽量不改动**，仅替换「标签事件来源」。

---

## 2. 可行性结论

| 维度 | 评估 | 说明 |
|------|------|------|
| **技术可行性** | ✅ **高** | ESP32 双核 + 硬件 UART 可稳定驱动 115200 8N1；WiFi 推送 JSON 事件成熟 |
| **协议迁移** | ✅ **可行** | YZ-M40 帧格式简单（`52 46` 头 + TLV）；可在 ESP32 用 C/C++ 移植 `frames.py` 核心逻辑，或继续发原始 hex 由 PC 解析（不推荐，占带宽） |
| **延迟** | ⚠️ **可接受** | WiFi 局域网通常 +5～30 ms；看门狗 tick 200 ms、appear/disappear 去抖，**一般足够** |
| **可靠性** | ⚠️ **需设计** | WiFi 断线、UDP 丢包、ESP32 重启需重连与事件序号；看门狗 miss 宽限已 1200 ms，可吸收短暂抖动 |
| **多读卡器** | ✅ **更易扩展** | 每料盒一台 ESP32，带 `reader_id` / `cabinet_id` 上报，比 USB 集线器清晰 |
| **开发成本** | ⚠️ **中等** | 需固件开发 + PC 网关抽象 + 联调；约 **2～4 人周**（单天线 MVP） |
| **与 64 路复用** | ✅ **正交** | 远期 64 路若用 STM32/FPGA 复用，仍可经 ESP32 或以太网网关上报；本方案是单天线分布式的 stepping stone |

**结论**：在**局域网单机 PC 部署**前提下，**ESP32 控 YZ-M40 + WiFi 上报**是合理演进路径，建议以 **MVP 单读卡器** 验证后再复制到多料盒。

---

## 3. 硬件方案

### 3.1 推荐 BOM（单节点）

| 部件 | 建议 | 备注 |
|------|------|------|
| MCU | ESP32-WROOM-32 或 ESP32-S3 | 需 1× UART；S3 余量更大 |
| RFID | 现有 **YZ-M40** 模块 | 3.3V/5V 电平需对照模块手册 |
| 连接 | ESP32 UART1 ↔ M40 TX/RX/GND | 波特率 **115200 8N1**，与现网一致 |
| 供电 | 5V 适配器或 USB | 模块峰值电流需确认 |
| 天线 | 随模块 | 安装位置影响 RSSI，与现演示一致 |

### 3.2 接线要点

- M40 与 ESP32 **共地**
- 若模块为 5V TTL，ESP32 侧 RX 需分压或电平转换
- **不要** 同时接 PC USB 与 ESP32 UART（模块仅一组串口）

### 3.3 可选增强

- **W5500 以太网**：WiFi 干扰大时用有线
- **外部看门狗芯片**：极端环境防死机
- **状态 LED**：连接 / 盘存 / 故障

---

## 4. 软件架构需求

### 4.1 分层目标

```
┌─────────────────────────────────────────────────────────┐
│ 应用层（不变）                                            │
│  presence_watchdog · epc_binding · dashboard · register   │
├─────────────────────────────────────────────────────────┤
│ 事件抽象层（新增）                                        │
│  RfidSource Protocol: async iter TagReadEvent             │
│  实现体: SerialGatewaySource | WifiEsp32Source          │
├─────────────────────────────────────────────────────────┤
│ 传输层                                                    │
│  串口 pyserial          |  WiFi TCP/WS/MQTT 客户端        │
├─────────────────────────────────────────────────────────┤
│ 边缘固件（新增）                                          │
│  UART 读帧 · 0x21 盘存 · JSON 上报 · OTA(可选)            │
└─────────────────────────────────────────────────────────┘
```

### 4.2 PC 端改造范围（建议）

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 定义 `TagReadEvent` 统一结构 | P0 | `epc`, `rssi`, `antenna`, `reader_id`, `ts_ms` |
| 抽象 `RfidGateway` 接口 | P0 | `start()` / `stop()` / 回调同 `GatewayService._on_event` |
| 实现 `WifiEsp32Gateway` | P0 | 连接 ESP32 服务端口，解析 JSON 行或 WebSocket 帧 |
| `lifespan.py` 按配置选择网关 | P0 | `RFID_TRANSPORT=serial|wifi` |
| 配置项扩展 | P0 | 见 §6 |
| `GET /api/v1/rfid/status` 扩展 | P1 | 返回 `transport`, `reader_id`, `wifi_rssi`, `last_seen` |
| 兼容 `test_rfid_serial.py` | P1 | 串口模式保留，便于实验室调试 |
| 多 reader 路由 | P2 | `reader_id` → `cabinet_id` 映射表 |

**不应改动**（若抽象正确）：

- `presence_watchdog.py` 去抖逻辑
- `operation_service.create_presence_pending_action()`
- 前端 `EventBusListener` / `rfid_listener`

### 4.3 ESP32 固件需求

| 功能 | 优先级 | 说明 |
|------|--------|------|
| WiFi STA 连接 | P0 | SSID/密码可 NVS 配置或配网（SmartConfig/AP） |
| UART 驱动 M40 | P0 | 上电发 `0x21` 开始盘存（可配置） |
| 帧解析 | P0 | 移植 checksum + TLV EPC/RSSI 提取 |
| 事件上报 | P0 | 每标签一帧 JSON + 换行，或 WebSocket binary |
| 心跳 | P0 | 每 5 s `{"type":"heartbeat","uptime_ms":...}` |
| 断线重连 | P0 | WiFi 断开后自动重连，盘存不中断 |
| 配置下发 | P1 | PC 下发 `start_inventory` / `stop_inventory` |
| OTA | P2 | 现场升级 |
| 本地缓存 | P2 | WiFi 断时环形缓冲，恢复后批量补发（带 `seq`） |

---

## 5. 通信协议草案（PC ↔ ESP32）

### 5.1 推荐：TCP + NDJSON（newline-delimited JSON）

- ESP32 为 **客户端**，主动连接 PC `RFID_WIFI_HOST:RFID_WIFI_PORT`（默认 `8766`）
- 每行一条 JSON，UTF-8

**标签事件（ESP32 → PC）**：

```json
{"type":"tag","reader_id":"BIN-TEST-1","epc":"E28068940000502244813C7D","rssi":-89,"antenna":1,"ts_ms":1712345678901}
```

**心跳**：

```json
{"type":"heartbeat","reader_id":"BIN-TEST-1","uptime_ms":120000,"wifi_rssi":-55}
```

**命令（PC → ESP32，可选）**：

```json
{"type":"cmd","action":"stop_inventory"}
{"type":"cmd","action":"start_inventory"}
```

### 5.2 备选方案对比

| 方案 | 优点 | 缺点 |
|------|------|------|
| **TCP NDJSON** | 实现简单、易调试、顺序可靠 | 需处理粘包/半包（按行切分即可） |
| **WebSocket** | 与现有 `/ws/bin-status` 风格统一 | ESP32 库资源占用略高 |
| **MQTT** | 多节点、QoS、Retain | 需 Broker；单机略重 |
| **HTTP POST** | 极简 | 高频标签时开销大，不推荐盘存 |

**MVP 建议**：TCP NDJSON，与 WebSocket 广播层分离（ESP32 → PC 接入层 → 现有 EventBus）。

### 5.3 与现有 `TAG_READ` 载荷对齐

当前 `lifespan._on_gateway_event` 期望：

```python
{"epc": str, "rssi": int | None, "antenna": int | None}
```

WiFi 网关应在注入 EventBus 前映射为相同字段；`reader_id` 可作为扩展字段供未来多天线路由，**MVP 可忽略**。

---

## 6. 配置需求（.env 扩展草案）

```ini
# 传输方式: serial | wifi
RFID_TRANSPORT=serial

# --- WiFi 模式（ESP32 连 PC）---
RFID_WIFI_ENABLED=false
RFID_WIFI_LISTEN_HOST=0.0.0.0
RFID_WIFI_LISTEN_PORT=8766
RFID_WIFI_READER_ID=default

# --- 串口模式（保持现有）---
RFID_SERIAL_PORT=COM11
RFID_BAUD_RATE=115200
...
```

固件侧（NVS / `config.json`）：

```ini
WIFI_SSID=...
WIFI_PASSWORD=...
SERVER_HOST=192.168.1.100
SERVER_PORT=8766
READER_ID=BIN-TEST-1
BAUD_RATE=115200
AUTO_START_INVENTORY=true
```

---

## 7. 非功能需求

| 类别 | 指标（建议） |
|------|----------------|
| 端到端延迟 | 标签进入场 → PC 收到事件 **< 100 ms**（LAN） |
| 吞吐 | 单读卡器 **≥ 20 tags/s** 突发（盘存场景足够） |
| 可用性 | WiFi 断线 10 s 内恢复后看门狗不误触发大批量假出库 |
| 安全 | MVP：局域网明文 TCP；量产：TLS 或 WPA3 + 令牌 |
| 可维护性 | PC 端 `RFID_TRANSPORT` 一键切换；串口工具仍可独立测 M40 |

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| WiFi 抖动导致虚假 disappear | 误弹出库确认 | 保持/略增 `RFID_PRESENCE_MISS_GRACE_MS`；ESP32 端短时聚合 |
| 重复上报同一 EPC | 看门狗重复计数 | PC 端与现网关一致：按 tick 去抖，非每帧触发 |
| 固件与 Python 协议漂移 | 解析失败 | 共用 golden test vectors（`tests/test_gateway/test_frames.py` hex） |
| ESP32 UART 缓冲溢出 | 丢标签 | 高波特率读空、标签回调极简、复杂逻辑放 PC |
| 双网关同时启用 | 重复事件 | 配置互斥；`RFID_TRANSPORT` 单选 |

---

## 9. 实施路线图（建议）

### Phase 0 — 验证（3～5 天）

- [ ] ESP32 串口打印 M40 盘存 EPC（Arduino / ESP-IDF）
- [ ] 与 `test_rfid_serial.py monitor` 对比 EPC 一致性

### Phase 1 — MVP（1～2 周）

- [ ] 固件：WiFi + TCP 客户端 + NDJSON 上报
- [ ] PC：`WifiEsp32Gateway` + `RFID_TRANSPORT=wifi`
- [ ] 仪表盘看门狗演示路径与串口模式行为一致
- [ ] `rfid/status` 显示 WiFi 连接状态

### Phase 2 — 生产化（2～3 周）

- [ ] 多 `reader_id` 与料盒绑定配置
- [ ] 断线缓冲与 `seq` 去重
- [ ] 配网流程 + 文档
- [ ] pytest：mock TCP 流注入 `TAG_READ`

### Phase 3 — 与远期 64 路关系

- 64 路射频开关仍可在 **一个** 边缘节点完成，对上仍走同一 WiFi 协议，仅 JSON 增加 `antenna` / `channel` 字段。

---

## 10. 验收标准（MVP）

1. PC 仅开 `RFID_TRANSPORT=wifi`，不接 USB 串口，可完成与现网相同的看门狗出库/入库演示（`BIN-TEST` 种子标签）。
2. `GET /api/v1/rfid/status` 显示 `connected: true` 且 `transport: wifi`。
3. WiFi 断开 5 s 再恢复后，盘存自动继续，无需重启 `main.py`。
4. `scripts/test_rfid_serial.py` 在串口模式仍可独立使用，互不干扰。

---

## 11. 参考代码锚点（当前仓库）

| 文件 | 迁移/复用要点 |
|------|----------------|
| `gateway/protocol/frames.py` | 帧解析、checksum → **固件 C 移植** |
| `gateway/protocol/commands.py` | `0x21`/`0x23` 命令字节 |
| `gateway/rfid_reader.py` | `poll_tags()` 语义 → 固件主循环 |
| `gateway/service.py` | `GatewayService._loop` → `WifiEsp32Gateway` 对等 |
| `backend/core/lifespan.py` | `_on_gateway_event` 入口保持不变 |
| `shared/constants.py` | `EventType.TAG_READ` |

---

## 12. 未决问题（需产品/硬件确认）

1. **每料盒一台 ESP32** 还是 **一台 ESP32 多 UART**？（决定 `reader_id` 模型）
2. M40 模块供电与天线是否随料盒移动？（影响 WiFi 天线布局）
3. 是否必须支持 **无 PC 局域网**（ESP32 AP 模式 + 平板）？当前需求文档假定 **PC 常驻**。
4. 是否需要 **加密**？实验室可明文，车间需评估。

---

*本文档为需求与可行性分析，不含固件与 `WifiEsp32Gateway` 实现。实现前建议先完成 Phase 0 硬件验证。*
