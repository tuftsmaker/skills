"""Grid autorouter — an A* maze router for wires.

The lane router in `wires.py` is predictable but dumb: it sends every wire down
a fixed gutter and lets runs stack. This router lays a coarse grid over the
canvas and routes each wire with A*:

  - the board, breadboard margin and component bodies are obstacles
  - cells already used by earlier wires cost more (sequential rip-up style,
    so wires spread out instead of stacking)
  - turning costs extra, which keeps runs straight and readable
  - the breadboard itself is passable but expensive, so the router prefers
    the gutters and the centre channel

Wires are routed shortest-first; each finished path raises the cost of the
cells it occupies. Nothing is forbidden, so a path always exists as long as
the endpoints are on the canvas.
"""

import heapq

CELL = 16          # grid pitch in canvas units (wire stroke is 7px)
TURN_COST = 10      # extra cells charged for a 90-degree turn
WIRE_COST = 26     # extra cost for a cell an earlier wire already occupies
BOARD_COST = 400   # effectively impassable (kept finite so A* can escape)
BREADBOARD_COST = 5
HOLE_COST = 7
STUB = 40          # fixed outbound stub from a pad before A* takes over


def _cell(v):
    return int(round(v / CELL))


def _coord(c):
    return c * CELL


class Router:
    def __init__(self, L):
        self.L = L
        self.nx = L.W // CELL + 1
        self.ny = L.H // CELL + 1
        self.extra = {}          # (ix, iy) -> extra cost
        self.blocked = set()

    # -- geometry ---------------------------------------------------------
    def add_cost(self, ix, iy, amount):
        self.extra[(ix, iy)] = self.extra.get((ix, iy), 0) + amount

    def add_rect_cost(self, x, y, w, h, amount):
        for iy in range(_cell(y), _cell(y + h) + 1):
            for ix in range(_cell(x), _cell(x + w) + 1):
                self.add_cost(ix, iy, amount)

    def block(self, ix, iy):
        self.blocked.add((ix, iy))

    def block_rect(self, x, y, w, h):
        for iy in range(_cell(y), _cell(y + h) + 1):
            for ix in range(_cell(x), _cell(x + w) + 1):
                self.block(ix, iy)

    def unblock_rect(self, x, y, w, h):
        for iy in range(_cell(y), _cell(y + h) + 1):
            for ix in range(_cell(x), _cell(x + w) + 1):
                self.blocked.discard((ix, iy))

    def inside(self, ix, iy):
        return 0 <= ix < self.nx and 0 <= iy < self.ny

    def cell_cost(self, ix, iy):
        if (ix, iy) in self.blocked:
            return BOARD_COST
        return 1 + self.extra.get((ix, iy), 0)

    # -- routing ----------------------------------------------------------
    def route(self, start, goal, first_dirs=None):
        """A* between two canvas points; returns a list of canvas points."""
        s = (_cell(start[0]), _cell(start[1]))
        g = (_cell(goal[0]), _cell(goal[1]))
        if not self.inside(*s) or not self.inside(*g):
            return [start, goal]

        DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))
        best = {}
        pq = []
        for d, (dx, dy) in enumerate(DIRS):
            if first_dirs and d not in first_dirs:
                continue
            heapq.heappush(pq, (0, s[0], s[1], d, None))

        came = {}
        goal_state = None
        while pq:
            cost, ix, iy, d, parent = heapq.heappop(pq)
            state = (ix, iy, d)
            if state in best:
                continue
            best[state] = cost
            came[state] = parent
            if (ix, iy) == g:
                goal_state = state
                break
            for nd, (dx, dy) in enumerate(DIRS):
                nx, ny = ix + dx, iy + dy
                if not self.inside(nx, ny):
                    continue
                step = self.cell_cost(nx, ny)
                if nd != d:
                    step += TURN_COST
                nstate = (nx, ny, nd)
                if nstate in best:
                    continue
                heapq.heappush(pq, (cost + step, nx, ny, nd, state))

        if goal_state is None:
            return [start, goal]

        cells = []
        state = goal_state
        while state is not None:
            cells.append((state[0], state[1]))
            state = came.get(state)
        cells.reverse()

        # keep the exact endpoints, simplify the middle to corner points
        pts = [start] + [(_coord(ix), _coord(iy)) for ix, iy in cells[1:-1]] + [goal]
        return simplify(pts)


