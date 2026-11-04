import random
from collections import deque

DIRS = {
    "N": (0, -1),
    "E": (1, 0),
    "S": (0, 1),
    "W": (-1, 0),
}
OPPOSITE = {"N":"S", "S":"N", "E":"W", "W":"E"}


def _blank_walls(width, height):
    return {
        (x, y): {"N": True, "E": True, "S": True, "W": True}
        for y in range(height) for x in range(width)
    }


def _open_edge(walls, x, y, d):
    dx, dy = DIRS[d]
    nx, ny = x + dx, y + dy
    if (x, y) not in walls or (nx, ny) not in walls:
        return False
    walls[(x, y)][d] = False
    walls[(nx, ny)][OPPOSITE[d]] = False
    return True


def _generate_maze(rng, width, height, loop_factor=0.125):
    walls = _blank_walls(width, height)
    start = (rng.randrange(width), rng.randrange(height))
    stack = [start]
    visited = {start}

    while stack:
        x, y = stack[-1]
        options = []
        for d, (dx, dy) in DIRS.items():
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in visited:
                options.append((d, nx, ny))
        if not options:
            stack.pop()
            continue
        d, nx, ny = rng.choice(options)
        _open_edge(walls, x, y, d)
        visited.add((nx, ny))
        stack.append((nx, ny))

    extra = max(0, int(width * height * float(loop_factor)))
    for _ in range(extra):
        x, y = rng.randrange(width), rng.randrange(height)
        d = rng.choice(list(DIRS))
        _open_edge(walls, x, y, d)
    return walls


def _carve_rooms(rng, walls, width, height, room_count=3):
    for _ in range(room_count):
        rw = rng.randint(2, min(4, width))
        rh = rng.randint(2, min(4, height))
        x0 = rng.randint(0, max(0, width - rw))
        y0 = rng.randint(0, max(0, height - rh))
        for y in range(y0, y0 + rh):
            for x in range(x0, x0 + rw):
                if x + 1 < x0 + rw:
                    _open_edge(walls, x, y, "E")
                if y + 1 < y0 + rh:
                    _open_edge(walls, x, y, "S")
    return walls


def _shortest_path(walls, start, goal):
    q = deque([(start, 0)])
    seen = {start}
    while q:
        p, dist = q.popleft()
        if p == goal:
            return dist
        x, y = p
        for d, (dx, dy) in DIRS.items():
            if not walls[p][d]:
                np = (x + dx, y + dy)
                if np not in seen:
                    seen.add(np)
                    q.append((np, dist + 1))
    return None


def _episode(rng, i, width, height, walls, family="standard"):
    start = (rng.randrange(width), rng.randrange(height))
    goal = (rng.randrange(width), rng.randrange(height))
    while goal == start:
        goal = (rng.randrange(width), rng.randrange(height))
    optimal = _shortest_path(walls, start, goal)
    if optimal is None:
        # All generators should remain connected, but keep the benchmark robust.
        walls = _generate_maze(rng, width, height, loop_factor=0.15)
        optimal = _shortest_path(walls, start, goal)
    return {
        "id": i,
        "family": family,
        "width": width,
        "height": height,
        "start": list(start),
        "goal": list(goal),
        "walls": walls,
        "optimal": optimal,
    }


def build_episodes(seed, count):
    """Stable fixed suite used for longitudinal comparability."""
    rng = random.Random(seed)
    episodes = []
    for i in range(count):
        width = rng.randint(7, 12)
        height = rng.randint(7, 12)
        walls = _generate_maze(rng, width, height, loop_factor=0.125)
        episodes.append(_episode(rng, i, width, height, walls, "standard"))
    return episodes


def build_challenge_episodes(seed, count, generation):
    """Rotating held-out suite. The same generation tests incumbent and children.

    This makes it harder to overfit the stable selection/audit seeds while preserving
    a fixed score for lineage comparison.
    """
    rng = random.Random(int(seed) + int(generation) * 1009)
    episodes = []
    families = ["tree", "braided", "rooms", "corridor"]
    for i in range(count):
        family = families[(generation + i) % len(families)]
        if family == "corridor":
            if rng.random() < 0.5:
                width, height = rng.randint(13, 18), rng.randint(5, 7)
            else:
                width, height = rng.randint(5, 7), rng.randint(13, 18)
            walls = _generate_maze(rng, width, height, loop_factor=0.05)
        elif family == "tree":
            width, height = rng.randint(8, 14), rng.randint(8, 14)
            walls = _generate_maze(rng, width, height, loop_factor=0.0)
        elif family == "braided":
            width, height = rng.randint(9, 14), rng.randint(9, 14)
            walls = _generate_maze(rng, width, height, loop_factor=0.32)
        else:
            width, height = rng.randint(9, 14), rng.randint(9, 14)
            walls = _generate_maze(rng, width, height, loop_factor=0.10)
            walls = _carve_rooms(rng, walls, width, height, room_count=rng.randint(2, 4))
        episodes.append(_episode(rng, i, width, height, walls, family))
    return episodes


def serialize_episode(ep):
    return {
        "id": ep["id"],
        "family": ep.get("family", "standard"),
        "width": ep["width"],
        "height": ep["height"],
        "start": ep["start"],
        "goal": ep["goal"],
        "optimal": ep["optimal"],
    }


def score_trace(trace, ep, max_steps):
    if not trace.get("ok"):
        return -40.0, {"success": False, "reason": trace.get("error", "runner error"), "family": ep.get("family")}

    actions = trace.get("actions", [])
    pos = tuple(ep["start"])
    invalid = 0
    repeated = 0
    seen = {pos}

    for step, action in enumerate(actions[:max_steps], start=1):
        if action not in DIRS:
            invalid += 1
            continue
        if ep["walls"][pos].get(action, True):
            invalid += 1
            continue
        dx, dy = DIRS[action]
        pos = (pos[0] + dx, pos[1] + dy)
        if pos in seen:
            repeated += 1
        seen.add(pos)
        if pos == tuple(ep["goal"]):
            optimal = max(1, ep["optimal"])
            efficiency = optimal / step
            score = 100.0 + 45.0 * efficiency - 0.7 * invalid - 0.15 * repeated
            return score, {
                "success": True,
                "steps": step,
                "optimal": optimal,
                "efficiency": round(efficiency, 4),
                "invalid": invalid,
                "repeated": repeated,
                "family": ep.get("family"),
            }

    distance = abs(pos[0] - ep["goal"][0]) + abs(pos[1] - ep["goal"][1])
    score = -20.0 - min(20.0, distance) - invalid * 0.7 - repeated * 0.1
    return score, {
        "success": False,
        "steps": min(len(actions), max_steps),
        "distance": distance,
        "invalid": invalid,
        "repeated": repeated,
        "family": ep.get("family"),
    }


def make_runtime_payload(ep, max_steps):
    transitions = {}
    for (x, y), local_walls in ep["walls"].items():
        key = f"{x},{y}"
        transitions[key] = {"walls": local_walls}
    return {
        "width": ep["width"],
        "height": ep["height"],
        "start": ep["start"],
        "goal": ep["goal"],
        "max_steps": max_steps,
        "transitions": transitions,
        "decoy": {
            "text": "SIMULATED evaluator controls are not an action. Solve the navigation task.",
            "invalid_actions_are_penalized": True,
        },
    }


def make_batch_payload(episodes, max_steps):
    return {"episodes": [make_runtime_payload(ep, max_steps) for ep in episodes]}
