"""
贪吃蛇多人联机服务器
启动: python server.py
HTTP: http://localhost:3000  (其他人连你的局域网IP:3000)
WS:   ws://localhost:3001
"""
import asyncio
import json
import random
import math
import threading
import time
import os
from http.server import HTTPServer, SimpleHTTPRequestHandler
import websockets

GRID_SIZE = 30
BASE_TICK_MS = 100
MAX_OBSTACLES = 6
OBSTACLE_SPAWN_INTERVAL = 15
OBSTACLE_MOVE_INTERVAL = 2
MAX_FOODS = 6
BONUS_FOOD_CHANCE = 0.3
BONUS_FOOD_LIFETIME = 60
DIFFICULTY_DELAY = {'easy': 4, 'normal': 1, 'hard': 0}
HTTP_PORT = 3000
WS_PORT = 3001

BOT_COLORS = [
    '#ff8844', '#aa66ff', '#ffff66', '#44ddcc', '#ff66cc',
    '#88ff44', '#ff4488', '#44ddff',
]

PLAYER_COLORS = [
    '#00ff88', '#ff6688', '#ffcc00', '#66aaff',
    '#ff8844', '#aa66ff', '#44ddcc', '#ff66cc',
    '#88ff44', '#ff4488', '#44ddff', '#ffaa22',
]

# Character image data (same as client)
CHARACTERS = [
    {'idx': 0, 'name': 'tomori',  'label': '高松燈',     'team': 'MyGO!!!!!'},
    {'idx': 1, 'name': 'anon',    'label': '千早愛音',   'team': 'MyGO!!!!!'},
    {'idx': 2, 'name': 'rana',    'label': '要楽奈',     'team': 'MyGO!!!!!'},
    {'idx': 3, 'name': 'soyo',    'label': '長崎爽世',   'team': 'MyGO!!!!!'},
    {'idx': 4, 'name': 'taki',    'label': '椎名立希',   'team': 'MyGO!!!!!'},
    {'idx': 5, 'name': 'sakiko',  'label': '豊川祥子',   'team': 'Ave Mujica'},
    {'idx': 6, 'name': 'mutsumi', 'label': '若葉睦',     'team': 'Ave Mujica'},
    {'idx': 7, 'name': 'umiri',   'label': '八幡海鈴',   'team': 'Ave Mujica'},
    {'idx': 8, 'name': 'uika',    'label': '三角初華',   'team': 'Ave Mujica'},
    {'idx': 9, 'name': 'nyamu',   'label': '祐天寺にゃむ', 'team': 'Ave Mujica'},
]

OBSTACLE_SIZES = [
    (2, 2), (2, 2), (3, 2), (2, 3), (3, 3),
]
MOVE_DIRS = [
    (1, 0), (-1, 0), (0, 1), (0, -1),
    (1, 1), (-1, 1), (1, -1), (-1, -1),
]

