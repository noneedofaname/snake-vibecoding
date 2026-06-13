# 🐍 贪吃蛇 × MyGO!!!!! & Ave Mujica

基于 Python WebSocket 的单机挑战 / 人机对战贪吃蛇游戏，融入 BanG Dream! It's MyGO!!!!! 和 Ave Mujica 角色元素。

## 🎮 游戏模式

### 🎮 单机模式
经典贪吃蛇玩法，地图上有：
- **6个苹果** — 吃了加 1 分，持续刷新
- **⭐ 金色星星** — 随机出现，+3 分，有时限
- **10位乐队成员** — 以 2×2 / 3×3 大头照形式在地图上移动，带有旋转和呼吸动画，碰到即死

### 🤖 人机模式
通过 WebSocket 连本地服务器，与 3 个 AI 对手同场竞技：
- **蛇蛇互撞** — 蛇头碰到任何其他蛇的身体都会死亡
- **AI 不复活** — 打死一个少一个，全部消灭即胜利（弹出祥子胜利画面）
- **三档难度**：
  - 🟢 简单 — AI 每 5 拍才反应一次
  - 🟡 普通 — AI 隔一拍反应
  - 🔴 困难 — AI 步步紧逼

## 🎵 音效

- **BGM**：`haruhikage.aac`（春日影钢琴版），开始游戏自动循环播放
- **死亡音效**：Web Audio API 合成的下降音阶 + 噪声爆炸

## 💬 吃分夸赞

每次吃到食物，屏幕底部随机弹出 10 位成员之一的头像和名台词（见 `quotes.json`），持续 2.5 秒。

## 🚀 运行方式

### 前提
- Python 3.10+
- 安装依赖：`pip install websockets`

### 启动
```bash
cd 项目目录
python server.py
```
浏览器打开 `http://localhost:3000/snake.html`

人机模式自动连接本地 WebSocket（`ws://localhost:3001`）。

## 📁 文件说明

| 文件 | 说明 |
|------|------|
| `snake.html` | 前端（HTML + CSS + JS），直接用浏览器打开 |
| `server.py` | WebSocket 服务器 + HTTP 静态文件服务 |
| `quotes.json` | 10位成员台词，可自由修改 |
| `*.webp` | 角色头像素材（10张） |
| `haruhikage.aac` | 背景音乐（春日影） |
| `sakiko_win.webp` | 胜利画面祥子图 |
| `download_images.py` | 素材下载脚本（已执行完毕） |

## ⚠️ 声明

- **本项目的所有音乐和图像素材均来源于网络，版权归原作者所有，仅供个人学习用途，不得用于商业目的。**
- 本项目纯粹为了练习 **vibe coding**（AI辅助开发），以验证「不写一行代码能否做出可玩游戏」。
- 代码质量不做保证——它是 AI 生成、逐步迭代的产物，结构上存在明显的技术债务（见 `MAINTENANCE.md`），请勿作为工程参考。

## 🛠 技术栈

- 前端：原生 Canvas + Web Audio API + WebSocket（零框架）
- 后端：Python `asyncio` + `websockets` + `http.server`
- 无 Node.js / npm 依赖
