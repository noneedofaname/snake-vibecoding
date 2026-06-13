# 🐍 贪吃蛇维护文档

## 一、代码结构问题（已知技术债务）

这是 vibe coding 的产物——从头到尾 AI 迭代生成，没做过任何架构设计。

### 问题 1：全部塞一个 HTML
`snake.html` 约 38KB，包含 **HTML（~3KB）+ CSS（~7.6KB）+ JS（~27KB）**。

- HTML、CSS、JS 三者在同一文件中，没有分离
- 所有 JS 变量全局作用域，没有模块化
- 如果未来想拆成多文件，JS 需要做模块化改造（`export`/`import` 或 ES module）

### 问题 2：server.py 单文件 826 行
- 游戏逻辑（GameState）、网络层（WebSocket handler）、HTTP 服务全在一个文件
- 如果把游戏逻辑拆到 `game.py`、网络层拆到 `server.py`、配置拆到 `config.py`，维护会容易得多
- 没有类和职责分离——GameState 承担了几乎所有功能

### 问题 3：单机和人机是两套独立的游戏逻辑
- `snake.html` 里 `tickSP()` / `drawSP()` 是单机版的游戏循环 + 渲染
- `server.py` 里 `tick()` 是人机版的游戏循环
- `snake.html` 里 `drawMulti()` 是人机版的渲染
- **食物、障碍、碰撞检测的逻辑在客户端和服务端各写了一遍**——如果要改规则，两边都要改

### 问题 4：魔法数字满天飞
`GRID_SIZE=30`、`BASE_TICK_MS=100`、`MAX_OBS=6`、`MAX_FOODS=6`、`OBS_SPAWN=15` 等散落在代码各处。没有统一的配置文件。

### 问题 5：没有测试、没有版本控制、没有 CI
作为 v0.1 初版可以接受，但后续迭代建议：
- 初始化 git 仓库
- 游戏逻辑单元测试
- 拆文件后再继续加功能

---

## 二、snake.html 代码地图

从文件头向下、按出现的功能区域划分：

### 📍 DOM 元素引用（行 ~95-105）
```js
const canvas, ctx, scoreEl, highScoreEl, lengthEl, ...;
```
所有 `getElementById` 集中在这里。如果加新 UI 元素，在这里加引用。

### 📍 常量（行 ~90）
```js
const GRID_SIZE=30, CELL_SIZE=canvas.width/GRID_SIZE;
const BASE_SPEED=100, MAX_OBS=6, OBS_SPAWN=15, OBS_MOVE=2, MAX_FOODS=6;
```

### 📍 音频引擎（行 ~100-125）
- `initAudio()` — 创建 AudioContext，加载 haruhikage.aac
- `playBGM()` — 播放循环背景音乐
- `stopBGM()` — 停止背景音乐
- `playDeathSound()` — Web Audio API 合成下降音阶 + 噪声（无需外部文件）

**机制**：BGM 用 `<Audio>` 元素加载 `.aac` 文件（loop=true）。死亡音效用 OscillatorNode 实时合成，避免额外文件依赖。

### 📍 角色素材（行 ~128-145）
- `characterFiles[]` — 10人的名字、标签、队伍
- `characterImages[]` — 加载的 Image 对象
- 图片加载完后 `loadingOverlay` 隐藏

**机制**：所有 10 张 webp 图片在页面加载时预加载，用于障碍物渲染。

### 📍 祝福语系统（行 ~145-155）
- `quotesData` — 从 `quotes.json` fetch 的台词数据
- `showCharacterQuote()` — 随机选人、选台词、显示 2.5 秒 toast

**机制**：吃分时调用，从 10 人中随机选 1 人，从该人的 4-5 句话中随机选 1 句，屏幕底部弹出圆形头像 + 台词。

### 📍 全局状态（行 ~155-158）
```js
let gameMode='single', ws, myId, myColor, serverState, botDifficulty='normal';
let multiAlive, isPaused, renderFrame, prevMultiScore;
```