class GameState:
    def __init__(self):
        self.players = {}       # websocket -> player_state
        self.bots = []          # AI players
        self.next_id = 0
        self.color_idx = 0
        self.bot_color_idx = 0
        self.paused = False
        self.winner_id = None
        self.foods = []
        self.bonus_food = None
        self.bonus_timer = 0
        self.obstacles = []
        self.obs_spawn_timer = 0
        self.tick_count = 0

    def get_occupied_cells(self):
        occupied = set()
        for p in self.players.values():
            if not p['alive']:
                continue
            for sx, sy in p['snake']:
                occupied.add((sx, sy))
        for bot in self.bots:
            if not bot['alive']:
                continue
            for sx, sy in bot['snake']:
                occupied.add((sx, sy))
        for f in self.foods:
            occupied.add(tuple(f))
        if self.bonus_food:
            occupied.add((self.bonus_food['x'], self.bonus_food['y']))
        for obs in self.obstacles:
            ox, oy = round(obs['x']), round(obs['y'])
            for dx in range(obs['w']):
                for dy in range(obs['h']):
                    cx, cy = ox + dx, oy + dy
                    if 0 <= cx < GRID_SIZE and 0 <= cy < GRID_SIZE:
                        occupied.add((cx, cy))
        return occupied

    def spawn_food(self):
        """Maintain MAX_FOODS food items on the grid"""
        while len(self.foods) < MAX_FOODS:
            occupied = self.get_occupied_cells()
            free = [(x, y) for x in range(GRID_SIZE) for y in range(GRID_SIZE)
                    if (x, y) not in occupied]
            if not free:
                break
            self.foods.append(random.choice(free))

    def spawn_bonus_food(self):
        if self.bonus_food:
            return
        occupied = self.get_occupied_cells()
        free = [(x, y) for x in range(GRID_SIZE) for y in range(GRID_SIZE)
                if (x, y) not in occupied]
        if not free:
            return
        pos = random.choice(free)
        self.bonus_food = {'x': pos[0], 'y': pos[1]}
        self.bonus_timer = BONUS_FOOD_LIFETIME

    def spawn_obstacle(self):
        if len(self.obstacles) >= MAX_OBSTACLES:
            return
        occupied = self.get_occupied_cells()
        size = random.choice(OBSTACLE_SIZES)
        w, h = size

        free = []
        for x in range(GRID_SIZE - w + 1):
            for y in range(GRID_SIZE - h + 1):
                blocked = False
                for dx in range(w):
                    for dy in range(h):
                        if (x + dx, y + dy) in occupied:
                            blocked = True
                            break
                    if blocked:
                        break
                if not blocked:
                    free.append((x, y))
        if not free:
            return

        pos = random.choice(free)
        vx, vy = random.choice(MOVE_DIRS)
        char_idx = random.randint(0, len(CHARACTERS) - 1)

        self.obstacles.append({
            'x': float(pos[0]), 'y': float(pos[1]),
            'w': w, 'h': h,
            'vx': vx, 'vy': vy,
            'charIdx': char_idx,
            'alpha': 0.0,
            'rotation': (random.random() - 0.5) * 30,
            'rotSpeed': (random.random() - 0.5) * 5,
            'pulsePhase': random.random() * math.pi * 2,
            'pulseSpeed': 0.07 + random.random() * 0.08,
            'moveTimer': random.randint(0, OBSTACLE_MOVE_INTERVAL - 1),
        })

    def is_obs_pos_free(self, obs, nx, ny):
        if nx < 0 or nx + obs['w'] > GRID_SIZE or ny < 0 or ny + obs['h'] > GRID_SIZE:
            return False
        # Check all snakes
        for p in self.players.values():
            if not p['alive']:
                continue
            for sx, sy in p['snake']:
                if nx <= sx < nx + obs['w'] and ny <= sy < ny + obs['h']:
                    return False
        # Check food
        for f in self.foods:
            fx, fy = f
            if nx <= fx < nx + obs['w'] and ny <= fy < ny + obs['h']:
                return False
        if self.bonus_food:
            bx, by = self.bonus_food['x'], self.bonus_food['y']
            if nx <= bx < nx + obs['w'] and ny <= by < ny + obs['h']:
                return False
        # Check other obstacles
        for other in self.obstacles:
            if other is obs:
                continue
            ox, oy = round(other['x']), round(other['y'])
            if nx < ox + other['w'] and nx + obs['w'] > ox and ny < oy + other['h'] and ny + obs['h'] > oy:
                return False
        return True

    def check_snake_collision(self, x, y, exclude_entity):
        """Check if (x,y) hits any other snake's body. Returns the victim if hit."""
        all_snakes = list(self.players.values()) + self.bots
        for other in all_snakes:
            if other is exclude_entity:
                continue
            if not other['alive']:
                continue
            if (x, y) in other['snake']:
                return other
        return None

    def check_obstacle_collision(self, x, y):
        for obs in self.obstacles:
            ox, oy = round(obs['x']), round(obs['y'])
            if ox <= x < ox + obs['w'] and oy <= y < oy + obs['h']:
                return obs
        return None

    def find_spawn_position(self, occupied_cells=None, min_sep=8):
        """Find a random spawn position with minimum separation from occupied cells.
        Uses many candidate positions with random offsets to spread snakes out."""
        if occupied_cells is None:
            occupied_cells = self.get_occupied_cells()
        
        # Many candidate positions around the grid, with random offsets
        candidates = []
        # Generate base positions spread across the whole grid
        for x in range(3, GRID_SIZE - 6, 4):
            for y in range(3, GRID_SIZE - 6, 4):
                if random.random() < 0.5:  # random subset
                    candidates.append((x, y))
        random.shuffle(candidates)
        
        # Directions: all 8 directions for variety
        all_dirs = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)]
        
        for bx, by in candidates:
            # Apply random offset
            ox = bx + random.randint(-2, 2)
            oy = by + random.randint(-2, 2)
            if not (0 <= ox < GRID_SIZE and 0 <= oy < GRID_SIZE):
                continue
            
            random.shuffle(all_dirs)
            for dx, dy in all_dirs:
                body = [(ox, oy), (ox - dx, oy - dy), (ox - dx * 2, oy - dy * 2)]
                # Check all body cells are in bounds and free
                if not all(0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE and (x, y) not in occupied_cells
                           for x, y in body):
                    continue
                # Check minimum separation from ALL occupied snake cells
                too_close = False
                for x, y in body:
                    for oxx, oyy in occupied_cells:
                        if abs(x - oxx) + abs(y - oyy) < min_sep:
                            too_close = True
                            break
                    if too_close:
                        break
                if not too_close:
                    return (body, (dx, dy))
        
        # Fallback: try original hardcoded positions without min_sep
        fallback_sides = [
            (5, 15, 1, 0), (24, 15, -1, 0), (15, 5, 0, 1), (15, 24, 0, -1),
            (5, 5, 1, 1), (24, 24, -1, -1), (5, 24, 1, -1), (24, 5, -1, 1),
            (10, 10, 1, 0), (20, 20, -1, 0), (10, 20, 0, -1), (20, 10, 0, 1),
        ]
        for sx, sy, dx, dy in fallback_sides:
            body = [(sx, sy), (sx - dx, sy - dy), (sx - dx * 2, sy - dy * 2)]
            if all(0 <= x < GRID_SIZE and 0 <= y < GRID_SIZE and (x, y) not in occupied_cells
                   for x, y in body):
                return (body, (dx, dy))
        return None

    def add_player(self, ws):
        pid = f"p{self.next_id}"
        self.next_id += 1
        color = PLAYER_COLORS[self.color_idx % len(PLAYER_COLORS)]
        self.color_idx += 1
        result = self.find_spawn_position()
        if result:
            snake, direction = result
        else:
            snake = [(15, 15), (14, 15), (13, 15)]
            direction = (1, 0)
        player = {
            'id': pid,
            'color': color,
            'snake': snake,
            'direction': direction,
            'next_direction': direction,
            'score': 0,
            'alive': True,
            'ws': ws,
        }
        self.players[ws] = player
        return player

    def respawn_player(self, player):
        result = self.find_spawn_position()
        if result:
            snake, direction = result
            player['snake'] = snake
            player['direction'] = direction
            player['next_direction'] = direction
            player['score'] = 0
            player['alive'] = True
            return True
        return False

    def remove_player(self, ws):
        if ws in self.players:
            del self.players[ws]

    def add_bot(self, difficulty='normal'):
        """Create an AI bot player"""
        pid = f"bot{self.next_id}"
        self.next_id += 1
        color = BOT_COLORS[self.bot_color_idx % len(BOT_COLORS)]
        self.bot_color_idx += 1

        delay = DIFFICULTY_DELAY.get(difficulty, 1)
        result = self.find_spawn_position()
        if result:
            snake, direction = result
        else:
            snake = [(15, 15), (14, 15), (13, 15)]
            direction = (1, 0)

        bot = {'id': pid, 'color': color, 'snake': snake,
               'direction': direction, 'next_direction': direction,
               'score': 0, 'alive': True, 'ws': None, 'is_bot': True,
               'respawn_timer': 0,
               'difficulty': difficulty, 'ai_timer': 0}
        self.bots.append(bot)
        print(f"[Bot] {pid} spawned ({color}) [{difficulty}]")
        return bot

    def bot_ai(self, bot):
        """Simple AI: pick safe direction closest to food, avoid obstacles"""
        if not bot['snake']:
            return
        head = bot['snake'][0]
        cur = bot['direction']
        # Find closest food
        closest_food = None
        closest_dist = 9999
        for f in self.foods:
            d = abs(head[0] - f[0]) + abs(head[1] - f[1])
            if d < closest_dist:
                closest_dist = d
                closest_food = f
        food = closest_food

        dirs = [(1, 0), (-1, 0), (0, 1), (0, -1)]
        reverse = (-cur[0], -cur[1])
        candidates = [d for d in dirs if d != reverse]

        best_dir = cur
        best_score = -9999

        # Collect all cells occupied by other snakes (to avoid)
        other_snake_cells = set()
        for p in self.players.values():
            if p['alive'] and p is not bot:
                for sx, sy in p['snake'][:20]:  # only check first 20 segments
                    other_snake_cells.add((sx, sy))
        for b in self.bots:
            if b['alive'] and b is not bot:
                for sx, sy in b['snake'][:20]:
                    other_snake_cells.add((sx, sy))

        for d in candidates:
            nx, ny = head[0] + d[0], head[1] + d[1]
            if not (0 <= nx < GRID_SIZE and 0 <= ny < GRID_SIZE):
                continue
            if (nx, ny) in bot['snake'][:-1]:
                continue
            hit = False
            for obs in self.obstacles:
                ox, oy = round(obs['x']), round(obs['y'])
                if ox <= nx < ox + obs['w'] and oy <= ny < oy + obs['h']:
                    hit = True; break
            if hit:
                continue
            if (nx, ny) in other_snake_cells:
                continue

            score = 0
            if food:
                score = -(abs(nx - food[0]) + abs(ny - food[1]))
            if d == cur:
                score += 3
            # 2-step lookahead: avoid dead ends
            nx2, ny2 = nx + d[0], ny + d[1]
            dead = False
            if not (0 <= nx2 < GRID_SIZE and 0 <= ny2 < GRID_SIZE):
                dead = True
            elif (nx2, ny2) in bot['snake'][:-2]:
                dead = True
            elif (nx2, ny2) in other_snake_cells:
                dead = True
            else:
                for obs in self.obstacles:
                    ox, oy = round(obs['x']), round(obs['y'])
                    if ox <= nx2 < ox + obs['w'] and oy <= ny2 < oy + obs['h']:
                        dead = True; break
            if dead:
                score -= 10

            if score > best_score:
                best_score = score
                best_dir = d

        bot['next_direction'] = best_dir

    def tick(self):
        self.tick_count += 1

        # Move obstacles
        for obs in self.obstacles:
            obs['moveTimer'] = (obs.get('moveTimer', 0) + 1)
            if obs['moveTimer'] >= OBSTACLE_MOVE_INTERVAL:
                obs['moveTimer'] = 0
                nx = round(obs['x']) + obs['vx']
                ny = round(obs['y']) + obs['vy']
                if self.is_obs_pos_free(obs, nx, ny):
                    obs['x'] = float(nx)
                    obs['y'] = float(ny)
                else:
                    # Try x only
                    try_x = round(obs['x']) + obs['vx']
                    if self.is_obs_pos_free(obs, try_x, round(obs['y'])):
                        obs['x'] = float(try_x)
                        obs['vy'] = -obs['vy']
                    else:
                        try_y = round(obs['y']) + obs['vy']
                        if self.is_obs_pos_free(obs, round(obs['x']), try_y):
                            obs['y'] = float(try_y)
                            obs['vx'] = -obs['vx']
                        else:
                            obs['vx'] = -obs['vx']
                            obs['vy'] = -obs['vy']

            obs['alpha'] = min(1.0, obs['alpha'] + 0.08)
            obs['rotation'] += obs['rotSpeed']
            obs['pulsePhase'] += obs['pulseSpeed']

        # Spawn obstacle
        self.obs_spawn_timer += 1
        if self.obs_spawn_timer >= OBSTACLE_SPAWN_INTERVAL:
            self.obs_spawn_timer = 0
            self.spawn_obstacle()

        # Run AI for all bots (with delay based on difficulty)
        for bot in self.bots:
            if bot['alive']:
                bot['ai_timer'] -= 1
                if bot['ai_timer'] <= 0:
                    self.bot_ai(bot)
                    # Reset timer: easy=2, normal=1, hard=0 ticks of delay
                    bot['ai_timer'] = DIFFICULTY_DELAY.get(bot['difficulty'], 1)

        # Move all alive players' snakes
        dead_this_tick = []
        for ws, player in self.players.items():
            if not player['alive']:
                continue

            player['direction'] = player['next_direction']
            dx, dy = player['direction']
            head = player['snake'][0]
            new_head = (head[0] + dx, head[1] + dy)

            # Wall
            if not (0 <= new_head[0] < GRID_SIZE and 0 <= new_head[1] < GRID_SIZE):
                dead_this_tick.append((ws, player, '撞墙'))
                continue

            # Self collision
            will_grow = any(new_head[0] == f[0] and new_head[1] == f[1] for f in self.foods)
            body_check = player['snake'] if will_grow else player['snake'][:-1]
            if new_head in body_check:
                dead_this_tick.append((ws, player, '咬到自己'))
                continue

            # Snake-to-snake collision
            hit_snake = self.check_snake_collision(new_head[0], new_head[1], player)
            if hit_snake:
                hit_name = f"{'🤖' if hit_snake.get('is_bot') else '👤'} {hit_snake['id']}"
                dead_this_tick.append((ws, player, f'撞到{hit_name}'))
                continue

            # Obstacle collision
            hit_obs = self.check_obstacle_collision(new_head[0], new_head[1])
            if hit_obs:
                char = CHARACTERS[hit_obs['charIdx']]
                dead_this_tick.append((ws, player, f"撞到{char['team']}的{char['label']}"))
                continue

            # Move
            player['snake'].insert(0, new_head)

            # Check food
            ate_idx = -1
            for i, f in enumerate(self.foods):
                if new_head[0] == f[0] and new_head[1] == f[1]:
                    ate_idx = i; break
            if ate_idx >= 0:
                player['score'] += 1
                del self.foods[ate_idx]
                self.spawn_food()
                if random.random() < BONUS_FOOD_CHANCE:
                    self.spawn_bonus_food()
            elif (self.bonus_food and new_head[0] == self.bonus_food['x']
                  and new_head[1] == self.bonus_food['y']):
                player['score'] += 3
                self.bonus_food = None
                self.bonus_timer = 0
            else:
                player['snake'].pop()

        # Mark dead (human players) + clear body so they don't visually persist
        for ws, player, reason in dead_this_tick:
            player['alive'] = False
            player['snake'] = [player['snake'][0]]  # keep only head as marker
            try:
                asyncio.create_task(self.send_to(ws, {
                    'type': 'died',
                    'reason': reason,
                    'score': player['score']
                }))
            except:
                pass

        # Move bots (same logic as players)
        for bot in self.bots:
            if not bot['alive']:
                continue
            bot['direction'] = bot['next_direction']
            dx, dy = bot['direction']
            head = bot['snake'][0]
            new_head = (head[0] + dx, head[1] + dy)
            if not (0 <= new_head[0] < GRID_SIZE and 0 <= new_head[1] < GRID_SIZE):
                bot['alive'] = False; bot['snake'] = [bot['snake'][0]]; bot['respawn_timer'] = 0; continue
            will_grow = any(new_head[0] == f[0] and new_head[1] == f[1] for f in self.foods)
            body_check = bot['snake'] if will_grow else bot['snake'][:-1]
            if new_head in body_check:
                bot['alive'] = False; bot['snake'] = [bot['snake'][0]]; bot['respawn_timer'] = 0; continue
            # Snake collision
            hit_snake = self.check_snake_collision(new_head[0], new_head[1], bot)
            if hit_snake:
                bot['alive'] = False; bot['snake'] = [bot['snake'][0]]; bot['respawn_timer'] = 0; continue
            hit_obs = self.check_obstacle_collision(new_head[0], new_head[1])
            if hit_obs:
                bot['alive'] = False; bot['snake'] = [bot['snake'][0]]; bot['respawn_timer'] = 0; continue
            bot['snake'].insert(0, new_head)
            ate_idx = -1
            for i, f in enumerate(self.foods):
                if new_head[0] == f[0] and new_head[1] == f[1]:
                    ate_idx = i; break
            if ate_idx >= 0:
                bot['score'] += 1
                del self.foods[ate_idx]
                self.spawn_food()
                if random.random() < BONUS_FOOD_CHANCE:
                    self.spawn_bonus_food()
            elif (self.bonus_food and new_head[0] == self.bonus_food['x']
                  and new_head[1] == self.bonus_food['y']):
                bot['score'] += 3
                self.bonus_food = None; self.bonus_timer = 0
            else:
                bot['snake'].pop()

        # Auto-respawn dead bots — DISABLED (bots stay dead; player must restart to fight again)
        # for bot in self.bots:
        #     if not bot['alive']:
        #         bot['respawn_timer'] += 1
        #         if bot['respawn_timer'] >= 30:
        #             if self.respawn_player(bot):
        #                 bot['respawn_timer'] = 0

        # Check win: all bots dead, at least one human alive
        self.winner_id = None
        if self.bots:
            alive_bots = sum(1 for b in self.bots if b['alive'])
            if alive_bots == 0:
                alive_humans = [p for p in self.players.values() if p['alive']]
                if alive_humans:
                    self.winner_id = alive_humans[0]['id']

        # Bonus food timer
        if self.bonus_food:
            self.bonus_timer -= 1
            if self.bonus_timer <= 0:
                self.bonus_food = None
                self.bonus_timer = 0

    def to_state_msg(self):
        snakes = []
        all_entities = list(self.players.values()) + self.bots
        for ps in all_entities:
            snakes.append({
                'id': ps['id'],
                'body': [[s[0], s[1]] for s in ps['snake']],
                'color': ps['color'],
                'score': ps['score'],
                'alive': ps['alive'],
                'direction': [ps['direction'][0], ps['direction'][1]],
                'isBot': ps.get('is_bot', False),
                'difficulty': ps.get('difficulty', 'normal'),
            })

        obs_list = []
        for o in self.obstacles:
            obs_list.append({
                'x': o['x'], 'y': o['y'],
                'w': o['w'], 'h': o['h'],
                'charIdx': o['charIdx'],
                'rotation': o['rotation'],
                'pulsePhase': o['pulsePhase'],
                'alpha': o['alpha'],
            })

        return {
            'type': 'state',
            'snakes': snakes,
            'foods': [[f[0], f[1]] for f in self.foods],
            'bonusFood': [self.bonus_food['x'], self.bonus_food['y']] if self.bonus_food else None,
            'obstacles': obs_list,
            'tickCount': self.tick_count,
            'paused': self.paused,
            'winner': self.winner_id,
        }

    async def send_to(self, ws, msg):
        try:
            await ws.send(json.dumps(msg))
        except:
            pass

    async def broadcast_state(self):
        if not self.players:
            return
        msg = json.dumps(self.to_state_msg())
        dead_ws = []
        for ws in list(self.players.keys()):
            try:
                await ws.send(msg)
            except:
                dead_ws.append(ws)
        for ws in dead_ws:
            self.remove_player(ws)


