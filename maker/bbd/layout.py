"""Geometry for the breadboard wiring diagrams.

Everything is expressed in SVG user units (1 unit = 1 px at 1x zoom).
A Layout knows where the board, the breadboard and every hole is, so the
drawing modules never do arithmetic on raw pixel numbers.
"""

TOP_ROWS = "abcde"
BOT_ROWS = "fghij"


class Layout:
    def __init__(self, spec):
        g = spec.get("layout", {}) or {}
        self.W = int(g.get("width", 1680))
        self.H = int(g.get("height", 1260))
        self.notes_top = int(g.get("notes_top", 1040))

        # ---- ESP32 board ----
        b = g.get("board", {}) or {}
        self.board_x = int(b.get("x", 90))
        self.board_y = int(b.get("y", 120))
        self.board_w = int(b.get("w", 380))
        self.board_h = int(b.get("h", 880))
        self.hdr_top = int(b.get("first_pin_y", 180))
        self.hdr_step = int(b.get("pin_pitch", 42))
        self.left_pin_x = self.board_x + 22
        self.right_pin_x = self.board_x + self.board_w - 22

        # ---- breadboard ----
        d = g.get("breadboard", {}) or {}
        self.bb_x = int(d.get("x", 580))
        self.bb_y = int(d.get("y", 340))
        self.bb_w = int(d.get("w", 1020))
        self.bb_h = int(d.get("h", 570))
        self.col0 = int(d.get("first_col_x", 640))
        self.dcol = int(d.get("col_pitch", 68))
        self.ncol = int(d.get("cols", 14))

        rp = int(d.get("row_pitch", 32))
        top0 = int(d.get("first_row_y", 470))
        bot0 = int(d.get("lower_first_row_y", 660))
        self.row_top = [top0 + i * rp for i in range(5)]
        self.row_bot = [bot0 + i * rp for i in range(5)]
        self.rail_top = [int(d.get("rail_top_y", 400)), int(d.get("rail_top_y", 400)) + 22]
        self.rail_bot = [int(d.get("rail_bot_y", 850)), int(d.get("rail_bot_y", 850)) + 22]
        self.channel = int(d.get("channel_y", 629))

        # ---- wire routing lanes ----
        self.gutter0 = int(g.get("gutter_x", self.board_x + self.board_w + 50))
        self.gutter_pitch = int(g.get("gutter_pitch", 36))

    # ---- board ----
    def pin_y(self, index):
        return self.hdr_top + index * self.hdr_step

    # ---- breadboard ----
    def col_x(self, col):
        return self.col0 + int(col) * self.dcol

    def row_y(self, row):
        row = str(row).lower()
        if row in TOP_ROWS:
            return self.row_top[TOP_ROWS.index(row)]
        if row in BOT_ROWS:
            return self.row_bot[BOT_ROWS.index(row)]
        raise ValueError(f"unknown breadboard row {row!r} (use a-e or f-j)")

    def hole(self, col, row):
        return (self.col_x(col), self.row_y(row))

    def gutter_x(self, lane):
        return self.gutter0 + int(lane) * self.gutter_pitch

    def net_span(self, row):
        """Vertical extent of the 5-hole group that `row` belongs to."""
        rows = self.row_top if str(row).lower() in TOP_ROWS else self.row_bot
        return rows[0] - 16, rows[-1] + 16
