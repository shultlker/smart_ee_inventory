# 依赖与安装说明

> 适用代码：smart_ee_inventory v0.1.0  
> 下列「实测版本」在 **Windows 10/11 · Python 3.11.5 · 2026-06-30** 的 `.venv` 中验证通过。

---

## 1. 环境要求

| 项目 | 要求 |
|------|------|
| Python | **3.11+**（`requires-python`；推荐 3.11 或 3.12） |
| 操作系统 | Windows（RFID 串口主测环境）；Linux/macOS 可运行 Web/API，串口路径不同 |
| 构建工具 | `pip` ≥ 23；安装 editable 时会拉取 **hatchling**（仅构建期） |
| 硬件（可选） | YZ-M40 USB 模块；无硬件可用 TCP 模拟器 |

---

## 2. 推荐安装（开发 / 演示）

在项目根目录执行：

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
pip install -e ".[dev]"
```

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
pip install -e ".[dev]"
```

说明：

- `-e`：以 **editable** 模式安装本仓库，修改 `backend/`、`frontend/`、`gateway/` 后无需重装。
- `[dev]`：额外安装 pytest、pytest-asyncio、ruff。
- 配置见 `.env.example` → 复制为 `.env`。

**仅运行（不跑测试 / lint）** — **其它 PC 部署请用这一条**：

```powershell
pip install -e .
# 或锁定版本：
# pip install -r requirements-lock.txt && pip install -e . --no-deps
```

**开发机需要测试 / ruff 时**再装 dev（建议用锁定文件，避免 pip 反复试 ruff 版本）：

```powershell
pip install -e .
pip install -r requirements-dev-lock.txt
# 等价于 pip install -e ".[dev]"，但版本固定、解析更快
```

---

## 3. 直接依赖（pyproject.toml 声明）

以下为项目**显式声明**的运行时包；业务代码直接 `import` 或经 CLI 使用。

| 包名 | 声明约束 | 实测版本 | 用途 |
|------|----------|----------|------|
| **fastapi** | ≥0.115.0 | 0.138.1 | REST API、OpenAPI、WebSocket 路由 |
| **uvicorn[standard]** | ≥0.32.0 | 0.49.0 | ASGI 服务器（含 watchfiles、httptools、websockets） |
| **nicegui** | ≥2.10.0 | **3.13.0** | Web UI（Quasar）；依赖 FastAPI + Socket.IO |
| **sqlalchemy** | ≥2.0.36 | 2.0.51 | ORM；异步会话 |
| **aiosqlite** | ≥0.20.0 | 0.22.1 | SQLite 异步驱动 |
| **pydantic** | ≥2.10.0 | 2.13.4 | 请求/响应模型校验 |
| **pydantic-settings** | ≥2.6.0 | 2.14.2 | `.env` 配置加载 |
| **pyserial** | ≥3.5 | 3.5 | YZ-M40 USB 串口 |
| **python-dotenv** | ≥1.0.0 | 1.2.2 | 环境变量文件（settings 使用） |
| **httpx** | ≥0.28.0 | 0.28.1 | 前端 ApiClient；测试里 FastAPI TestClient 也依赖 httpx 生态 |

### 开发依赖（optional `[dev]`）

| 包名 | 声明约束 | 实测版本 | 用途 |
|------|----------|----------|------|
| **pytest** | ≥8.3.0, &lt;10 | 9.1.1 | 单元 / API 测试 |
| **pytest-asyncio** | ≥0.24.0, &lt;2 | 1.4.0 | 异步测试 |
| **ruff** | **≥0.15.0, &lt;0.16** | 0.15.20 | 代码检查 |

> 旧版 `ruff>=0.8.0` 会让 pip 在 0.8～0.15 间大量回溯试装。**其它 PC 部署运行服务时不要装 `[dev]`**（见 §2）。

---

## 4. 主要传递依赖（自动安装，无需手写）

安装上述直接依赖后，pip 会自动拉取例如：