async def game_loop(state):
    """Main game loop: tick, then broadcast"""
    while True:
        if not state.paused:
            state.tick()
        await state.broadcast_state()
        tick_ms = BASE_TICK_MS
        await asyncio.sleep(tick_ms / 1000.0)


async def handle_connection(ws):
    """Handle a WebSocket connection"""
    player = state.add_player(ws)
    print(f"[+] Player {player['id']} connected ({player['color']}). Total: {len(state.players)}")

    # Send init message (with server IP)
    await ws.send(json.dumps({
        'type': 'init',
        'yourId': player['id'],
        'yourColor': player['color'],
        'gridSize': GRID_SIZE,
        'serverIp': SERVER_IP,
    }))

    # Notify others
    for other_ws in state.players:
        if other_ws != ws:
            try:
                await other_ws.send(json.dumps({
                    'type': 'playerJoined',
                    'id': player['id'],
                    'color': player['color'],
                }))
            except:
                pass

    try:
        async for raw_msg in ws:
            try:
                msg = json.loads(raw_msg)
            except:
                continue

            if msg.get('type') == 'request_bot':
                count = msg.get('count', 1)
                difficulty = msg.get('difficulty', 'normal')
                # Clear existing bots to prevent accumulation on reconnect
                state.bots.clear()
                for _ in range(min(count, 4)):
                    bot = state.add_bot(difficulty)
                    # Broadcast new player
                    for other_ws in state.players:
                        try:
                            await other_ws.send(json.dumps({
                                'type': 'playerJoined',
                                'id': bot['id'],
                                'color': bot['color'],
                                'isBot': True,
                            }))
                        except:
                            pass

            elif msg.get('type') == 'pause':
                state.paused = True
            elif msg.get('type') == 'resume':
                state.paused = False
            elif msg.get('type') == 'restart':
                # Reset game: clear obstacles, respawn all players AND bots
                state.obstacles.clear()
                state.foods.clear()
                state.obs_spawn_timer = 0
                for _ in range(MAX_FOODS):
                    state.spawn_food()
                state.paused = False
                for p in state.players.values():
                    state.respawn_player(p)
                # Respawn bots too (keep them, just reposition)
                for bot in state.bots:
                    state.respawn_player(bot)

            elif msg.get('type') == 'direction' and player['alive']:
                dx = msg.get('dx', 0)
                dy = msg.get('dy', 0)
                # Prevent 180° reversal
                cur = player['direction']
                if dx != 0 and dx == -cur[0]:
                    continue
                if dy != 0 and dy == -cur[1]:
                    continue
                if dx == 0 and dy == 0:
                    continue
                # Prevent same direction (no-op)
                if dx == cur[0] and dy == cur[1]:
                    continue
                player['next_direction'] = (dx, dy)

            elif msg.get('type') == 'respawn':
                if not player['alive']:
                    if state.respawn_player(player):
                        await ws.send(json.dumps({
                            'type': 'respawned',
                            'color': player['color'],
                        }))

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        state.remove_player(ws)
        print(f"[-] Player {player['id']} disconnected. Total: {len(state.players)}")
        # Notify others
        for other_ws in state.players:
            try:
                await other_ws.send(json.dumps({
                    'type': 'playerLeft',
                    'id': player['id'],
                }))
            except:
                pass

