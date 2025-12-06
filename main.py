from pathlib import Path
import sys
import argparse
import random
import pygame

TILE_SIZE = 48
FPS = 60
ENEMY_STEP_DELAY = 30
ENEMY_MOVE_PATTERN = "horizontal"

ASSET_NAMES = {
    "player": "player",
    "wall": "wall",
    "empty": "empty",
    "collect": "collectible",
    "exit": "exit",
    "enemy": "enemy",
}


class GameError(Exception):
    pass


def load_map(path):
    p = Path(path)
    if not p.exists():
        raise GameError(f"Map file not found: {path}")
    text = p.read_text(encoding="utf-8")
    lines = [
        ln.rstrip("\n")
        for ln in text.splitlines()
        if ln.strip() != ""
    ]
    if not lines:
        raise GameError("Map file is empty")
    width = len(lines[0])
    for ln in lines:
        if len(ln) != width:
            raise GameError(
                "Map must be rectangular (all lines same length)"
            )
        for ch in ln:
            if ch not in {"0", "1", "C", "E", "P", "X"}:
                raise GameError(f"Invalid map character: {ch}")
    flat = "".join(lines)
    if flat.count("P") != 1:
        raise GameError(
            "Map must contain exactly one 'P' (player start)"
        )
    if "C" not in flat:
        raise GameError(
            "Map must contain at least one 'C' (collectible)"
        )
    if "E" not in flat:
        raise GameError(
            "Map must contain at least one 'E' (exit)"
        )
    grid = [list(row) for row in lines]
    return grid


def find_player(grid):
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch == "P":
                return x, y
    raise GameError("Player start 'P' not found")


def find_enemies(grid):
    enemies = []
    for y, row in enumerate(grid):
        for x, ch in enumerate(row):
            if ch == "X":
                enemies.append((x, y))
    return enemies


def load_frames_from_prefix(assets_dir, prefix, tile_size):
    ad = Path(assets_dir)
    if not ad.exists() or not ad.is_dir():
        return None
    candidates = sorted(
        [
            p
            for p in ad.iterdir()
            if p.is_file()
            and p.stem.lower().startswith(prefix.lower())
        ]
    )
    frames = []
    for c in candidates:
        try:
            img = pygame.image.load(str(c))
            surf = img.convert_alpha()
            surf = pygame.transform.scale(
                surf, (tile_size, tile_size)
            )
            frames.append(surf)
        except pygame.error:
            continue
    if frames:
        return frames
    fpath = ad / (prefix + ".png")
    if fpath.exists():
        try:
            img = pygame.image.load(str(fpath))
            surf = img.convert_alpha()
            surf = pygame.transform.scale(
                surf, (tile_size, tile_size)
            )
            return [surf]
        except pygame.error:
            return None
    return None


def make_fallback_surface(tile_size, kind):
    surf = pygame.Surface((tile_size, tile_size))
    if kind == "player":
        surf.fill((50, 180, 50))
    elif kind == "wall":
        surf.fill((70, 70, 70))
    elif kind == "empty":
        surf.fill((200, 200, 200))
    elif kind == "collect":
        surf.fill((200, 180, 50))
    elif kind == "exit":
        surf.fill((180, 50, 50))
    elif kind == "enemy":
        surf.fill((180, 30, 30))
    else:
        surf.fill((100, 100, 100))
    return surf


def load_assets(assets_dir, tile_size):
    assets = {}
    for key, prefix in ASSET_NAMES.items():
        frames = load_frames_from_prefix(
            assets_dir, prefix, tile_size
        )
        if not frames:
            fallback = make_fallback_surface(tile_size, key)
            assets[key] = [fallback]
        else:
            assets[key] = frames
    return assets


class Enemy:
    def __init__(self, x, y, pattern=ENEMY_MOVE_PATTERN):
        self.x = x
        self.y = y
        self.pattern = pattern
        self.step_dir = 1
        self.tick = 0

    def update(self, grid):
        self.tick += 1
        if self.tick < ENEMY_STEP_DELAY:
            return
        self.tick = 0
        rows = len(grid)
        cols = len(grid[0])
        moves = [(0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)]
        dx, dy = random.choice(moves)
        nx = self.x + dx
        ny = self.y + dy
        if not (0 <= nx < cols and 0 <= ny < rows):
            return
        if grid[ny][nx] == "1":
            return
        self.x = nx
        self.y = ny


def draw_grid(screen, grid, player_pos, enemies,
              assets, anim_indices):
    rows = len(grid)
    cols = len(grid[0])
    for y in range(rows):
        for x in range(cols):
            ch = grid[y][x]
            pos = (x * TILE_SIZE, y * TILE_SIZE)
            if ch == "1":
                screen.blit(assets["wall"][0], pos)
            else:
                screen.blit(assets["empty"][0], pos)
            if ch == "C":
                screen.blit(assets["collect"][0], pos)
            elif ch == "E":
                screen.blit(assets["exit"][0], pos)
    for e in enemies:
        frames = assets["enemy"]
        idx = anim_indices["enemy"] % len(frames)
        screen.blit(
            frames[idx],
            (e.x * TILE_SIZE, e.y * TILE_SIZE),
        )
    px, py = player_pos
    p_frames = assets["player"]
    idx = anim_indices["player"] % len(p_frames)
    screen.blit(
        p_frames[idx],
        (px * TILE_SIZE, py * TILE_SIZE),
    )


