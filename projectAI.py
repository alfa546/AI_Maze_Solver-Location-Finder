import tkinter as tk
from tkinter import ttk, messagebox
import numpy as np
import time
import threading
import requests
import json
from collections import deque
import webbrowser
import os
import subprocess
import sys
from pathlib import Path

# ═══════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════
ROWS      = 20
COLS      = 20
CELL_SIZE = 32
PADDING   = 2

# ── Color Palette ──
BG_APP      = "#0D1117"
BG_PANEL    = "#161B22"
BG_CARD     = "#1C2128"
BORDER_CLR  = "#30363D"
ACCENT      = "#2D5A8E"
ACCENT2     = "#3FB950"
ACCENT3     = "#F78166"
ACCENT4     = "#D2A8FF"
TEXT_PRI    = "#E6EDF3"
TEXT_SEC    = "#8B949E"

CLR_EMPTY   = "#1C2128"
CLR_WALL    = "#0D1117"
CLR_WALL_BD = "#21262D"
CLR_START   = "#3FB950"
CLR_END     = "#F78166"
CLR_VISITED   = "#2188FF"
CLR_QUEUE     = "#1D4ED8"
CLR_PATH      = "#8E1616"
CLR_GRID      = "#272B2F"

# ════════════════════════════════════
#  REAL MAP ROUTING  (OpenStreetMap + OSRM )
# ════════════════════════════════════
def geocode_city(name):
    """Convert city name → (lat, lon) using Nominatim (free)"""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": name, "format": "json", "limit": 1}
    headers = {"User-Agent": "MazeSolverApp/1.0"}
    try:
        r = requests.get(url, params=params, headers=headers, timeout=8)
        data = r.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"]), data[0]["display_name"]
        return None
    except Exception as e:
        return None

def get_route(start_coords, end_coords):
    """Get real road routes using OSRM (free, no key needed) - Returns list of route dicts"""
    slat, slon = start_coords
    elat, elon = end_coords
    # Added alternatives=true to get multiple paths
    url = (f"https://router.project-osrm.org/route/v1/driving/"
           f"{slon},{slat};{elon},{elat}"
           f"?overview=full&annotations=false&geometries=geojson&steps=true&alternatives=true")
    headers = {"User-Agent": "MazeSolverApp/1.0"}
    try:
        r = requests.get(url, headers=headers, timeout=15)
        data = r.json()
        if data.get("code") == "Ok" and "routes" in data:
            all_routes = []
            for r_data in data["routes"]:
                dist_km = r_data["distance"] / 1000
                dur_min = r_data["duration"] / 60
                
                route_coords = []
                if "geometry" in r_data and r_data["geometry"]:
                    geom = r_data["geometry"]
                    if isinstance(geom, dict) and "coordinates" in geom:
                        coords = geom["coordinates"]
                        route_coords = [[float(lat), float(lon)] for lon, lat in coords]
                
                all_routes.append({
                    'distance': dist_km,
                    'duration': dur_min,
                    'coords': route_coords
                })
            return all_routes
        return None
    except Exception as e:
        print(f"Route error: {e}")
        return None

def haversine_km(lat1, lon1, lat2, lon2):
    """Straight-line distance between two coords (km)"""
    import math
    R = 6371
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(d_lon/2)**2)
    return R * 2 * math.asin(math.sqrt(a))