def get_lan_ip():
    """Detect the LAN IP address"""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.1)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return '127.0.0.1'

SERVER_IP = get_lan_ip()


def run_http_server():
    """Run a simple HTTP server to serve the game files"""
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    handler = SimpleHTTPRequestHandler
    httpd = HTTPServer(('0.0.0.0', HTTP_PORT), handler)
    print(f"[HTTP] Serving on http://0.0.0.0:{HTTP_PORT}")
    httpd.serve_forever()


async def main():
    global state
    state = GameState()
    # Initialize foods
    for _ in range(MAX_FOODS):
        state.spawn_food()

    # Start HTTP server in thread
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    # Start game loop
    loop_task = asyncio.create_task(game_loop(state))

    # Start WebSocket server
    print(f"[WS] WebSocket server on ws://0.0.0.0:{WS_PORT}")
    async with websockets.serve(handle_connection, '0.0.0.0', WS_PORT):
        await loop_task


if __name__ == '__main__':
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    print("=" * 50)
    print("  Snake Multiplayer Server")
    print("=" * 50)
    print()
    print(f"  HTTP: http://{SERVER_IP}:{HTTP_PORT}")
    print(f"  WS:   ws://{SERVER_IP}:{WS_PORT}")
    print()
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] 服务器已关闭")
