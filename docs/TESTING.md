# 测试与调试指南

> 适用代码：smart_ee_inventory v0.1.0

本文说明如何运行自动化测试、使用调试脚本，以及各关键组件的测试覆盖范围。

---

## 1. 快速开始

```powershell
cd D:\smart_ee_inventory
.\.venv\Scripts\Activate.ps1

# 冒烟测试（网关协议 + 核心服务 + 编辑 API，约 30 秒）
python scripts/smoke_test.py

# 全量 pytest
python -m pytest tests -q

# 校验本地 inventory.db 种子数据（需先 init_db）
python scripts/init_db.py --drop
python scripts/verify_seed.py --strict
```

测试默认使用**内存 SQLite**（`tests/conftest.py` 设置 `DATABASE_URL=sqlite+aiosqlite:///:memory:`），不会改动 `./data/inventory.db`。

---

## 2. 自动化测试结构

| 目录 | 覆盖组件 |
|------|----------|
| `tests/test_gateway/` | YZ-M40 帧解析/组帧、`BoardSimulator` 协议模拟 |
| `tests/test_services/` | 看门狗、操作确认、标签管理、BOM、EPC 绑定、种子数据、手动编辑 |
| `tests/test_api/` | REST API（bins/slots/inventory/assets/boms/rfid 等） |
| `tests/test_config/` | 网络/配置 |

### 关键组件 ↔ 测试文件

| 组件 | 测试 |
|------|------|
| `gateway/protocol/frames.py` | `test_frames.py` |
| `gateway/board_simulator.py` | `test_board_simulator.py` |
| `backend/services/epc_binding.py` | `test_epc_binding.py` |
| `backend/services/inventory_manage_service.py` | `test_inventory_manage.py` |
| `backend/services/inventory_edit_service.py` | `test_inventory_edit.py`, `test_inventory_edit_api.py` |
| `backend/services/bom_service.py` | `test_bom.py`, `test_bom_api.py` |
| `backend/services/presence_watchdog.py` | `test_presence_watchdog.py` |
| `backend/services/operation_service.py` | `test_operation_confirm.py`, `test_asset_manual_ops.py` |
| `scripts/seed_data.py` | `test_seed_data.py` |

---

## 3. 调试脚本

| 脚本 | 用途 |
|------|------|
| `scripts/init_db.py` | 建表 + 加载种子（`--drop` 清空重建） |
| `scripts/verify_seed.py` | 校验 `BIN-TEST` 三格库存与三枚 EPC 绑定 |
| `scripts/smoke_test.py` | 一键跑核心 pytest；可选 `--verify-seed` |
| `scripts/test_rfid_serial.py` | 真实 YZ-M40 串口：list / version / monitor |
| `scripts/simulate_rfid_board.py` | **无硬件**：TCP 模拟读卡器（默认 `127.0.0.1:9276`） |
| `scripts/check_rfid_health.py` | 串口连通 + 被动监听帧统计 |

### RFID 模拟器（推荐日常调试）

```powershell
# 终端 1
python scripts/simulate_rfid_board.py

# 终端 2 — .env
# RFID_SERIAL_PORT=socket://127.0.0.1:9276
python main.py

# 终端 1 交互
rfid> hold r10k
rfid> release all
rfid> emit jetson
```

预设别名：`r10k` / `c100n` / `jetson` → 种子库三枚 EPC。

核心逻辑在 `gateway/board_simulator.py`；CLI 在 `scripts/simulate_rfid_board.py`。

### 真实硬件串口

1. **先停** `main.py`（COM 口独占）
2. `python scripts/test_rfid_serial.py monitor -p COM11 -d 15`
3. 确认帧头 `52 46`、EPC 解析正常后再启主程序

详见 [MEMO.md §5](MEMO.md) 踩坑记录。

---

## 4. 编写新测试的约定

1. **服务层**：使用 `db_session` fixture，自行创建最小料盒/格位/物料，避免依赖文件库种子。
2. **API 层**：在 `db_session` 中 `commit()` 后，用 `TestClient(create_app())` 发请求。
3. **需要种子数据的 API 测试**：检测无数据时 `pytest.skip("need seed data")`（见 `test_bom_api.py`）。
4. **网关/协议**：不依赖数据库，纯 bytes 断言。
5. 运行单文件：`python -m pytest tests/test_services/test_epc_binding.py -v`

---

## 5. CI / 发布前检查清单

- [ ] `python scripts/smoke_test.py`
- [ ] `python -m pytest tests -q`（全量）
- [ ] 若改动种子： `python scripts/init_db.py --drop` + `python scripts/verify_seed.py --strict`
- [ ] 若改动 RFID： `python -m pytest tests/test_gateway -q`
- [ ] 手动：模拟器 + 仪表盘看门狗 / 非标借还各走一遍

---

## 6. 相关文档

- [MEMO.md](MEMO.md) — 硬件实测、NiceGUI 加载、数据库迁移
- [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) — 能力与文件索引
- [RFID_MULTIPLEXER_WATCHDOG.md](RFID_MULTIPLEXER_WATCHDOG.md) — 看门狗现场演示脚本