def render_text(screen, font, moves, remaining, msg=None,
                hint=None):
    moves_surf = font.render(
        f"Moves: {moves}", True, (255, 255, 255)
    )
    rem_surf = font.render(
        f"Remaining: {remaining}", True, (255, 255, 255)
    )
    screen.blit(moves_surf, (8, 8))
    screen.blit(rem_surf, (8, 32))
    if msg:
        w = screen.get_width()
        h = screen.get_height()
        s = font.render(msg, True, (255, 200, 50))
        rx = (w - s.get_width()) // 2
        ry = (h - s.get_height()) // 2
        screen.blit(s, (rx, ry))
    if hint:
        h_surf = font.render(hint, True, (200, 200, 200))
        screen.blit(h_surf, (8, h - 28))


def run_game(map_path, assets_dir):
    base_grid = load_map(map_path)
    cols = len(base_grid[0])
    rows = len(base_grid)
    width = cols * TILE_SIZE
    height = rows * TILE_SIZE

    pygame.init()
    screen = pygame.display.set_mode((width, height))
    pygame.display.set_caption("2D Collect Game")
    clock = pygame.time.Clock()

    assets = load_assets(assets_dir, TILE_SIZE)
    font = pygame.font.SysFont(None, 24)

    def init_level():
        grid_local = load_map(map_path)
        px, py = find_player(grid_local)
        grid_local[py][px] = "0"
        enemy_pos = find_enemies(grid_local)
        for ex, ey in enemy_pos:
            grid_local[ey][ex] = "0"
        enemies_local = [Enemy(x, y) for x, y in enemy_pos]
        remaining_local = sum(row.count("C") for row in grid_local)
        return grid_local, px, py, enemies_local, remaining_local

    grid, player_x, player_y, enemies, remaining = init_level()

    moves = 0
    anim_indices = {"player": 0, "enemy": 0}
    anim_timer = 0
    anim_delay = 8
    running = True
    game_over = False
    win = False

    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
                break
            if ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_ESCAPE:
                    running = False
                    break
                if game_over or win:
                    if ev.key == pygame.K_r:
                        grid, player_x, player_y, enemies, remaining = (
                            init_level()
                        )
                        moves = 0
                        anim_indices = {"player": 0, "enemy": 0}
                        anim_timer = 0
                        game_over = False
                        win = False
                    continue
                dx = 0
                dy = 0
                if ev.key == pygame.K_w:
                    dy = -1
                elif ev.key == pygame.K_s:
                    dy = 1
                elif ev.key == pygame.K_a:
                    dx = -1
                elif ev.key == pygame.K_d:
                    dx = 1
                if dx or dy:
                    nx = player_x + dx
                    ny = player_y + dy
                    if 0 <= nx < cols and 0 <= ny < rows:
                        t = grid[ny][nx]
                        if t != "1":
                            player_x = nx
                            player_y = ny
                            moves += 1
                            if t == "C":
                                remaining -= 1
                                grid[ny][nx] = "0"
                            for e in enemies:
                                if (player_x, player_y) == (e.x, e.y):
                                    game_over = True
                                    break
                            if (
                                t == "E"
                                and remaining == 0
                                and not game_over
                            ):
                                win = True
        if not game_over and not win:
            for e in enemies:
                e.update(grid)
            for e in enemies:
                if (player_x, player_y) == (e.x, e.y):
                    game_over = True
                    break
        anim_timer += 1
        if anim_timer >= anim_delay:
            anim_timer = 0
            anim_indices["player"] = (
                anim_indices["player"] + 1
            ) % len(assets["player"])
            anim_indices["enemy"] = (
                anim_indices["enemy"] + 1
            ) % len(assets["enemy"])
        screen.fill((30, 30, 30))
        draw_grid(
            screen,
            grid,
            (player_x, player_y),
            enemies,
            assets,
            anim_indices,
        )
        if game_over:
            render_text(
                screen,
                font,
                moves,
                remaining,
                msg="GAME OVER",
                hint="Press R to restart or ESC to quit",
            )
        elif win:
            render_text(
                screen,
                font,
                moves,
                remaining,
                msg="YOU WIN",
                hint="Press R to restart or ESC to quit",
            )
        else:
            render_text(screen, font, moves, remaining)
        pygame.display.flip()
        clock.tick(FPS)
    pygame.quit()
    return 0


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run 2D collect game."
    )
    parser.add_argument(
        "--map", "-m", default="map.txt", help="Path to map file"
    )
    parser.add_argument(
        "--assets", "-a", default="assets", help="Assets folder"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    try:
        sys.exit(run_game(args.map, args.assets))
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