| 包名 | 实测版本 | 由谁引入 | 说明 |
|------|----------|----------|------|
| starlette | 1.3.1 | fastapi、nicegui | ASGI 框架；TestClient 在此 |
| greenlet | 3.5.3 | sqlalchemy | 异步 ORM 所需 |
| anyio | 4.14.1 | httpx、starlette | 异步 I/O |
| aiohttp / aiofiles | 3.14.1 / 25.1.0 | nicegui | 静态资源、内部 HTTP |
| python-socketio / engineio | 5.16.3 / 4.13.3 | nicegui | 浏览器 WebSocket |
| python-multipart | 0.0.32 | nicegui | 表单上传 |
| orjson | 3.11.9 | nicegui | JSON 加速 |
| click | 8.4.2 | uvicorn | CLI |
| watchfiles | 1.2.0 | uvicorn[standard] | 热重载（`DEBUG=true`） |
| websockets | 16.0 | uvicorn[standard] | WebSocket 协议栈 |

> **注意**：NiceGUI 3.x 与声明的下限 `>=2.10.0` 兼容；当前开发机为 **3.13.0**。若需锁定大版本，可在自有环境使用 `requirements-lock.txt`（见 §6）。

---

## 5. 标准库（无需 pip 安装）

项目还使用 Python 标准库，例如：`asyncio`、`logging`、`sqlite3`（经 SQLAlchemy）、`socket`（模拟器）、`pathlib`、`dataclasses`、`urllib` 等。

---

## 6. 可选：锁定版本重装

若需与开发机一致的可复现环境，可使用仓库根目录 **`requirements-lock.txt`**（仅锁定**直接**依赖版本）：

```powershell
pip install -U pip
pip install -e .
pip install -r requirements-lock.txt
pip install -r requirements-dev-lock.txt   # 开发工具
```

或一条命令安装全部锁定版本后再 editable 本包：

```powershell
pip install -r requirements-lock.txt -r requirements-dev-lock.txt
pip install -e . --no-deps
```

---

## 7. 验证安装

```powershell
python -c "import fastapi, nicegui, sqlalchemy, aiosqlite, serial, httpx; print('OK')"
python -c "import smart_ee_inventory" 2>nul || python -c "import backend, frontend, gateway; print('editable OK')"
python scripts/smoke_test.py
```

期望：无 ImportError；冒烟测试 **38 passed** 量级（含 `test_frontend`）。

查看已安装版本：

```powershell
pip list
pip show smart-ee-inventory
```

---

## 8. 常见问题

| 现象 | 处理 |
|------|------|
| **`pip install -e ".[dev]"` 反复下载 ruff** | **部署机改用 `pip install -e .`**；开发机先 `pip install -U pip`，再用 `pip install -r requirements-dev-lock.txt` 代替宽泛的 `[dev]` |
| `pip install -e ".[dev]"` 报 hatchling 错误 | 先 `pip install -U pip hatchling`，再重试 |
| PowerShell 无法执行 Activate | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| `import serial` 失败 | 确认安装的是 **pyserial**（`pip install pyserial`），不是名为 `serial` 的其他包 |
| NiceGUI / FastAPI 版本过旧 | `pip install -U "nicegui>=2.10" "fastapi>=0.115"` |
| 测试 StarletteDeprecationWarning（httpx） | 当前 TestClient 仍用 httpx；警告可忽略，不影响测试通过 |
| 接 RFID 时串口被占用 | 关闭 `test_rfid_serial.py monitor` 与其它占 COM 的程序；`.env` 设 `DEBUG=false` |

---

## 9. 与 pyproject.toml 的关系

权威声明在根目录 **`pyproject.toml`** 的 `[project.dependencies]` 与 `[project.optional-dependencies.dev]`。  
本文档实测版本用于文档与 `requirements-lock.txt`；升级依赖后请同步运行：

```powershell
python scripts/smoke_test.py
python -m pytest tests -q
```

并更新 `requirements-lock.txt` 与本文档「实测版本」列。