### 📍 绘图工具（行 ~160-190）
- `roundRect()` — canvas 圆角矩形（中国浏览器 polyfill）
- `drawStar()` — 五角星（金色星星食物）
- `drawObsList()` — 画所有障碍物（角色头像+旋转+呼吸+阴影+名字标签）
- `drawFood()` — 画苹果（径向渐变+光晕+高光）
- `drawSnakeHead()` / `drawSnakeBody()` — 蛇的渲染
- `drawGrid()` / `drawIdle()` / `drawConnecting()` — 背景/待机画面

### 📍 单机游戏逻辑（行 ~192-310）
**核心状态**：
```js
let snake, foods=[], bonusFood, bonusTimer, obstacles, ...;
```
- `initSP()` — 初始化/重置所有状态，生成 6 个初始食物
- `occSP()` — 计算所有被占用的格子（蛇+食物+障碍）
- `spawnFoodSP()` — 在空位上生成新食物（维持 6 个）
- `spawnBonusSP()` — 生成金色星星，60 tick 倒计时
- `spawnObsSP()` — 生成移动障碍物（角色头像，随机大小/方向/旋转）
- `moveObsSP()` — 每 2 tick 移动障碍物，碰壁反弹
- `tickSP()` — **主循环**：移动蛇 → 碰撞检测 → 吃食物 → 更新分数 → 生成障碍
- `endSP()` — 游戏结束：停止音乐、更新最高分、显示死亡面板
- `startSP()` / `togglePauseSP()` / `setDirSP()` — 控制方法
- `drawSP()` — 渲染单机画面

**调用链**：`startSP()` → `setInterval(tickSP, speed)` → 每次 tick 调 `tickSP()` → `requestAnimationFrame(renderLoop)` → `drawSP()`

### 📍 人机模式逻辑（行 ~312-380）
**WebSocket 生命周期**：
- `connect()` — 建立 WebSocket，`onopen` 时发送 `request_bot`
- `disconnect()` — 关闭连接，重置状态
- `sendDir(dx,dy)` — 发送方向指令
- `sendPause()` / `sendResume()` / `sendRestart()` — 控制指令

**消息处理**（`ws.onmessage`）：
- `type:'init'` — 收到自己的 ID 和颜色
- `type:'state'` — 收到完整游戏状态（蛇、食物、障碍等），调 `drawMulti()` 渲染
- `type:'died'` — 自己死亡，显示死亡面板
- `type:'state'` 中 `winner` 字段非空 → 胜利弹窗

**分数变化检测**：`updateMyScore()` 比较 `prevMultiScore` 和当前分数，变了就调 `showCharacterQuote()`。

### 📍 渲染循环（行 ~382-395）
```js
function renderLoop(){
  if(gameMode=='single'){
    if(gameRunning||gameOver) drawSP();
    else drawIdle();
    renderFrame=requestAnimationFrame(renderLoop);
  }else{
    if(serverState) drawMulti(serverState);
    else drawConnecting();
    renderFrame=requestAnimationFrame(renderLoop);
  }
}
```

**机制**：单机模式用自己的状态渲染，人机模式用服务端推送的 `serverState` 渲染。只有一个 rAF 循环，模式切换时 `cancelAnimationFrame` + 重启。

### 📍 输入处理（行 ~397-430）
- 键盘：方向键 / WASD 控制方向，空格 暂停/开始/重生
- 触摸：swipe 控制方向
- 移动端按钮：方向箭头 click/touch 事件

### 📍 模式切换（行 ~432-445）
`mode-btn` 点击 → 切换 `gameMode` → 重启动画循环 → 连接/断开 WebSocket。

### 📍 难度选择（行 ~447-452）
`diff-btn` 点击 → 设置 `botDifficulty` → 下次连接时发送给服务端。

---

## 三、server.py 代码地图

### 📍 常量（行 1-30）
```python
GRID_SIZE=30, BASE_TICK_MS=100, MAX_OBSTACLES=6, MAX_FOODS=6, DIFFICULTY_DELAY
BOT_COLORS, PLAYER_COLORS, CHARACTERS
```

### 📍 GameState 类（行 ~90-650）
这是核心类，管理整个游戏世界：

