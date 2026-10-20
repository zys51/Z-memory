# 部署操作手册（Phase 3 照此执行）

> 前置：服务代码已就绪、本地契约测试 12/12 通过（见 README Phase 1）。
> 本文档给「大一新生」用，每一步能复制就复制。

---

## 第 1 步：注册阿里云 + 开通 DashScope（拿嵌入 Key）

1. 打开 https://www.aliyun.com → 右上角「免费注册」。
2. 用手机号注册，完成**实名认证**（个人认证，需身份证）。
   - 可选：再做**学生认证**（学信网/学生证），后续买服务器能拿学生价。
3. 开通 **百炼（Model Studio / DashScope）**：
   - 控制台搜索「百炼」或直接访问 https://bailian.console.aliyun.com/
   - 首次进入按提示开通（免费开通，按量付费，新用户常有免费额度）。
4. 创建 API Key：
   - 百炼控制台 → 「API-KEY」或右上角头像 → API-KEY 管理。
   - 创建后得到一串 `sk-` 开头的 Key，**保存好（只显示一次）**。
5. 本地验证 Key 是否可用（在你自己的电脑，装好依赖后）：
   ```powershell
   $env:DASHSCOPE_API_KEY="sk-你的key"
   python scripts/test_embedding.py
   ```
   看到 `[OK] 成功：...维度=...` 即通过。

---

## 第 2 步：购买轻量服务器（最便宜档）

> 到这一步再买即可；买前可让 AI 帮你找当前最便宜的学生/新用户特价档。

1. 阿里云控制台搜索「**轻量应用服务器**」。
2. 选**最便宜**的 Linux 镜像档位（建议 2核2G 以上、Ubuntu 22.04/24.04 或 Debian，磁盘 ≥ 40G）。
   - 地域选**离你近的**（如华东）即可；带宽 3M~5M 够用。
   - 常见新用户/学生价：¥9~10/月 或 首年 ¥99 级。
3. 购买后进入服务器管理页：
   - 设置**登录密码**（或密钥对）。
   - 记下**公网 IP**。
   - 在「防火墙」里放行 **8080** 端口（TCP）。

---

## 第 3 步：把代码传上去并启动服务

### 第 0 步：把代码传到服务器（二选一）

**A. git clone（推荐，需先建 GitHub 仓库）**
```bash
cd ~ && git clone https://github.com/你的用户名/你的仓库.git memcomp && cd memcomp
```

**B. scp 上传（无需 GitHub，推荐用脚本，在本机 PowerShell 执行）**
```powershell
cd D:\Working\memcomp
powershell -ExecutionPolicy Bypass -File scripts\upload.ps1 -Ip 公网IP
```
（等价的手动 scp：`scp -r app run.py requirements.txt .env.example deploy.sh root@公网IP:~/memcomp/`）

### 方式 0（最省事，推荐）：一键脚本 `deploy.sh`

SSH 登录服务器后（Windows 用 `ssh root@公网IP`，或阿里云网页版「远程连接」），在代码目录执行：

```bash
cd ~/memcomp
DASHSCOPE_API_KEY=sk-你的阿里云key bash deploy.sh
```

脚本会自动：装依赖 → 建虚拟环境 → 写 `.env` → 装 systemd 服务 → 启动并设开机自启 → 健康检查。
（`AML_API_KEY` 先不用填，拿到官方评测 Key 后再 `nano .env` 更新并 `systemctl restart memcomp`。）

### 方式 A（手动，可对照理解）

SSH 登录服务器后（Windows 可用 PowerShell 的 `ssh root@公网IP`，或用阿里云网页版「远程连接」）：

```bash
# 1) 安装 Python3 + venv + git
sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip git

# 2) 拉代码（或先用 scp/git 上传你的仓库）
cd ~
git clone https://github.com/你的用户名/你的仓库.git memcomp
cd memcomp

# 3) 建虚拟环境装依赖（国内服务器建议用清华镜像）
python3 -m venv .venv
source .venv/bin/activate
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 4) 配置环境变量
cp .env.example .env
nano .env   # 填 AML_API_KEY（评测Key，先随便填一个占位，拿到官方Key再改）、DASHSCOPE_API_KEY（你的阿里云Key）

# 5) 前台试跑一下，确认能起
python run.py
# 看到 "Uvicorn running on http://0.0.0.0:8080" 即成功；Ctrl+C 退出
```

### 方式 B：Docker（可选，环境更干净）

```bash
sudo apt-get install -y docker.io
cd ~/memcomp
sudo docker build -t memcomp .
sudo docker run -d --restart unless-stopped -p 8080:8080 \
  -e AML_API_KEY="你的评测Key" \
  -e DASHSCOPE_API_KEY="你的阿里云Key" \
  -v memcomp_data:/app/data \
  --name memcomp memcomp
```

### 让服务常驻（方式 A 用 systemd）

```bash
sudo nano /etc/systemd/system/memcomp.service
```

粘贴：
```ini
[Unit]
Description=AML Memory Service
After=network.target

[Service]
WorkingDirectory=/root/memcomp
ExecStart=/root/memcomp/.venv/bin/python run.py
Restart=always
EnvironmentFile=/root/memcomp/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now memcomp
sudo systemctl status memcomp   # 看到 active (running) 即成功
```

---

## 第 4 步：公网自测

在你自己的电脑上（把 `公网IP` 换成你的）：

```bash
curl http://公网IP:8080/health
# 期望：{"ok":true,"service":"aml-memory-service",...}

curl -X POST http://公网IP:8080/add -H "Content-Type: application/json" -H "X-Api-Key: 你的AML_API_KEY" -d '{"request_id":"t1","messages":[{"role":"user","content":"I live in Beijing"}],"user_id":"u1","session_id":"s1"}'
# 期望：{"success":true,"request_id":"t1",...}

curl -X POST http://公网IP:8080/search -H "Content-Type: application/json" -H "X-Api-Key: 你的AML_API_KEY" -d '{"query":"Where do I live","user_id":"u1","top_k":5}'
# 期望：{"data":[{"id":1,"content":"I live in Beijing","created_at":"..."}]}
```

---

## 第 5 步：官网提交评测申请

1. 打开 https://agentmemories.ai/evaluation
2. 填写：
   - 赛道：文本；组别：开源方法榜（学术榜）
   - Add/Search API 地址：`http://公网IP:8080`（或 `/v1/add`、`/v1/search` 路径）
   - 鉴权方式：`X-Api-Key`，值填你 `.env` 里的 `AML_API_KEY`
   - GitHub 仓库 + 固定 commit
3. 提交后**次日 19:00 前**收到评测 Key（AML Key），把它填回 `.env` 的 `AML_API_KEY` 并重启服务。
4. 用官方 Key 跑 **Smoke** → 全绿后启动 **Full**。

---

## 常见问题

- **端口不通**：检查阿里云控制台「防火墙」是否放行 8080；`ufw` 是否放行。
- **嵌入报错**：确认 `DASHSCOPE_API_KEY` 正确、已开通百炼、账号有余额/免费额度。
- **评测 Key 填错**：Smoke 会报 401，按报错改 `.env` 并重启服务。
