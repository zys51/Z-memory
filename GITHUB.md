# GitHub 仓库搭建指南（部署 + 提交都要用）

> 比赛要求：开源方法榜需提供**公开 GitHub 仓库 + 固定 commit**。
> 同时部署时可以 `git clone` 拉代码到服务器，最省事。

---

## 1. 建仓库

1. 打开 https://github.com → 登录/注册。
2. 右上角 **+** → **New repository**。
3. 名字随意（如 `agent-memory-challenge`），选 **Public**（公开，比赛要求），**不勾** README/.gitignore（我们本地已有）。
4. 点 **Create repository**。

## 2. 本地推送代码（PowerShell）

```powershell
cd D:\Working\memcomp

# 首次：装 git（若没有）——去 https://git-scm.com/download/win 下载安装，或：
# winget install Git.Git

git init
git add -A
git commit -m "AML memory service v1: BM25 + text-embedding-v4 + RRF"
git branch -M main
git remote add origin https://github.com/你的用户名/你的仓库名.git
git push -u origin main
```

> 推送时会弹 GitHub 登录授权；用浏览器登录即可（或提前配好 Personal Access Token）。

## 3. 记录固定 commit（提交比赛用）

```powershell
git rev-parse HEAD
```

会输出一串 40 位的 hash（如 `a1b2c3d...`），这就是「固定 commit」，比赛提交时要填。

## 4. 之后改了代码要更新

```powershell
git add -A
git commit -m "改动说明"
git push
```

> ⚠️ 正式评测提交后，**不要再改代码/换 commit**（成绩绑定版本）。要改就等下一次 Full。

---

## 5. 隐私提醒

- 确认 `.gitignore` 生效：`.env`（含密钥）、`data/*.db`、`.venv/` 等都**不会**被提交。
- 推送前可 `git status` 看一眼有没有误加 `.env`。