**数据结构**：
- `self.players: dict[ws, player]` — 人类玩家
- `self.bots: list[bot]` — AI 对手
- `self.foods: list[(x,y)]` — 食物位置
- `self.obstacles: list[dict]` — 移动障碍物
- `self.winner_id: str|None` — 胜利者 ID

**Player/Bot 结构**：
```python
{
  'id': str, 'color': str, 'snake': [(x,y),...],
  'direction': (dx,dy), 'next_direction': (dx,dy),
  'score': int, 'alive': bool, 'ws': WebSocket|None,
  'is_bot': bool,        # bot 特有
  'respawn_timer': int,  # bot 特有（当前禁用）
  'difficulty': str,     # bot 特有
  'ai_timer': int,       # bot 特有
}
```

**关键方法**：
- `tick()` — **主循环**：AI思考 → 移动所有蛇 → 碰撞检测 → 吃食物 → 胜利判定 → 广播状态
- `bot_ai(bot)` — AI寻路：曼哈顿距离 + 2步前瞻 + 避让其他蛇 + 难度延迟
- `find_spawn_position()` — 出生点：随机候选 + 8格最小间距
- `get_occupied_cells()` — 收集所有被占用的格子
- `spawn_food()` — 维持 MAX_FOODS 个食物
- `check_snake_collision()` — 蛇头撞其他蛇身检测
- `check_obstacle_collision()` — 撞障碍物检测
- `respawn_player()` — 重生玩家（restart 时用）
- `to_state_msg()` — 序列化全量状态发给客户端

### 📍 WebSocket 处理（行 ~660-760）
`handle_connection(ws)` — 每个连接的异步处理循环：
- `direction` — 更新方向
- `pause` / `resume` — 暂停/继续
- `restart` — 重置所有蛇位置，保留 bots
- `request_bot` — 创建 AI 对手（带 difficulty）
- 连接断开 → `remove_player`

### 📍 HTTP 服务（行 ~770-790）
`SimpleHTTPRequestHandler` 从当前目录提供静态文件（html/webp/aac/json）。

### 📍 主函数（行 ~790-826）
- 启动 HTTP 服务器（端口 3000）
- 启动 WebSocket 服务器（端口 3001）
- 启动游戏主循环（`game_loop` — 每 BASE_TICK_MS 毫秒调一次 `tick()`）
- 自动检测局域网 IP 并打印

---

## 四、数据流

```
[浏览器]                    [Python Server]
   |                            |
   |-- WS connect ------------>|
   |<-- init {id,color} -------|
   |-- request_bot {count,di}->|   (创建3个AI)
   |                            |   game_loop: tick() 每100ms
   |-- direction {dx,dy} ----->|
   |<-- state {snakes,...} ----|   每tick广播一次
   |                            |
   |  renderLoop()             |
   |  -> drawMulti(state)      |
   |                            |
   |-- restart --------------->|   respawn_player() x4
```

**关键**：所有游戏逻辑在服务端运行，客户端只是一个"遥控器+显示器"。服务端 tick 做碰撞判定、死亡通知，客户端收到 `state` 后纯渲染。

---

## 五、修改指南

### 加新食物类型
1. `server.py` — `tick()` 加新检测，`to_state_msg()` 加新字段
2. `snake.html` — `drawMulti()` 加新绘制，单机 `tickSP()` / `drawSP()` 对应加

### 调难度
`server.py` 顶部 `DIFFICULTY_DELAY` 字典。数值 = AI 不动脑子的 tick 数。

### 改台词
编辑 `quotes.json`，格式保持即可。热更新（fetch 每次页面加载读）。

### 改音乐
替换 `haruhikage.aac` 为同名文件，或改 `snake.html` 中 `new Audio('xxx')` 的路径。
死亡音效是代码生成的（`playDeathSound()`），不需要文件。

### 加减障碍物数量
`snake.html` — `MAX_OBS=6`
`server.py` — `MAX_OBSTACLES=6`

### 加减食物数量
`snake.html` — `MAX_FOODS=6`
`server.py` — `MAX_FOODS=6`