# ═══════════════════════════════════════════════════════
#  MAIN APP
# ═══════════════════════════════════════════════════════
class MazeSolverPro:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Maze Solver PRO — DFS & BFS + Real Map Routing")
        self.root.configure(bg=BG_APP)
        self.root.resizable(False, False)

        self.grid    = np.zeros((ROWS, COLS), dtype=int)
        self.start   = None
        self.end     = None
        self.mode    = tk.StringVar(value="wall")
        self.algo    = tk.StringVar(value="bfs")
        self.speed   = tk.IntVar(value=50)
        self.solving = False
        self.cells   = {}
        self.stats   = {"visited": 0, "path": 0, "time": 0.0, "algo": "-"}
        self._drag   = None

        self._build_ui()
        self._draw_grid()

    # ───────────────────────────────────────────────────
    #  UI
    # ───────────────────────────────────────────────────
    def _build_ui(self):
        # Title
        hdr = tk.Frame(self.root, bg=BG_APP, pady=12)
        hdr.pack(fill="x", padx=20)
        tk.Label(hdr, text="AI MAZE SOLVER",
                 font=("Courier New", 17, "bold"),
                 fg=ACCENT, bg=BG_APP).pack(side="left")
        tk.Label(hdr, text="DFS  •  BFS Shortest Path  •  Real Map Routing",
                 font=("Courier New", 9), fg=TEXT_SEC, bg=BG_APP).pack(
                     side="left", padx=14, pady=2)

        main = tk.Frame(self.root, bg=BG_APP)
        main.pack(fill="both", padx=20, pady=(0, 16))

        self._build_left_panel(main)
        self._build_canvas(main)
        self._build_right_panel(main)

    # ── Left Panel ──────────────────────────────────────
    def _build_left_panel(self, parent):
        p = tk.Frame(parent, bg=BG_PANEL, width=200,
                     highlightthickness=1, highlightbackground=BORDER_CLR)
        p.pack(side="left", fill="y")
        p.pack_propagate(False)

        def sec(txt):
            tk.Frame(p, bg=BORDER_CLR, height=1).pack(fill="x", padx=12, pady=(12,0))
            tk.Label(p, text=txt.upper(), font=("Courier New", 8, "bold"),
                     fg=TEXT_SEC, bg=BG_PANEL).pack(anchor="w", padx=12, pady=(4,2))

        # Drawing mode
        sec("Drawing Mode")
        self._mode_btns = {}
        modes = [("wall","Walls",CLR_WALL_BD),("erase","Erase",BG_CARD),
                 ("start","Start Point",CLR_START),("end","End Point",CLR_END)]
        mf = tk.Frame(p, bg=BG_PANEL)
        mf.pack(fill="x", padx=12, pady=6)
        for val, lbl, clr in modes:
            b = self._mode_btn(mf, lbl, clr, val)
            b.pack(fill="x", pady=2)
            self._mode_btns[val] = b
        self._sync_mode_btns()

        # Algorithm
        sec("Algorithm")
        af = tk.Frame(p, bg=BG_PANEL)
        af.pack(fill="x", padx=12, pady=6)
        self._algo_btns = {}
        algos = [("bfs", "BFS — Shortest Path", ACCENT4),
                 ("dfs", "DFS — Deep Search",   ACCENT)]
        for val, lbl, clr in algos:
            b = self._algo_btn(af, lbl, clr, val)
            b.pack(fill="x", pady=2)
            self._algo_btns[val] = b
        self._sync_algo_btns()

        # Speed
        sec("Speed")
        sf = tk.Frame(p, bg=BG_PANEL)
        sf.pack(fill="x", padx=12, pady=6)
        sh = tk.Frame(sf, bg=BG_PANEL)
        sh.pack(fill="x")
        tk.Label(sh, text="Slow", font=("Courier New",8),
                 fg=TEXT_SEC, bg=BG_PANEL).pack(side="left")
        tk.Label(sh, text="Fast", font=("Courier New",8),
                 fg=TEXT_SEC, bg=BG_PANEL).pack(side="right")
        tk.Scale(sf, from_=1, to=100, orient="horizontal",
                 variable=self.speed, bg=BG_PANEL, fg=ACCENT,
                 troughcolor=BG_CARD, highlightthickness=0,
                 bd=0, showvalue=False, sliderrelief="flat",
                 sliderlength=16).pack(fill="x")

        # Actions
        sec("Actions")
        act = tk.Frame(p, bg=BG_PANEL)
        act.pack(fill="x", padx=12, pady=6)
        self.solve_btn = self._act_btn(act,"▶  SOLVE",ACCENT,self._start_solve)
        self.solve_btn.pack(fill="x", pady=2)
        self._act_btn(act,"⟳  Random Maze",TEXT_SEC,self._random_maze).pack(fill="x",pady=2)
        self._act_btn(act,"✕  Clear All",ACCENT3,self._clear_all).pack(fill="x",pady=2)
        self._act_btn(act,"↺  Clear Path",TEXT_SEC,self._clear_path).pack(fill="x",pady=2)

        # Legend
        sec("Legend")
        lf = tk.Frame(p, bg=BG_PANEL)
        lf.pack(fill="x", padx=12, pady=6)
        legends = [(CLR_START,"Start"),(CLR_END,"End"),
                   (CLR_VISITED,"Searching"),(CLR_PATH,"Final Path"),
                   (CLR_WALL_BD,"Wall")]
        for clr, lbl in legends:
            r = tk.Frame(lf, bg=BG_PANEL)
            r.pack(fill="x", pady=1)
            tk.Frame(r, bg=clr, width=10, height=10,
                     highlightthickness=1,
                     highlightbackground=BORDER_CLR).pack(side="left",padx=(0,6))
            tk.Label(r, text=lbl, font=("Courier New",8),
                     fg=TEXT_SEC, bg=BG_PANEL).pack(side="left")

        # Stats
        sec("Statistics")
        self.stats_frame = tk.Frame(p, bg=BG_PANEL)
        self.stats_frame.pack(fill="x", padx=12, pady=6)
        self._refresh_stats()

    # ── Canvas ──────────────────────────────────────────
    def _build_canvas(self, parent):
        cf = tk.Frame(parent, bg=BG_CARD,
                      highlightthickness=1, highlightbackground=BORDER_CLR)
        cf.pack(side="left", padx=10)
        w = COLS*(CELL_SIZE+PADDING)+PADDING
        h = ROWS*(CELL_SIZE+PADDING)+PADDING
        self.canvas = tk.Canvas(cf, width=w, height=h,
                                bg="#161B22", bd=0,
                                highlightthickness=0, cursor="crosshair")
        self.canvas.pack(padx=8, pady=8)
        self.canvas.bind("<Button-1>",        self._click)
        self.canvas.bind("<B1-Motion>",       self._drag_move)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self,"_drag",None))

    # ── Right Panel (Real Map) ───────────────────────────
    def _build_right_panel(self, parent):
        p = tk.Frame(parent, bg=BG_PANEL, width=240,
                     highlightthickness=1, highlightbackground=BORDER_CLR)
        p.pack(side="left", fill="y", padx=(10,0))
        p.pack_propagate(False)

        def sec(txt):
            tk.Frame(p, bg=BORDER_CLR, height=1).pack(fill="x", padx=12, pady=(12,0))
            tk.Label(p, text=txt.upper(), font=("Courier New", 8, "bold"),
                     fg=TEXT_SEC, bg=BG_PANEL).pack(anchor="w", padx=12, pady=(4,2))

        # Header
        tk.Frame(p, bg=BORDER_CLR, height=1).pack(fill="x", padx=12, pady=(14,0))
        hdr = tk.Frame(p, bg=BG_PANEL)
        hdr.pack(fill="x", padx=12, pady=(6,0))
        tk.Label(hdr, text="REAL MAP ROUTING",
                 font=("Courier New", 10, "bold"),
                 fg=ACCENT2, bg=BG_PANEL).pack(anchor="w")
        tk.Label(hdr, text="Powered by OpenStreetMap (Free)",
                 font=("Courier New", 8),
                 fg=TEXT_SEC, bg=BG_PANEL).pack(anchor="w")

        sec("Start City")
        sf = tk.Frame(p, bg=BG_PANEL)
        sf.pack(fill="x", padx=12, pady=4)
        self.start_city = tk.Entry(sf, font=("Courier New", 10),
                                   bg=BG_CARD, fg=TEXT_PRI,
                                   insertbackground=ACCENT,
                                   relief="flat", bd=6,
                                   highlightthickness=1,
                                   highlightbackground=BORDER_CLR)
        self.start_city.pack(fill="x")
        self.start_city.insert(0, "Lahore, Pakistan")

        sec("End City")
        ef = tk.Frame(p, bg=BG_PANEL)
        ef.pack(fill="x", padx=12, pady=4)
        self.end_city = tk.Entry(ef, font=("Courier New", 10),
                                 bg=BG_CARD, fg=TEXT_PRI,
                                 insertbackground=ACCENT,
                                 relief="flat", bd=6,
                                 highlightthickness=1,
                                 highlightbackground=BORDER_CLR)
        self.end_city.pack(fill="x")
        self.end_city.insert(0, "Karachi, Pakistan")

        sec("Actions")
        mf = tk.Frame(p, bg=BG_PANEL)
        mf.pack(fill="x", padx=12, pady=6)
        self.map_btn = self._act_btn(mf, "🗺  Find Route + Map",
                                     ACCENT2, self._find_map_route)
        self.map_btn.pack(fill="x", pady=2)
        self.map_btn2 = self._act_btn(mf, "🌍 Open Interactive Map",
                                      ACCENT4, self._open_interactive_map)
        self.map_btn2.pack(fill="x", pady=2)

        # Result box
        sec("Route Result")
        rf = tk.Frame(p, bg=BG_PANEL)
        rf.pack(fill="x", padx=12, pady=6)

        self.map_result = tk.Frame(rf, bg=BG_CARD,
                                   highlightthickness=1,
                                   highlightbackground=BORDER_CLR)
        self.map_result.pack(fill="x")

        self.lbl_from   = self._result_row(self.map_result, "From", "—")
        self.lbl_to     = self._result_row(self.map_result, "To",   "—")
        self.lbl_dist   = self._result_row(self.map_result, "Distance", "—")
        self.lbl_dur    = self._result_row(self.map_result, "Drive Time", "—")
        self.lbl_air    = self._result_row(self.map_result, "Straight", "—")

        # Status
        self.map_status = tk.Label(p, text="Enter cities and click Find Route",
                                   font=("Courier New", 8),
                                   fg=TEXT_SEC, bg=BG_PANEL,
                                   wraplength=210, justify="left")
        self.map_status.pack(padx=12, pady=6, anchor="w")

        # Info note
        sec("How It Works")
        tk.Label(p,
                 text="Uses real road network data\nfrom OpenStreetMap.\n\n"
                      "Routing engine: OSRM\n(Open Source Routing)\n\n"
                      "No API key needed.\n100% Free forever.",
                 font=("Courier New", 8),
                 fg=TEXT_SEC, bg=BG_PANEL,
                 justify="left").pack(padx=12, pady=4, anchor="w")

    def _result_row(self, parent, label, value):
        row = tk.Frame(parent, bg=BG_CARD)
        row.pack(fill="x", padx=8, pady=3)
        tk.Label(row, text=label+":", font=("Courier New", 8),
                 fg=TEXT_SEC, bg=BG_CARD, width=9,
                 anchor="w").pack(side="left")
        lbl = tk.Label(row, text=value, font=("Courier New", 9, "bold"),
                       fg=ACCENT2, bg=BG_CARD, anchor="w")
        lbl.pack(side="left", padx=(4,0))
        return lbl

    # ── Widget helpers ──────────────────────────────────
    def _mode_btn(self, parent, text, color, value):
        def cmd():
            self.mode.set(value)
            self._sync_mode_btns()
        f = tk.Frame(parent, bg=BG_CARD, cursor="hand2",
                     highlightthickness=1, highlightbackground=BORDER_CLR)
        tk.Frame(f, bg=color, width=10, height=10).pack(side="left", padx=(7,5), pady=7)
        lbl = tk.Label(f, text=text, font=("Courier New", 9),
                       fg=TEXT_PRI, bg=BG_CARD, cursor="hand2")
        lbl.pack(side="left")
        for w in [f, lbl]:
            w.bind("<Button-1>", lambda e, c=cmd: c())
        f._val = value
        return f

    def _algo_btn(self, parent, text, color, value):
        def cmd():
            self.algo.set(value)
            self._sync_algo_btns()
        f = tk.Frame(parent, bg=BG_CARD, cursor="hand2",
                     highlightthickness=1, highlightbackground=BORDER_CLR)
        tk.Frame(f, bg=color, width=10, height=10).pack(side="left", padx=(7,5), pady=7)
        lbl = tk.Label(f, text=text, font=("Courier New", 9),
                       fg=TEXT_PRI, bg=BG_CARD, cursor="hand2")
        lbl.pack(side="left")
        for w in [f, lbl]:
            w.bind("<Button-1>", lambda e, c=cmd: c())
        f._val = value
        return f

    def _act_btn(self, parent, text, color, cmd):
        return tk.Button(parent, text=text,
                         font=("Courier New", 9, "bold"),
                         fg=color, bg=BG_CARD,
                         activeforeground=color,
                         activebackground=BORDER_CLR,
                         bd=0, pady=7, cursor="hand2",
                         relief="flat", highlightthickness=1,
                         highlightbackground=BORDER_CLR,
                         command=cmd)

    def _sync_mode_btns(self):
        cur = self.mode.get()
        for val, btn in self._mode_btns.items():
            btn.configure(highlightbackground=ACCENT if val==cur else BORDER_CLR)

    def _sync_algo_btns(self):
        cur = self.algo.get()
        for val, btn in self._algo_btns.items():
            btn.configure(highlightbackground=ACCENT if val==cur else BORDER_CLR)

    def _refresh_stats(self):
        for w in self.stats_frame.winfo_children():
            w.destroy()
        items = [
            ("Algorithm",  self.stats["algo"]),
            ("Visited",    str(self.stats["visited"])),
            ("Path Steps", str(self.stats["path"])),
            ("Time",       f"{self.stats['time']:.2f}s"),
        ]
        for lbl, val in items:
            row = tk.Frame(self.stats_frame, bg=BG_CARD,
                           highlightthickness=1, highlightbackground=BORDER_CLR)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=lbl, font=("Courier New", 8),
                     fg=TEXT_SEC, bg=BG_CARD).pack(side="left", padx=7, pady=4)
            clr = ACCENT4 if self.stats["algo"]=="DFS" else ACCENT
            tk.Label(row, text=val, font=("Courier New", 8, "bold"),
                     fg=clr, bg=BG_CARD).pack(side="right", padx=7)

    # ───────────────────────────────────────────────────
    #  GRID
    # ───────────────────────────────────────────────────
    def _cell_xy(self, r, c):
        x1 = PADDING + c*(CELL_SIZE+PADDING)
        y1 = PADDING + r*(CELL_SIZE+PADDING)
        return x1, y1, x1+CELL_SIZE, y1+CELL_SIZE

    def _draw_grid(self):
        self.canvas.delete("all")
        self.cells.clear()
        for r in range(ROWS):
            for c in range(COLS):
                x1,y1,x2,y2 = self._cell_xy(r,c)
                rid = self.canvas.create_rectangle(
                    x1,y1,x2,y2, fill=CLR_EMPTY, outline=CLR_GRID, width=1)
                self.cells[(r,c)] = rid

    def _set_cell(self, r, c, fill, outline=None):
        rid = self.cells.get((r,c))
        if rid:
            self.canvas.itemconfig(rid, fill=fill,
                                   outline=outline or CLR_GRID)

    def _redraw_cell(self, r, c):
        if (r,c)==self.start:
            self._set_cell(r,c,CLR_START,CLR_START)
        elif (r,c)==self.end:
            self._set_cell(r,c,CLR_END,CLR_END)
        elif self.grid[r,c]==1:
            self._set_cell(r,c,CLR_WALL,CLR_WALL_BD)
        else:
            self._set_cell(r,c,CLR_EMPTY,CLR_GRID)

    def _put_label(self, r, c, txt):
        x1,y1,x2,y2 = self._cell_xy(r,c)
        self.canvas.create_text((x1+x2)//2,(y1+y2)//2,
                                 text=txt,
                                 font=("Courier New",10,"bold"),
                                 fill="white", tags="lbl")

    def _sync_labels(self):
        self.canvas.delete("lbl")
        if self.start: self._put_label(*self.start,"S")
        if self.end:   self._put_label(*self.end,  "E")

    # ───────────────────────────────────────────────────
    #  MOUSE
    # ───────────────────────────────────────────────────
    def _to_cell(self, x, y):
        c = x//(CELL_SIZE+PADDING)
        r = y//(CELL_SIZE+PADDING)
        if 0<=r<ROWS and 0<=c<COLS:
            return r,c
        return None

    def _click(self, e):
        if self.solving: return
        cell = self._to_cell(e.x, e.y)
        if cell: self._apply(cell); self._drag = cell

    def _drag_move(self, e):
        if self.solving: return
        cell = self._to_cell(e.x, e.y)
        if cell and cell!=self._drag and self.mode.get() in ("wall","erase"):
            self._apply(cell); self._drag = cell

    def _apply(self, cell):
        r,c = cell
        m = self.mode.get()
        if m=="wall":
            if cell not in (self.start, self.end):
                self.grid[r,c]=1
                self._set_cell(r,c,CLR_WALL,CLR_WALL_BD)
        elif m=="erase":
            self.grid[r,c]=0
            if cell==self.start: self.start=None
            if cell==self.end:   self.end=None
            self._set_cell(r,c,CLR_EMPTY,CLR_GRID)
            self._sync_labels()
        elif m=="start":
            if cell!=self.end and self.grid[r,c]==0:
                old=self.start; self.start=cell
                if old: self._redraw_cell(*old)
                self._set_cell(r,c,CLR_START,CLR_START)
                self._sync_labels()
        elif m=="end":
            if cell!=self.start and self.grid[r,c]==0:
                old=self.end; self.end=cell
                if old: self._redraw_cell(*old)
                self._set_cell(r,c,CLR_END,CLR_END)
                self._sync_labels()

    # ───────────────────────────────────────────────────
    #  MAZE GEN / CLEAR
    # ───────────────────────────────────────────────────
    def _random_maze(self):
        if self.solving: return
        self.grid=np.zeros((ROWS,COLS),dtype=int)
        self.start=(0,0); self.end=(ROWS-1,COLS-1)
        for r in range(ROWS):
            for c in range(COLS):
                if np.random.random()<0.28 and (r,c) not in ((0,0),(ROWS-1,COLS-1)):
                    self.grid[r,c]=1
        self._draw_grid()
        for r in range(ROWS):
            for c in range(COLS):
                self._redraw_cell(r,c)
        self._sync_labels()
        self.stats={"visited":0,"path":0,"time":0.0,"algo":"-"}
        self._refresh_stats()

    def _clear_all(self):
        if self.solving: return
        self.grid=np.zeros((ROWS,COLS),dtype=int)
        self.start=None; self.end=None
        self._draw_grid()
        self.stats={"visited":0,"path":0,"time":0.0,"algo":"-"}
        self._refresh_stats()

    def _clear_path(self):
        if self.solving: return
        for r in range(ROWS):
            for c in range(COLS):
                if self.grid[r,c]==0:
                    self._set_cell(r,c,CLR_EMPTY,CLR_GRID)
        if self.start: self._set_cell(*self.start,CLR_START,CLR_START)
        if self.end:   self._set_cell(*self.end,  CLR_END,  CLR_END)
        self._sync_labels()
        self.stats={"visited":0,"path":0,"time":0.0,"algo":"-"}
        self._refresh_stats()

    # ───────────────────────────────────────────────────
    #  SOLVE DISPATCHER
    # ───────────────────────────────────────────────────
    def _start_solve(self):
        if self.solving: return
        if not self.start or not self.end:
            messagebox.showwarning("Missing","Set START and END first!"); return
        self._clear_path()
        self.solving=True
        self.solve_btn.configure(text="⏳ Solving...", state="disabled")
        algo = self.algo.get()
        fn = self._run_bfs if algo=="bfs" else self._run_dfs
        threading.Thread(target=fn, daemon=True).start()

    # ═══════════════════════════════════════════════════
    #  BFS  — Shortest SHORTEST PATH
    # ═══════════════════════════════════════════════════
    def _run_bfs(self):
        t0 = time.time()
        start, end = self.start, self.end
        visited = {start}
        parent  = {}
        queue   = deque([start])
        found   = False
        v_count = 0
        delay   = max(1, 100-self.speed.get()) / 1000.0
        dirs    = [(-1,0),(1,0),(0,-1),(0,1)]

        while queue:
            curr = queue.popleft()
            r,c  = curr
            if curr!=start and curr!=end:
                self._set_cell(r,c,CLR_VISITED)
            v_count+=1
            self.stats["visited"]=v_count
            self.stats["algo"]="BFS"
            self.root.after(0,self._refresh_stats)
            time.sleep(delay)

            if curr==end:
                found=True; break

            for dr,dc in dirs:
                nb=(r+dr,c+dc)
                nr,nc=nb
                if (0<=nr<ROWS and 0<=nc<COLS
                        and nb not in visited
                        and self.grid[nr,nc]==0):
                    visited.add(nb)
                    parent[nb]=curr
                    queue.append(nb)
                    if nb!=end:
                        self._set_cell(nr,nc,CLR_QUEUE)

        elapsed = time.time()-t0
        self._finish(found, parent, start, end, elapsed, "BFS", CLR_PATH)

    # ═══════════════════════════════════════════════════
    #  DFS  — Deep search
    # ═══════════════════════════════════════════════════
    def _run_dfs(self):
        t0 = time.time()
        start, end = self.start, self.end
        visited = {start}
        parent  = {}
        stack   = [start]
        found   = False
        v_count = 0
        delay   = max(1, 100-self.speed.get()) / 1000.0
        dirs    = [(-1,0),(1,0),(0,-1),(0,1)]

        while stack:
            curr = stack[-1]
            r,c  = curr
            if curr!=start and curr!=end:
                self._set_cell(r,c,CLR_VISITED)
            v_count+=1
            self.stats["visited"]=v_count
            self.stats["algo"]="DFS"
            self.root.after(0,self._refresh_stats)
            time.sleep(delay)

            if curr==end:
                found=True; break

            moved=False
            for dr,dc in dirs:
                nb=(r+dr,c+dc)
                nr,nc=nb
                if (0<=nr<ROWS and 0<=nc<COLS
                        and nb not in visited
                        and self.grid[nr,nc]==0):
                    visited.add(nb)
                    parent[nb]=curr
                    stack.append(nb)
                    if nb!=end:
                        self._set_cell(nr,nc,CLR_VISITED)
                    moved=True; break

            if not moved:
                popped=stack.pop()
                if popped!=start and popped!=end:
                    self._set_cell(*popped,CLR_VISITED)

        elapsed = time.time()-t0
        self._finish(found, parent, start, end, elapsed, "DFS", CLR_PATH)

    # ── Common finish ────────────────────────────────────
    
    def _finish(self, found, parent, start, end, elapsed, name, path_clr):
        if found:
            path=[]
            node=end
            while node in parent:
                path.append(node); node=parent[node]
            path.append(start); path.reverse()

            for i,(r,c) in enumerate(path):
                alt = "#B91C1C" # Slightly Lighter Dark Red
                clr = path_clr if i%2==0 else alt
                if (r,c) not in (start,end):
                    self._set_cell(r,c,clr)
                time.sleep(0.018)

            self.stats.update({"path":len(path),"time":elapsed})
            self.root.after(0,self._refresh_stats)
            self.root.after(0,lambda: messagebox.showinfo(
                f"{name} — Path Found!",
                f"Algorithm     : {name}\n"
                f"Cells visited  : {self.stats['visited']}\n"
                f"Path length    : {len(path)} steps\n"
                f"Time taken     : {elapsed:.3f}s\n\n"
                + ("✅ BFS guarantees the SHORTEST path!"
                   if name=="BFS" else
                   "⚠️ DFS path may NOT be shortest.\nUse BFS for shortest path.")))
        else:
            self.stats["time"]=elapsed
            self.root.after(0,self._refresh_stats)
            self.root.after(0,lambda: messagebox.showwarning(
                "No Path","No path found! Remove some walls."))

        self.solving=False
        self.root.after(0,lambda: self.solve_btn.configure(
            text="▶  SOLVE", state="normal"))

    # ═══════════════════════════════════════════════════
    #  REAL MAP ROUTING
    # ═══════════════════════════════════════════════════
    def _find_map_route(self):
        sc = self.start_city.get().strip()
        ec = self.end_city.get().strip()
        if not sc or not ec:
            messagebox.showwarning("Missing","Enter both city names!"); return

        self.map_btn.configure(text="⏳ Searching...", state="disabled")
        self.map_status.configure(text="Looking up cities...", fg=ACCENT)

        def run():
            # Geocode both cities
            self.root.after(0, lambda: self.map_status.configure(
                text=f"Finding: {sc}...", fg=ACCENT))
            sr = geocode_city(sc)
            if not sr:
                self.root.after(0, lambda: self._map_error(f"City not found: {sc}"))
                return

            self.root.after(0, lambda: self.map_status.configure(
                text=f"Finding: {ec}...", fg=ACCENT))
            er = geocode_city(ec)
            if not er:
                self.root.after(0, lambda: self._map_error(f"City not found: {ec}"))
                return

            slat,slon,sname = sr
            elat,elon,ename = er

            # Straight-line distance
            air_km = haversine_km(slat,slon,elat,elon)

            # Road route
            self.root.after(0, lambda: self.map_status.configure(
                text="Calculating road route...", fg=ACCENT))
            route = get_route((slat,slon),(elat,elon))

            self.root.after(0, lambda: self._map_done(
                sname, ename, air_km, route))

        threading.Thread(target=run, daemon=True).start()

    def _map_done(self, sname, ename, air_km, route):
        # Shorten long names
        def short(n):
            parts = n.split(",")
            return ", ".join(p.strip() for p in parts[:2])

        self.lbl_from.configure(text=short(sname))
        self.lbl_to.configure(  text=short(ename))
        self.lbl_air.configure( text=f"{air_km:,.1f} km" if air_km > 0 else "—")

        if route and isinstance(route, list) and len(route) > 0:
            primary = route[0]
            dist_km = primary.get('distance', 0)
            dur_min = primary.get('duration', 0)
            
            hrs  = int(dur_min//60)
            mins = int(dur_min%60)
            dur_str = f"{hrs}h {mins}m" if hrs else f"{mins} min"
            self.lbl_dist.configure(text=f"{dist_km:,.1f} km")
            self.lbl_dur.configure( text=dur_str)
            self.map_status.configure(
                text=f"✅ Found {len(route)} possible routes!",
                fg=ACCENT2)
        else:
            self.lbl_dist.configure(text="N/A (no road)")
            self.lbl_dur.configure( text="—")
            self.map_status.configure(
                text="Road route unavailable (ocean/no road).\nShowing straight-line only.",
                fg=ACCENT3)

        self.map_btn.configure(text="🗺  Find Route + Map", state="normal")
        if hasattr(self, 'map_btn2'):
            self.map_btn2.configure(state="normal")

    def _map_error(self, msg):
        self.map_status.configure(text=f"❌ {msg}", fg=ACCENT3)
        self.map_btn.configure(text="🗺  Find Route + Map", state="normal")
        if hasattr(self, 'map_btn2'):
            self.map_btn2.configure(state="normal")

    # ═══════════════════════════════════════════════════
    #  INTERACTIVE MAP WITH FOLIUM
    # ═══════════════════════════════════════════════════
    def _ensure_folium(self):
        """Ensure folium is installed, if not install it"""
        try:
            import folium
            return True
        except ImportError:
            self.map_status.configure(
                text="Installing folium... please wait",
                fg=ACCENT)
            self.root.update()
            try:
                subprocess.run(
                    [sys.executable, "-m", "pip", "install", "folium"],
                    capture_output=True, timeout=60)
                return True
            except Exception as e:
                messagebox.showerror(
                    "Installation Failed",
                    f"Could not install folium:\n{e}\n\n"
                    "Run in terminal:\npip install folium")
                return False

    def _open_map_directly(self, map_path):
        """Open map file in default browser using multiple methods"""
        try:
            # Method 1: Direct file URI with webbrowser
            file_uri = Path(map_path).as_uri()
            webbrowser.open(file_uri)
            return True
        except:
            pass
        
        try:
            # Method 2: Windows - use start command
            if os.name == 'nt':
                os.startfile(map_path)
                return True
        except:
            pass
        
        try:
            # Method 3: Use subprocess with start
            subprocess.Popen(['start', '', map_path], shell=True)
            return True
        except:
            pass
        
        try:
            # Method 4: Direct file path
            webbrowser.open(f'file:///{map_path}')
            return True
        except:
            pass
        
        return False

    def _open_interactive_map(self):
        """Open interactive map with start/end points and shortest route"""
        sc = self.start_city.get().strip()
        ec = self.end_city.get().strip()
        if not sc or not ec:
            messagebox.showwarning("Missing","Enter both city names!"); return

        if not self._ensure_folium():
            return

        self.map_btn.configure(state="disabled")
        self.map_btn2.configure(text="⏳ Creating Map...", state="disabled")
        self.map_status.configure(text="Building interactive map...", fg=ACCENT)

        def run():
            try:
                import folium
                import sys
            except ImportError:
                self.root.after(0, lambda: messagebox.showerror(
                    "Error", "Folium not installed"))
                self.root.after(0, lambda: (
                    self.map_btn.configure(state="normal"),
                    self.map_btn2.configure(text="🌍 Open Interactive Map", state="normal")
                ))
                return

            # Geocode both cities
            sr = geocode_city(sc)
            if not sr:
                self.root.after(0, lambda: self._map_error(f"City not found: {sc}"))
                return

            er = geocode_city(ec)
            if not er:
                self.root.after(0, lambda: self._map_error(f"City not found: {ec}"))
                return

            slat, slon, sname = sr
            elat, elon, ename = er

            # Calculate center point
            center_lat = (slat + elat) / 2
            center_lon = (slon + elon) / 2

            # Create map
            m = folium.Map(
                location=[center_lat, center_lon],
                zoom_start=6,
                tiles='OpenStreetMap'
            )

            # Add start marker (green)
            folium.Marker(
                location=[slat, slon],
                popup=f"<b>START: {sname}</b><br><i>Click for details</i>",
                tooltip=f"Start: {sname}",
                icon=folium.Icon(color='green', icon='play', prefix='fa')
            ).add_to(m)

            # Add end marker (red)
            folium.Marker(
                location=[elat, elon],
                popup=f"<b>END: {ename}</b><br><i>Click for details</i>",
                tooltip=f"End: {ename}",
                icon=folium.Icon(color='red', icon='stop', prefix='fa')
            ).add_to(m)

            # Get actual road route for visual display
            route_data = get_route((slat, slon), (elat, elon))

            if route_data and isinstance(route_data, list) and len(route_data) > 0:
                primary_route = route_data[0]
                dist_km = primary_route.get('distance', 0)
                dur_min = primary_route.get('duration', 0)
                hrs = int(dur_min // 60)
                mins = int(dur_min % 60)
                dur_str = f"{hrs}h {mins}m" if hrs else f"{mins} min"
                
                # Removed AntPath to ensure the winner isn't decided beforehand visually

                # 2. Create multiple PolyLines for animation
                all_line_ids = []
                all_coords_json = []
                
                # We'll use the real routes + maybe some simulated ones if needed
                for i, r in enumerate(route_data):
                    r_coords = r['coords']
                    line = folium.PolyLine(
                        locations=[r_coords[0]],
                        color='#FFA500', # Search Color (Orange)
                        weight=4, opacity=0.85,
                        popup=f'<b>Route Analysis {i+1}</b><br>Calculating...',
                    ).add_to(m)
                    all_line_ids.append(line.get_name())
                    all_coords_json.append(r_coords)
                
                # 3. Add Custom JS and CSS for Multi-Path Animation
                js_all_coords = json.dumps(all_coords_json)
                js_all_ids = json.dumps(all_line_ids)
                
                flourish_html = """
                <style>
                @keyframes status-pulse {
                    0% { opacity: 1; transform: scale(1); }
                    50% { opacity: 0.5; transform: scale(1.1); }
                    100% { opacity: 1; transform: scale(1); }
                }
                .ai-status-box {
                    position: absolute; top: 20px; right: 20px; padding: 15px 20px;
                    background: rgba(13, 17, 23, 0.95); color: #3FB950;
                    border: 2px solid #30363D; border-radius: 12px;
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    font-weight: bold; z-index: 9999; box-shadow: 0 8px 32px rgba(0,0,0,0.7);
                    backdrop-filter: blur(8px); min-width: 260px; transition: all 0.5s ease;
                }
                .pulse-dot {
                    display: inline-block; width: 12px; height: 12px;
                    background: #3FB950; border-radius: 50%; margin-right: 12px;
                    box-shadow: 0 0 10px #3FB950; animation: status-pulse 1s infinite;
                }
                </style>
                <div id="ai-status" class="ai-status-box">
                    <span class="pulse-dot"></span>
                    <span id="ai-text">INITIALIZING AI...</span>
                </div>
                """
                
                script = f"""
                <script>
                window.onload = function() {{
                    var allCoords = {js_all_coords};
                    var allLineIds = {js_all_ids};
                    var statusBox = document.getElementById('ai-status');
                    var statusText = document.getElementById('ai-text');
                    var map = window[allLineIds[0]]._map;
                    
                    // Phase 1: Neural Scan
                    function runSearchSimulation(callback) {{
                        statusText.innerHTML = 'SCANNING ALL PATHS...';
                        var searchLayer = L.layerGroup().addTo(map);
                        var startPoint = allCoords[0][0];
                        var endPoint = allCoords[0][allCoords[0].length-1];
                        
                        for(var s=0; s<45; s++) {{
                            var lat = startPoint[0] + (Math.random() - 0.5) * (endPoint[0] - startPoint[0]) * 1.6;
                            var lon = startPoint[1] + (Math.random() - 0.5) * (endPoint[1] - startPoint[1]) * 1.6;
                            L.circleMarker([lat, lon], {{radius: 2, color: '#3FB950', opacity: 0.6}}).addTo(searchLayer);
                        }}
                        setTimeout(function() {{ searchLayer.clearLayers(); callback(); }}, 800);
                    }}

                    // Phase 2: Live Multi-Drawing
                    function drawAllPaths() {{
                        var finishedCount = 0;
                        var totalPaths = allCoords.length;
                        
                        allCoords.forEach(function(coords, index) {{
                            var line = window[allLineIds[index]];
                            var i = 1;
                            var speed = Math.max(3, 800 / coords.length); // Super fast
                            
                            function step() {{
                                if (i < coords.length) {{
                                    line.addLatLng(coords[i]);
                                    i++;
                                    setTimeout(step, speed);
                                }} else {{
                                    finishedCount++;
                                    checkFinished();
                                }}
                            }}
                            step();
                        }});
                        
                        function checkFinished() {{
                            var progress = Math.round((finishedCount / totalPaths) * 100);
                            statusText.innerHTML = 'AI SEARCHING: ' + progress + '%';
                            
                            if (finishedCount === totalPaths) {{
                                statusText.innerHTML = 'OPTIMAL PATH IDENTIFIED';
                                allLineIds.forEach(function(id, index) {{
                                    var line = window[id];
                                    if (index === 0) {{
                                        line.setStyle({{color: '#FF0000', weight: 7, opacity: 1}}); // BEST -> RED
                                        line.bringToFront();
                                    }} else {{
                                        line.setStyle({{color: '#0000FF', weight: 3, opacity: 0.5}}); // ALT -> BLUE
                                    }}
                                }});
                                
                                statusBox.style.borderColor = '#FF0000';
                                statusText.style.color = '#FF0000';
                                document.querySelector('.pulse-dot').style.background = '#FF0000';
                                
                                setTimeout(function() {{ 
                                    statusBox.style.opacity = '0';
                                    statusBox.style.transform = 'translateY(-20px)';
                                }}, 6000);
                            }}
                        }}
                    }}
                    
                    setTimeout(function() {{
                        runSearchSimulation(function() {{
                            drawAllPaths();
                        }});
                    }}, 1000);
                }};
                </script>
                """
                m.get_root().html.add_child(folium.Element(flourish_html))
                m.get_root().html.add_child(folium.Element(script))
                
                # Add markers for start and end
                folium.CircleMarker(location=primary_route['coords'][0], radius=8, color='green', fill=True).add_to(m)
                folium.CircleMarker(location=primary_route['coords'][-1], radius=8, color='red', fill=True).add_to(m)
            else:
                # Fallback: Straight line
                folium.PolyLine(locations=[[slat, slon], [elat, elon]], color='blue', weight=3).add_to(m)

            # Save map in the same directory as the script for better reliability
            script_dir = Path(__file__).parent
            map_path = str(script_dir / "route_map.html")
            m.save(map_path)

            self.root.after(0, lambda: self.map_status.configure(
                text=f"✅ Map created!\nOpening in browser...",
                fg=ACCENT2))
            
            # Try to open in browser
            success = self._open_map_directly(map_path)
            
            if success:
                self.root.after(0, lambda: self.map_status.configure(
                    text=f"✅ Map opened in browser!\n📁 Saved: {map_path}",
                    fg=ACCENT2))
            else:
                self.root.after(0, lambda: messagebox.showinfo(
                    "Map Created ✅",
                    f"Interactive map created successfully!\n\n"
                    f"📁 Location: {map_path}\n\n"
                    f"Please open this file in your browser.\n"
                    f"The file is saved on your Desktop as 'route_map.html'"))
                self.root.after(0, lambda: self.map_status.configure(
                    text=f"✅ Map created at:\n{map_path}",
                    fg=ACCENT2))

            self.map_btn.configure(state="normal")
            self.map_btn2.configure(text="🌍 Open Interactive Map", state="normal")

        threading.Thread(target=run, daemon=True).start()


# ═══════════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    root = tk.Tk()
    app  = MazeSolverPro(root)

    root.update_idletasks()
    sw,sh = root.winfo_screenwidth(), root.winfo_screenheight()
    ww,wh = root.winfo_width(),       root.winfo_height()
    root.geometry(f"+{(sw-ww)//2}+{(sh-wh)//2}")

    root.mainloop()