def simplify(pts):
    """Drop points that lie on the straight line between their neighbours."""
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        a, b, c = out[-1], pts[i], pts[i + 1]
        if (a[0] == b[0] == c[0]) or (a[1] == b[1] == c[1]):
            continue
        if b != out[-1]:
            out.append(b)
    out.append(pts[-1])
    return out


def _endpoint_cells(L, board, spec, parts, end):
    """Return (point, outward directions) for a wire endpoint."""
    from .wires import parse_endpoint
    kind = parse_endpoint(L, board, end, parts)
    if kind[0] == "bb":
        col, row, (x, y) = kind[1], kind[2], kind[2] and kind[2]
        return (x, y), None
    if kind[0] == "part":
        return kind[1], None
    # board pin / pad
    x, y = kind[1]
    if L.mount == "extension":
        outward = (-1, 1) if x < L.board_x + L.board_w / 2 else (0, 0)
        dirs = {1} if x < L.board_x + L.board_w / 2 else {0}
    else:
        dirs = {1} if x < L.board_x + L.board_w / 2 else {0}
    return (x, y), dirs


def route_all(L, board, spec, parts):
    """Route every wire on the grid. Returns a list of point lists."""
    from . import components as comp
    from .wires import parse_endpoint

    wires = spec.get("wires") or []
    r = Router(L)

    # --- obstacles ---
    # board (its pads stay reachable through the fixed stubs)
    r.block_rect(L.board_x, L.board_y, L.board_w, L.board_h)
    # component bodies
    for c in spec.get("components") or []:
        rect = comp.component_bounds(L, c)
        if rect:
            r.block_rect(*rect)
    # breadboard: passable but costly, and hole cells cost extra
    if not L.bb_hidden:
        r.add_rect_cost(L.bb_x, L.bb_y, L.bb_w, L.bb_h, BREADBOARD_COST)
        for row in L.row_top + L.row_bot:
            for i in range(L.ncol):
                r.add_cost(_cell(L.col_x(i)), _cell(row), HOLE_COST)
    # no-go bands: the title strip and the notes area
    r.add_rect_cost(0, 0, L.W, 150, 400)
    r.add_rect_cost(0, L.notes_top - 10, L.W, 120, 400)

    # bias toward the routing lanes: preferred cells are the gutter columns,
    # the corridor rows, the centre channel and the columns above/below each
    # hole that a wire has to reach
    preferred = set()
    for lane in range(9):
        for x in (L.gutter_x(lane), L.left_gutter_x(lane)):
            cx = _cell(x)
            for iy in range(_cell(160), _cell(L.notes_top - 20)):
                preferred.add((cx, iy))
        cy = _cell(L.corridor_y(lane))
        for ix in range(_cell(L.left_gutter_x(8)), _cell(L.gutter_x(0)) + 1):
            preferred.add((ix, cy))
    for iy in range(_cell(L.channel - 40), _cell(L.channel + 40)):
        for ix in range(_cell(L.col_x(0) - 60), _cell(L.col_x(L.ncol - 1) + 60)):
            preferred.add((ix, iy))
    for ix in range(r.nx):
        for iy in range(r.ny):
            if (ix, iy) not in preferred:
                r.add_cost(ix, iy, 2)

    # keep the pads on the board edge reachable: carve a stub out of the board
    for w in wires:
        for end in (w["from"], w["to"]):
            kind = parse_endpoint(L, board, end, parts)
            if kind[0] != "board":
                continue
            x, y = kind[1]
            if x < L.board_x + L.board_w / 2:
                r.unblock_rect(L.board_x - 10, y - 12, (x - L.board_x) + 22, 24)
            else:
                r.unblock_rect(x - 12, y - 12, (L.board_x + L.board_w - x) + 22, 24)

    # --- route, shortest first so long runs claim the roomy channels ---
    order = []
    for i, w in enumerate(wires):
        a, _ = _endpoint_cells(L, board, w, parts, w["from"])
        b, _ = _endpoint_cells(L, board, w, parts, w["to"])
        import math
        order.append((math.dist(a, b), i))
    order.sort()

    paths = [None] * len(wires)
    for _, i in order:
        w = wires[i]
        a, dirs_a = _endpoint_cells(L, board, w, parts, w["from"])
        b, dirs_b = _endpoint_cells(L, board, w, parts, w["to"])
        pts = r.route(a, b, dirs_a)
        paths[i] = pts
        # reserve the cells this wire used
        for (x, y) in pts:
            r.add_cost(_cell(x), _cell(y), WIRE_COST)
    return paths