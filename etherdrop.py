from __future__ import annotations

import ipaddress
import hashlib
import ctypes
import json
import os
import platform
import queue
import select
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zlib
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path, PurePosixPath
import tkinter as tk
from tkinter import filedialog, ttk

APP_NAME = "EtherDrop"
APP_VERSION = "2.0.0"
GITHUB_REPOSITORY = "JaafarTanoukhi/EtherDrop"
RELEASE_ASSET = "EtherDrop.exe"
PROTOCOL_VERSION = 3
MAGIC = "ETHERDROP_V3"
DISCOVERY_PORT = 45670
TRANSFER_PORT = 45671
DISCOVERY_GROUP = "ff02::1"
ANNOUNCE_INTERVAL = 1.0
PEER_TIMEOUT = 4.0

BLOCK_SIZE = 8 * 1024 * 1024
SOCKET_BUFFER = 4 * 1024 * 1024
MAX_CONTROL_FRAME = 1024 * 1024
TRANSFER_TIMEOUT = 15.0
RECONNECT_DELAY = 1.0
TRANSFER_HEARTBEAT_INTERVAL = 2.0

SESSION_ID = uuid.uuid4().hex

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

COLOR_BG = "#F3F4F5"
COLOR_SURFACE = "#FFFFFF"
COLOR_SURFACE_ALT = "#E7E9EC"
COLOR_PANEL = "#F8F9FA"
COLOR_BORDER = "#DCDFE3"
COLOR_TEXT = "#22252B"
COLOR_MUTED = "#686C76"
COLOR_ACCENT = "#55616E"
COLOR_ACCENT_HOVER = "#414C58"
COLOR_CYAN = "#55616E"
COLOR_CYAN_HOVER = "#414C58"
COLOR_SUCCESS = "#237D52"
COLOR_WARNING = "#986416"
COLOR_DANGER = "#BC3E49"
COLOR_DANGER_HOVER = "#A7313C"

THEMES = {
    "ethernet": {name: value for name, value in globals().copy().items() if name.startswith("COLOR_")},
    "wifi": {
        "COLOR_BG": "#F1F5FA", "COLOR_SURFACE": "#FFFFFF", "COLOR_SURFACE_ALT": "#E6EDF7",
        "COLOR_PANEL": "#F7F9FD", "COLOR_BORDER": "#D8E1EE", "COLOR_TEXT": COLOR_TEXT,
        "COLOR_MUTED": COLOR_MUTED, "COLOR_ACCENT": "#266CD3", "COLOR_ACCENT_HOVER": "#1D56AF",
        "COLOR_CYAN": "#266CD3", "COLOR_CYAN_HOVER": "#1D56AF",
        "COLOR_SUCCESS": COLOR_SUCCESS, "COLOR_WARNING": COLOR_WARNING,
        "COLOR_DANGER": COLOR_DANGER, "COLOR_DANGER_HOVER": COLOR_DANGER_HOVER,
    },
}
THEMES["neutral"] = {**THEMES["ethernet"], "COLOR_BG": "#F4F4F5",
    "COLOR_SURFACE_ALT": "#E8E8EB", "COLOR_PANEL": "#F8F8F9", "COLOR_BORDER": "#DEDEE2",
    "COLOR_ACCENT": "#50545E", "COLOR_ACCENT_HOVER": "#383C45",
    "COLOR_CYAN": "#50545E", "COLOR_CYAN_HOVER": "#383C45"}


def apply_mode_theme(root: tk.Misc, mode: str) -> None:
    globals().update(THEMES[mode])
    configure_modern_theme(root)


def icon_image(parent, name, tone="ink", size=24):
    root = parent.winfo_toplevel()
    pixels = min((24, 30, 36, 42, 48, 60, 72, 84, 96),
                 key=lambda value: abs(value - size * root.ui_scale))
    key = (name, tone, pixels)
    if not hasattr(root, "icon_images"):
        root.icon_images = {}
    if key not in root.icon_images:
        path = Path(__file__).resolve().parent / "assets" / "icons" / f"{name}-{tone}-{pixels}.png"
        root.icon_images[key] = tk.PhotoImage(master=root, data=path.read_bytes())
    return root.icon_images[key]


def mode_badge(parent, mode: str, background: str = None):
    background = background or COLOR_BG
    box = tk.Frame(parent, bg=background)
    tk.Label(box, image=icon_image(parent, "wifi" if mode == "wifi" else "ethernet-port", mode),
             bg=background).pack(side="left", padx=(0, 8))
    tk.Label(box, text="Wi-Fi" if mode == "wifi" else "Ethernet", bg=background,
             fg=COLOR_ACCENT, font=("Segoe UI", 10)).pack(side="left")
    return box


def view_snapshot(parent):
    """Copy only our own view into memory for a transition; never capture the desktop."""
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    pointer = ctypes.c_void_p
    user32.GetWindowDC.argtypes, user32.GetWindowDC.restype = [pointer], pointer
    user32.GetAncestor.argtypes, user32.GetAncestor.restype = [pointer, ctypes.c_uint], pointer
    user32.GetForegroundWindow.restype = pointer
    user32.ReleaseDC.argtypes = [pointer, pointer]
    gdi32.BitBlt.argtypes = [pointer, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                            pointer, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
    gdi32.CreateCompatibleDC.argtypes, gdi32.CreateCompatibleDC.restype = [pointer], pointer
    gdi32.CreateDIBSection.argtypes = [pointer, pointer, ctypes.c_uint, pointer, pointer, ctypes.c_uint]
    gdi32.CreateDIBSection.restype = pointer
    gdi32.SelectObject.argtypes, gdi32.SelectObject.restype = [pointer, pointer], pointer
    gdi32.DeleteObject.argtypes = [pointer]
    gdi32.DeleteDC.argtypes = [pointer]
    width, height = parent.winfo_width(), parent.winfo_height()
    header = struct.pack("<IiiHHIIiiII", 40, width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
    info = ctypes.create_string_buffer(header)
    pixels = pointer()
    handle = parent.winfo_id()
    if user32.GetAncestor(handle, 2) != user32.GetForegroundWindow():
        return None
    dc = user32.GetWindowDC(handle)
    memory = gdi32.CreateCompatibleDC(dc)
    bitmap = gdi32.CreateDIBSection(dc, info, 0, ctypes.byref(pixels), None, 0)
    old_bitmap = gdi32.SelectObject(memory, bitmap)
    try:
        if not gdi32.BitBlt(memory, 0, 0, width, height, dc, 0, 0, 0x00CC0020):
            return None
        rgba = ctypes.string_at(pixels, width * height * 4)
        rgb = bytearray(width * height * 3)
        rgb[0::3], rgb[1::3], rgb[2::3] = rgba[2::4], rgba[1::4], rgba[0::4]
        return tk.PhotoImage(master=parent.winfo_toplevel(),
                            data=f"P6\n{width} {height}\n255\n".encode() + rgb, format="PPM")
    finally:
        gdi32.SelectObject(memory, old_bitmap)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory)
        user32.ReleaseDC(handle, dc)


def finish_motion(parent):
    root = parent._root()
    if getattr(root, "motion_parent", None) is not parent:
        return
    if root.motion_callback:
        root.after_cancel(root.motion_callback)
    root.motion_callback = None
    root.motion_parent = None
    root.motion_prepared = False
    root.motion_overlay.attributes("-alpha", 0)
    root.motion_overlay.withdraw()
    root.motion_label.configure(image="")
    root.motion_image = None


def present_motion(overlay):
    user32, dwmapi = ctypes.windll.user32, ctypes.windll.dwmapi
    pointer = ctypes.c_void_p
    user32.GetAncestor.argtypes, user32.GetAncestor.restype = [pointer, ctypes.c_uint], pointer
    dwmapi.DwmSetWindowAttribute.argtypes = [pointer, ctypes.c_uint, pointer, ctypes.c_uint]
    handle = user32.GetAncestor(overlay.winfo_id(), 2)
    disabled = ctypes.c_int(1)
    # Our fade controls visibility; Windows must not animate the cover appearing.
    dwmapi.DwmSetWindowAttribute(handle, 3, ctypes.byref(disabled), ctypes.sizeof(disabled))
    overlay.attributes("-alpha", 1)
    overlay.update_idletasks()
    ctypes.windll.gdi32.GdiFlush()
    # Present the old view before any page or palette changes can become visible.
    dwmapi.DwmFlush()


def begin_motion(parent):
    root = parent.winfo_toplevel()
    if getattr(root, "motion_prepared", False):
        return
    active_parent = getattr(root, "motion_parent", None)
    if active_parent is not None:
        finish_motion(active_parent)
    if platform.system() != "Windows" or not parent.winfo_ismapped():
        return
    parent.update_idletasks()
    snapshot = view_snapshot(parent)
    if snapshot is None:
        return
    if not hasattr(root, "motion_overlay"):
        root.motion_overlay = tk.Toplevel(root)
        root.motion_overlay.withdraw()
        root.motion_overlay.overrideredirect(True)
        root.motion_overlay.transient(root)
        # Create a layered window before its first visible frame, avoiding a style-change flash.
        root.motion_overlay.attributes("-toolwindow", True, "-disabled", True, "-alpha", 0)
        root.motion_label = tk.Label(root.motion_overlay, borderwidth=0, highlightthickness=0)
        root.motion_label.pack(fill="both", expand=True)
    root.motion_parent = parent
    root.motion_prepared = True
    root.motion_callback = None
    root.motion_image = snapshot
    root.motion_label.configure(image=snapshot)
    root.motion_bounds = (parent.winfo_width(), parent.winfo_height(), parent.winfo_rootx(), parent.winfo_rooty())
    width, height, x, y = root.motion_bounds
    root.motion_overlay.geometry(f"{width}x{height}+{x}+{y}")
    root.motion_overlay.deiconify()
    root.motion_overlay.lift(root)
    # Process mapping and paint events while transparent; idle work alone leaves
    # the previous transition's pixels in the reused window.
    root.motion_overlay.update()
    present_motion(root.motion_overlay)


def show_view(frame, previous=None, animate=True):
    parent, root = frame.master, frame.winfo_toplevel()
    if animate:
        begin_motion(parent)
    if previous is not None:
        previous.pack_forget()
    frame.pack(fill="both", expand=True)
    if not animate or getattr(root, "motion_parent", None) is not parent:
        return
    if root.motion_callback:
        root.after_cancel(root.motion_callback)

    def start():
        root.motion_prepared = False
        root.update_idletasks()
        started = time.monotonic()

        def step():
            if not parent.winfo_exists():
                finish_motion(parent)
                return
            bounds = (parent.winfo_width(), parent.winfo_height(), parent.winfo_rootx(), parent.winfo_rooty())
            if not parent.winfo_ismapped() or bounds != root.motion_bounds:
                finish_motion(parent)
                return
            progress = min((time.monotonic() - started) / .22, 1)
            root.motion_overlay.attributes("-alpha", 1 - progress*progress*(3-2*progress))
            if progress < 1:
                root.motion_callback = root.after(16, step)
            else:
                finish_motion(parent)
        step()
    root.motion_callback = root.after_idle(start)


class RoundedCard(tk.Canvas):
    def __init__(self, parent, padding=20, height=160):
        scale = parent.winfo_toplevel().ui_scale
        super().__init__(parent, bg=COLOR_BG, highlightthickness=0, borderwidth=0, height=round(height * scale))
        self.padding = round(padding * scale)
        self.body = ttk.Frame(self, style="Card.TFrame")
        self.shape = self.create_polygon(0, 0, 0, 0, smooth=True, fill=COLOR_SURFACE, outline="")
        self.body_window = self.create_window(self.padding, self.padding, window=self.body, anchor="nw")
        self.bind("<Configure>", self._resize)

    def _resize(self, event):
        width, height, radius = event.width, event.height, round(18 * self.winfo_toplevel().ui_scale)
        self.coords(self.shape, radius, 0, width-radius, 0, width, 0, width, radius,
                    width, height-radius, width, height, width-radius, height,
                    radius, height, 0, height, 0, height-radius, 0, radius, 0, 0)
        self.itemconfigure(self.body_window, width=max(width-2*self.padding, 1),
                           height=max(height-2*self.padding, 1))


@lru_cache(maxsize=128)
def rounded_button_data(color, background, focus_color=None):
    size, radius = 32, 10
    red, green, blue = (int(color[index:index+2], 16) for index in (1, 3, 5))
    backdrop = tuple(int(background[index:index+2], 16) for index in (1, 3, 5))
    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            dx = max(radius - x - .5, x + .5 - (size - radius), 0)
            dy = max(radius - y - .5, y + .5 - (size - radius), 0)
            alpha = round(max(0, min(1, radius + .5 - (dx*dx + dy*dy)**.5)) * 255)
            distance = min(x + .5, y + .5, size - x - .5, size - y - .5)
            if dx and dy:
                distance = radius - (dx*dx + dy*dy)**.5
            if focus_color and distance < 2:
                rgb = tuple(int(focus_color[index:index+2], 16) for index in (1, 3, 5))
            else:
                rgb = (red, green, blue)
            rgb = tuple(round(channel * alpha / 255 + behind * (255-alpha) / 255)
                        for channel, behind in zip(rgb, backdrop))
            rows.extend((*rgb, 255))
    def chunk(kind, data):
        return struct.pack("!I", len(data)) + kind + data + struct.pack("!I", zlib.crc32(kind + data))
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack("!2I5B", size, size, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")
    return png


def rounded_button_image(root, color, background, focused=False):
    key = (color, background, COLOR_ACCENT if focused else None)
    if not hasattr(root, "button_image_cache"):
        root.button_image_cache = {}
    if key not in root.button_image_cache:
        root.button_image_cache[key] = tk.PhotoImage(master=root, data=rounded_button_data(*key))
    return root.button_image_cache[key]


def accent_tint(opacity):
    return "#" + "".join(f"{round(int(COLOR_ACCENT[i:i+2], 16)*opacity + int(COLOR_BG[i:i+2], 16)*(1-opacity)):02X}"
                         for i in (1, 3, 5))

DPI_AWARENESS_MODE = "Unknown"


def enable_high_dpi_awareness() -> str:
    global DPI_AWARENESS_MODE
    if platform.system() != "Windows":
        DPI_AWARENESS_MODE = "Unavailable"
        return DPI_AWARENESS_MODE

    user32 = ctypes.windll.user32
    try:
        setter = user32.SetProcessDpiAwarenessContext
        setter.argtypes = [ctypes.c_void_p]
        setter.restype = ctypes.c_bool
        if setter(ctypes.c_void_p(-4)):
            DPI_AWARENESS_MODE = "Per-Monitor V2"
            return DPI_AWARENESS_MODE
    except (AttributeError, OSError):
        pass

    try:
        if ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0:
            DPI_AWARENESS_MODE = "Per-Monitor"
            return DPI_AWARENESS_MODE
    except (AttributeError, OSError):
        pass

    try:
        if user32.SetProcessDPIAware():
            DPI_AWARENESS_MODE = "System-aware"
            return DPI_AWARENESS_MODE
    except (AttributeError, OSError):
        pass

    try:
        context = user32.GetThreadDpiAwarenessContext()
        awareness = user32.GetAwarenessFromDpiAwarenessContext(context)
        DPI_AWARENESS_MODE = {0: "Unaware", 1: "System-aware", 2: "Per-Monitor"}.get(awareness, "Unknown")
    except (AttributeError, OSError):
        DPI_AWARENESS_MODE = "Unknown"
    return DPI_AWARENESS_MODE


def configure_tk_dpi(window: tk.Misc) -> tuple[int, float]:
    dpi = 96
    if platform.system() == "Windows":
        try:
            dpi = int(ctypes.windll.user32.GetDpiForWindow(window.winfo_id())) or 96
        except (AttributeError, OSError, tk.TclError):
            dpi = 96
    window.tk.call("tk", "scaling", dpi / 72.0)
    return dpi, dpi / 96.0


def set_scaled_window_geometry(
    window: tk.Misc,
    width: int,
    height: int,
    min_width: int,
    min_height: int,
    scale: float,
) -> None:
    screen_width = window.winfo_screenwidth()
    screen_height = window.winfo_screenheight()
    available_width = max(screen_width - 80, 640)
    available_height = max(screen_height - 100, 500)
    actual_width = min(round(width * scale), available_width)
    actual_height = min(round(height * scale), available_height)
    actual_min_width = min(round(min_width * scale), available_width)
    actual_min_height = min(round(min_height * scale), available_height)
    x = max(0, min(window.winfo_x(), screen_width - actual_width - 20))
    y = max(0, min(window.winfo_y(), screen_height - actual_height - 70))
    window.geometry(f"{actual_width}x{actual_height}+{x}+{y}")
    window.minsize(actual_min_width, actual_min_height)


enable_high_dpi_awareness()


def configure_modern_theme(root: tk.Misc) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(background=COLOR_BG)
    style.configure(".", font=("Segoe UI", 11), background=COLOR_BG, foreground=COLOR_TEXT)
    for name, color in (("App", COLOR_BG), ("Card", COLOR_SURFACE), ("Panel", COLOR_PANEL)):
        style.configure(f"{name}.TFrame", background=color)
    style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT)
    for name, size, weight, background, foreground in (
        ("Hero", 30, "bold", COLOR_BG, COLOR_TEXT),
        ("Title", 24, "bold", COLOR_BG, COLOR_TEXT),
        ("Subtitle", 11, "normal", COLOR_BG, COLOR_MUTED),
        ("Small", 9, "normal", COLOR_BG, COLOR_MUTED),
        ("Card", 11, "normal", COLOR_SURFACE, COLOR_TEXT),
        ("CardTitle", 14, "bold", COLOR_SURFACE, COLOR_TEXT),
        ("CardMuted", 10, "normal", COLOR_SURFACE, COLOR_MUTED),
        ("MetricLabel", 10, "normal", COLOR_SURFACE, COLOR_MUTED),
        ("MetricValue", 14, "normal", COLOR_SURFACE, COLOR_TEXT),
        ("AccentText", 11, "normal", COLOR_BG, COLOR_ACCENT),
        ("Sync", 10, "normal", COLOR_SURFACE, COLOR_SUCCESS),
        ("Waiting", 10, "normal", COLOR_SURFACE, COLOR_MUTED),
        ("Lost", 10, "normal", COLOR_SURFACE, COLOR_DANGER),
        ("Phase", 11, "normal", COLOR_BG, COLOR_ACCENT),
        ("SuccessPhase", 11, "normal", COLOR_BG, COLOR_SUCCESS),
        ("WarningPhase", 11, "normal", COLOR_BG, COLOR_WARNING),
        ("DangerPhase", 11, "normal", COLOR_BG, COLOR_DANGER),
    ):
        style.configure(f"{name}.TLabel", font=("Segoe UI", size, weight), background=background, foreground=foreground)

    style.configure("TButton", background=COLOR_SURFACE_ALT, foreground=COLOR_TEXT,
                    padding=(16, 11), borderwidth=0, focusthickness=1, focuscolor=COLOR_ACCENT,
                    font=("Segoe UI", 11))
    style.map("TButton", background=[("pressed", COLOR_BORDER), ("active", COLOR_BORDER)],
              foreground=[("disabled", COLOR_MUTED)])
    for name in ("Accent", "Cyan"):
        style.configure(f"{name}.TButton", background=COLOR_ACCENT, foreground="#FFFFFF")
        style.map(f"{name}.TButton", background=[("disabled", COLOR_SURFACE_ALT),
                  ("pressed", COLOR_ACCENT_HOVER), ("active", COLOR_ACCENT_HOVER)],
                  foreground=[("disabled", COLOR_MUTED)])
    style.configure("Danger.TButton", background=COLOR_SURFACE_ALT, foreground=COLOR_DANGER)
    style.map("Danger.TButton", background=[("active", COLOR_BORDER)])
    style.configure("Ghost.TButton", background=COLOR_BG, foreground=COLOR_MUTED, padding=(10, 9))
    style.map("Ghost.TButton", background=[("active", COLOR_SURFACE_ALT)])
    style.configure("Link.TButton", background=COLOR_SURFACE, foreground=COLOR_ACCENT, padding=(10, 9))
    style.map("Link.TButton", background=[("active", COLOR_PANEL)])
    style.configure("Segment.TButton", background=COLOR_SURFACE_ALT, padding=(24, 10))
    style.configure("SelectedSegment.TButton", foreground=COLOR_TEXT, padding=(24, 10))
    style.configure("Role.TButton", font=("Segoe UI", 12), anchor="w", justify="left", padding=(24, 22))
    style.configure("Card.TCheckbutton", background=COLOR_SURFACE, foreground=COLOR_TEXT, padding=5)
    style.map("Card.TCheckbutton", background=[("active", COLOR_SURFACE)],
              indicatorcolor=[("selected", COLOR_ACCENT), ("!selected", COLOR_SURFACE_ALT)])
    style.configure("Modern.Horizontal.TProgressbar", background=COLOR_ACCENT, troughcolor=COLOR_SURFACE_ALT,
                    borderwidth=0, bordercolor=COLOR_SURFACE_ALT, lightcolor=COLOR_ACCENT, darkcolor=COLOR_ACCENT,
                    thickness=6)
    style.configure("TNotebook", background=COLOR_BG, borderwidth=0, tabmargins=0)
    style.configure("TNotebook.Tab", background=COLOR_BG, foreground=COLOR_MUTED, padding=(18, 10), borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", COLOR_SURFACE)], foreground=[("selected", COLOR_TEXT)])
    style.configure("Treeview", background=COLOR_SURFACE, fieldbackground=COLOR_SURFACE,
                    foreground=COLOR_TEXT, borderwidth=0, bordercolor=COLOR_SURFACE, rowheight=34, relief="flat")
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nsew"})])
    style.map("Treeview", background=[("selected", COLOR_SURFACE_ALT)], foreground=[("selected", COLOR_TEXT)])
    style.configure("Treeview.Heading", background=COLOR_PANEL, foreground=COLOR_MUTED, borderwidth=0,
                    bordercolor=COLOR_PANEL, lightcolor=COLOR_PANEL, darkcolor=COLOR_PANEL,
                    relief="flat", padding=(8, 9), font=("Segoe UI", 10))
    style.configure("TSeparator", background=COLOR_BORDER)
    style.configure("Vertical.TScrollbar", background=COLOR_BORDER, troughcolor=COLOR_SURFACE,
                    borderwidth=0, bordercolor=COLOR_SURFACE, lightcolor=COLOR_BORDER, darkcolor=COLOR_BORDER,
                    width=8, arrowsize=8)
    style.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"sticky": "nsew", "expand": True})]})])
    style.configure("TScrollbar", background=COLOR_BORDER, troughcolor=COLOR_SURFACE, borderwidth=0,
                    arrowcolor=COLOR_MUTED, arrowsize=8)
    if not hasattr(root, "button_images"):
        root.button_images = {}
    hover = accent_tint(.14)
    for name, normal, active in (("TButton", COLOR_SURFACE_ALT, hover),
        ("Card.TButton", COLOR_SURFACE_ALT, hover),
        ("Accent.TButton", COLOR_ACCENT, COLOR_ACCENT_HOVER),
        ("Cyan.TButton", COLOR_ACCENT, COLOR_ACCENT_HOVER),
        ("Danger.TButton", COLOR_SURFACE_ALT, hover),
        ("Ghost.TButton", COLOR_BG, hover),
        ("Link.TButton", COLOR_SURFACE, hover),
        ("Role.TButton", COLOR_SURFACE, hover),
        ("Segment.TButton", COLOR_SURFACE, hover),
        ("SelectedSegment.TButton", accent_tint(.32), accent_tint(.4))):
        background = COLOR_SURFACE if name in ("Link.TButton", "Card.TButton") else COLOR_BG
        generated = [rounded_button_image(root, color, background) for color in (normal, active, COLOR_SURFACE_ALT)]
        generated.append(rounded_button_image(root, normal, background, focused=True))
        if name in root.button_images:
            images = root.button_images[name]
            for destination, new in zip(images, generated):
                destination.tk.call(str(destination), "copy", str(new))
        else:
            images = [new.copy() for new in generated]
            root.button_images[name] = images
        element = "Rounded" + name
        if element not in style.element_names():
            style.element_create(element, "image", str(images[0]), ("disabled", str(images[2])),
                                 ("pressed", str(images[1])), ("active", str(images[1])),
                                 ("focus", str(images[3])), border=10, sticky="nsew")
        style.configure(name, background=background)
        style.map(name, background=[])
        if name not in ("Accent.TButton", "Cyan.TButton"):
            style.map(name, foreground=[("disabled", COLOR_MUTED),
                      ("active", COLOR_DANGER if name == "Danger.TButton" else COLOR_TEXT)])
        style.layout(name, [(element, {"sticky": "nsew", "children": [
            ("Button.padding", {"sticky": "nsew", "children": [("Button.label", {"sticky": "nsew"})]})]})])
    style.configure("Selected.Ghost.TButton", foreground=COLOR_ACCENT)

@dataclass(frozen=True)
class EthernetAdapter:
    name: str
    if_index: int
    link_local: str
    mac: str
    link_speed: str
    rx_bps: int
    tx_bps: int
    has_gateway: bool


@dataclass(frozen=True)
class WifiAdapter:
    name: str
    if_index: int
    address: str
    prefix_length: int
    mac: str = ""
    link_speed: str = ""
    rx_bps: int = 0
    tx_bps: int = 0
    has_gateway: bool = True

    @property
    def network(self):
        return ipaddress.IPv4Network(f"{self.address}/{self.prefix_length}", strict=False)


def discover_wifi_adapters() -> list[WifiAdapter]:
    script = r'''
$ErrorActionPreference = 'Stop'
$items = @()
Get-NetAdapter -Physical | Where-Object {
    $_.Status -eq 'Up' -and $_.NdisPhysicalMedium -in @(1, 9)
} | ForEach-Object {
    $a = $_
    $ip = Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object { $_.AddressState -eq 'Preferred' } | Select-Object -First 1
    if ($ip) {
        $items += [PSCustomObject]@{
            Name = [string]$a.Name; IfIndex = [int]$a.ifIndex
            Address = [string]$ip.IPAddress; PrefixLength = [int]$ip.PrefixLength
            Mac = [string]$a.MacAddress; LinkSpeed = [string]$a.LinkSpeed
            RxBps = [int64]$a.ReceiveLinkSpeed; TxBps = [int64]$a.TransmitLinkSpeed
        }
    }
}
$items | ConvertTo-Json -Compress
'''
    raw = run_powershell(script)
    if not raw:
        return []
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]
    return [WifiAdapter(str(x["Name"]), int(x["IfIndex"]), str(x["Address"]), int(x["PrefixLength"]),
                        str(x.get("Mac", "")), str(x.get("LinkSpeed", "")),
                        int(x.get("RxBps") or 0), int(x.get("TxBps") or 0)) for x in data]


def adapter_endpoint(adapter, port: int, peer_ip: str | None = None):
    if isinstance(adapter, WifiAdapter):
        return (peer_ip or adapter.address, port)
    return ipv6_scope_tuple(peer_ip or adapter.link_local, port, adapter.if_index)


def adapter_family(adapter):
    return socket.AF_INET if isinstance(adapter, WifiAdapter) else socket.AF_INET6


@dataclass(frozen=True)
class TransferItem:
    source: Path
    relative: str
    size: int
    modified_ns: int


@dataclass
class IncomingTransferDecision:
    ready: threading.Event = field(default_factory=threading.Event)
    destination: Path | None = None
    owner: int = 0
    reason: str = "Transfer declined by the receiver."

    def accept(self, destination: Path, owner: int = 0) -> None:
        if self.ready.is_set():
            return
        self.destination = destination
        self.owner = owner
        self.ready.set()

    def reject(self, reason: str = "Transfer declined by the receiver.") -> None:
        if self.ready.is_set():
            return
        self.reason = reason
        self.ready.set()


class TransferCancelled(RuntimeError):
    pass


class TransferRejected(RuntimeError):
    pass


class TransferInterrupted(ConnectionError):
    pass


def run_powershell(script: str) -> str:
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True,
        text=True,
        creationflags=creationflags,
        timeout=12,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "PowerShell command failed.")
    return result.stdout.strip()


def discover_ethernet_adapters(require_link_local: bool = True) -> list[EthernetAdapter]:
    # Only UP, physical IEEE 802.3 Ethernet adapters are returned.
    # Wi-Fi is explicitly excluded by MediaType.
    if platform.system() != "Windows":
        raise RuntimeError("EtherDrop is currently Windows-only.")

    script = r'''
$ErrorActionPreference = 'Stop'
$items = @()
$adapters = Get-NetAdapter -Physical | Where-Object {
    $_.Status -eq 'Up' -and $_.MediaType -eq '802.3'
}
foreach ($a in $adapters) {
    $ll = Get-NetIPAddress -InterfaceIndex $a.ifIndex -AddressFamily IPv6 -ErrorAction SilentlyContinue |
        Where-Object { $_.IPAddress -like 'fe80::*' } |
        Select-Object -First 1 -ExpandProperty IPAddress

    $cfg = Get-NetIPConfiguration -InterfaceIndex $a.ifIndex -ErrorAction SilentlyContinue
    $hasGateway = $false
    if ($cfg) {
        if ($cfg.IPv4DefaultGateway -or $cfg.IPv6DefaultGateway) {
            $hasGateway = $true
        }
    }

    $items += [PSCustomObject]@{
        Name = [string]$a.Name
        IfIndex = [int]$a.ifIndex
        LinkLocal = [string]$ll
        Mac = [string]$a.MacAddress
        LinkSpeed = [string]$a.LinkSpeed
        RxBps = [int64]$a.ReceiveLinkSpeed
        TxBps = [int64]$a.TransmitLinkSpeed
        HasGateway = [bool]$hasGateway
    }
}
$items | ConvertTo-Json -Compress
'''
    raw = run_powershell(script)
    if not raw:
        return []

    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]

    adapters = []
    for x in data:
        link_local = str(x.get("LinkLocal") or "").split("%")[0]
        if require_link_local and not link_local:
            continue
        adapters.append(
            EthernetAdapter(
                name=str(x["Name"]),
                if_index=int(x["IfIndex"]),
                link_local=link_local,
                mac=str(x.get("Mac", "")),
                link_speed=str(x.get("LinkSpeed", "")),
                rx_bps=int(x.get("RxBps") or 0),
                tx_bps=int(x.get("TxBps") or 0),
                has_gateway=bool(x.get("HasGateway")),
            )
        )
    return adapters


ETHERNET_SETUP_SCRIPT = r'''
param(
    [Parameter(Mandatory = $true)][string]$ProgramPath,
    [Parameter(Mandatory = $true)][int]$DiscoveryPort,
    [Parameter(Mandatory = $true)][int]$TransferPort,
    [Parameter(Mandatory = $true)][string]$ResultPath
)

$ErrorActionPreference = 'Stop'
$actions = @()
$warnings = @()
$result = $null
$exitCode = 0

try {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Administrator permission is required to configure Ethernet. Approve the Windows prompt and try again.'
    }

    $activeAdapters = @(Get-NetAdapter -Physical -ErrorAction Stop | Where-Object {
        $_.Status -eq 'Up' -and [string]$_.MediaType -eq '802.3'
    })
    $directAdapters = @($activeAdapters | Where-Object {
        $configuration = Get-NetIPConfiguration -InterfaceIndex $_.ifIndex -ErrorAction SilentlyContinue
        -not $configuration -or (-not $configuration.IPv4DefaultGateway -and -not $configuration.IPv6DefaultGateway)
    })
    if (-not $directAdapters) {
        if ($activeAdapters) {
            throw 'EtherDrop found active physical Ethernet, but it has a default gateway. For safety, automatic setup only works on an isolated direct cable and will not modify routed Ethernet.'
        }
        throw 'No active physical Ethernet cable was detected. Connect this laptop directly to the other laptop, make sure the Ethernet adapter is enabled, then try again.'
    }

    $adapter = $directAdapters | Sort-Object -Property @{
        Expression = { [Math]::Min([int64]$_.ReceiveLinkSpeed, [int64]$_.TransmitLinkSpeed) }
        Descending = $true
    } | Select-Object -First 1
    $interfaceIndex = [int]$adapter.ifIndex
    $actions += 'Verified active physical Ethernet with no default gateway.'

    $binding = Get-NetAdapterBinding -Name $adapter.Name -ComponentID 'ms_tcpip6' -ErrorAction Stop
    $restartRequired = -not [bool]$binding.Enabled
    if ($restartRequired) {
        Enable-NetAdapterBinding -Name $adapter.Name -ComponentID 'ms_tcpip6' -ErrorAction Stop | Out-Null
        $actions += 'Enabled IPv6, which EtherDrop uses for direct link-local communication.'
    } else {
        $actions += 'IPv6 was already enabled.'
    }

    try {
        Set-NetAdapterPowerManagement -Name $adapter.Name -SelectiveSuspend Disabled -DeviceSleepOnDisconnect Disabled -NoRestart -ErrorAction Stop
        $actions += 'Disabled supported Ethernet selective-suspend settings.'
    } catch {
        $warnings += ('The adapter did not accept every power setting: ' + $_.Exception.Message)
    }

    $discoveryRule = 'EtherDrop-Direct-Discovery'
    $transferRule = 'EtherDrop-Direct-Transfer'
    Get-NetFirewallRule -Name $discoveryRule -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue
    Get-NetFirewallRule -Name $transferRule -ErrorAction SilentlyContinue | Remove-NetFirewallRule -ErrorAction SilentlyContinue

    New-NetFirewallRule `
        -Name $discoveryRule `
        -DisplayName 'EtherDrop direct-link discovery' `
        -Description 'Allows EtherDrop IPv6 link-local discovery on the selected physical Ethernet adapter only.' `
        -Group 'EtherDrop' `
        -Enabled True `
        -Profile Any `
        -Direction Inbound `
        -Action Allow `
        -EdgeTraversalPolicy Block `
        -Program $ProgramPath `
        -InterfaceAlias $adapter.Name `
        -InterfaceType Wired `
        -RemoteAddress 'fe80::/10' `
        -Protocol UDP `
        -LocalPort $DiscoveryPort `
        -ErrorAction Stop | Out-Null

    New-NetFirewallRule `
        -Name $transferRule `
        -DisplayName 'EtherDrop direct-link transfer' `
        -Description 'Allows EtherDrop TCP transfers from IPv6 link-local peers on the selected physical Ethernet adapter only.' `
        -Group 'EtherDrop' `
        -Enabled True `
        -Profile Any `
        -Direction Inbound `
        -Action Allow `
        -EdgeTraversalPolicy Block `
        -Program $ProgramPath `
        -InterfaceAlias $adapter.Name `
        -InterfaceType Wired `
        -RemoteAddress 'fe80::/10' `
        -Protocol TCP `
        -LocalPort $TransferPort `
        -ErrorAction Stop | Out-Null
    $actions += 'Replaced EtherDrop firewall rules with direct-link-only UDP and TCP rules.'

    if ($restartRequired) {
        Restart-NetAdapter -Name $adapter.Name -Confirm:$false -ErrorAction Stop
        $actions += 'Restarted the Ethernet adapter because IPv6 had to be enabled.'
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            Start-Sleep -Milliseconds 500
            $current = Get-NetAdapter -Name $adapter.Name -ErrorAction SilentlyContinue
            if ($current -and $current.Status -eq 'Up') { break }
        }
    }

    $linkLocal = $null
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $linkLocal = Get-NetIPAddress -InterfaceIndex $interfaceIndex -AddressFamily IPv6 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -like 'fe80::*' } |
            Select-Object -First 1 -ExpandProperty IPAddress
        if ($linkLocal) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $linkLocal) {
        throw 'IPv6 is enabled, but Windows did not create a link-local address. Check the cable and adapter driver.'
    }
    $actions += ('Confirmed IPv6 link-local address ' + $linkLocal + '.')

    $result = [PSCustomObject]@{
        Success = $true
        Adapter = [string]$adapter.Name
        InterfaceIndex = $interfaceIndex
        LinkLocal = [string]$linkLocal
        ProgramPath = [string]$ProgramPath
        Actions = @($actions)
        Warnings = @($warnings)
    }
} catch {
    $exitCode = 1
    $result = [PSCustomObject]@{
        Success = $false
        Error = [string]$_.Exception.Message
        Actions = @($actions)
        Warnings = @($warnings)
    }
}

$result | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $ResultPath -Encoding UTF8
exit $exitCode
'''


def powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def version_tuple(value: str) -> tuple[int, int, int]:
    parts = value.removeprefix("v").split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise ValueError("Release versions must use vMAJOR.MINOR.PATCH, for example v1.0.1.")
    return tuple(int(part) for part in parts)


def latest_release() -> dict | None:
    request = Request(
        f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases/latest",
        headers={"Accept": "application/vnd.github+json", "User-Agent": f"{APP_NAME}/{APP_VERSION}"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            release = json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    asset = next((asset for asset in release["assets"] if asset["name"] == RELEASE_ASSET), None)
    if version_tuple(release["tag_name"]) > version_tuple(APP_VERSION) and asset is None:
        raise RuntimeError(f"The latest release does not contain {RELEASE_ASSET} yet.")
    return {"version": release["tag_name"], "notes": release.get("body") or "No update notes were provided.", "asset": asset}


def bundled_release_notes() -> str:
    return Path(__file__).with_name("RELEASE_NOTES.md").read_text(encoding="utf-8").strip()


def update_state_path() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / APP_NAME / "updates.json"


def load_update_state() -> dict:
    try:
        return json.loads(update_state_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_update_state(state: dict) -> None:
    path = update_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state), encoding="utf-8")


def download_update(release: dict, events: queue.Queue) -> Path:
    target = Path(sys.executable).resolve()
    staging = Path(tempfile.mkdtemp(prefix=".etherdrop-update-", dir=target.parent))
    try:
        asset = release["asset"]
        request = Request(asset["browser_download_url"], headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
        downloaded = staging / RELEASE_ASSET
        digest = hashlib.sha256()
        done = 0
        last_progress = time.monotonic()
        last_done = 0
        events.put(("update_progress", 0, asset["size"], 0.0))
        with urlopen(request, timeout=30) as response, downloaded.open("wb") as output:
            while block := response.read(64 * 1024):
                output.write(block)
                digest.update(block)
                done += len(block)
                now = time.monotonic()
                if now - last_progress >= 0.25 or done == asset["size"]:
                    speed = (done - last_done) / max(now - last_progress, 0.001)
                    events.put(("update_progress", done, asset["size"], speed))
                    last_progress, last_done = now, done
        if done != asset["size"] or done == 0:
            raise RuntimeError("The update download is incomplete. Please try again.")
        expected_digest = asset.get("digest")
        if expected_digest and expected_digest != "sha256:" + digest.hexdigest():
            raise RuntimeError("The update checksum does not match the GitHub release.")
        with downloaded.open("rb") as source:
            if source.read(2) != b"MZ":
                raise RuntimeError("The downloaded update is not a Windows executable.")
        return staging
    except Exception:
        shutil.rmtree(staging)
        raise


def launch_updater(staging: Path) -> None:
    target = Path(sys.executable).resolve()
    script = staging / "update.ps1"
    script.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        f"$target = {powershell_literal(str(target))}\n"
        f"$staging = {powershell_literal(str(staging))}\n"
        f"$download = {powershell_literal(str(staging / RELEASE_ASSET))}\n"
        "$backup = Join-Path $staging 'previous.exe'\n"
        "$cleanup = $true\n"
        "try {\n"
        f"    Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue\n"
        "    $replaced = $false\n"
        "    for ($attempt = 0; $attempt -lt 60; $attempt++) {\n"
        "        try { Move-Item -LiteralPath $target -Destination $backup; $replaced = $true; break }\n"
        "        catch { Start-Sleep -Milliseconds 500 }\n"
        "    }\n"
        "    if (-not $replaced) { throw 'The current executable is still locked or its folder is not writable.' }\n"
        "    Move-Item -LiteralPath $download -Destination $target\n"
        "    Start-Process -FilePath $target -WorkingDirectory (Split-Path -LiteralPath $target)\n"
        "} catch {\n"
        "    $failure = $_.Exception.Message\n"
        "    if (Test-Path -LiteralPath $backup) {\n"
        "        try {\n"
        "            if (Test-Path -LiteralPath $target) { Remove-Item -LiteralPath $target -Force }\n"
        "            Move-Item -LiteralPath $backup -Destination $target\n"
        "        } catch { $cleanup = $false; $failure += '\nPrevious executable retained at: ' + $backup }\n"
        "    }\n"
        "    Add-Type -AssemblyName System.Windows.Forms\n"
        "    [System.Windows.Forms.MessageBox]::Show($failure, 'EtherDrop update failed') | Out-Null\n"
        "    if (Test-Path -LiteralPath $target) {\n"
        "        Start-Process -FilePath $target -WorkingDirectory (Split-Path -LiteralPath $target)\n"
        "    }\n"
        "} finally {\n"
        "    if ($cleanup) { Remove-Item -LiteralPath $staging -Recurse -Force }\n"
        "}\n",
        encoding="utf-8-sig",
    )
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script)],
        env={**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"},
        creationflags=subprocess.CREATE_NO_WINDOW,
        cwd=str(target.parent),
    )


def run_ethernet_autoconfigure(program_path: Path) -> dict:
    temporary_dir = Path(tempfile.mkdtemp(prefix="EtherDropSetup_"))
    script_path = temporary_dir / "configure_ethernet.ps1"
    result_path = temporary_dir / "result.json"
    script_path.write_text(ETHERNET_SETUP_SCRIPT, encoding="utf-8-sig")

    elevated_arguments = [
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script_path),
        "-ProgramPath",
        str(program_path),
        "-DiscoveryPort",
        str(DISCOVERY_PORT),
        "-TransferPort",
        str(TRANSFER_PORT),
        "-ResultPath",
        str(result_path),
    ]
    argument_line = subprocess.list2cmdline(elevated_arguments)
    launcher = (
        "$process = Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Hidden "
        f"-Wait -PassThru -ArgumentList {powershell_literal(argument_line)}; exit $process.ExitCode"
    )

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", launcher],
            capture_output=True,
            text=True,
            creationflags=creationflags,
            timeout=120,
        )
        if not result_path.exists():
            detail = completed.stderr.strip() or completed.stdout.strip()
            if "canceled by the user" in detail.lower() or "cancelled by the user" in detail.lower():
                raise RuntimeError("Administrator permission was cancelled. No Ethernet settings were changed.")
            raise RuntimeError(detail or "The elevated Ethernet setup did not return a result.")

        result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        if not result.get("Success"):
            error_lines = [str(result.get("Error") or "Ethernet setup failed.")]
            completed_actions = result.get("Actions") or []
            setup_warnings = result.get("Warnings") or []
            if isinstance(completed_actions, str):
                completed_actions = [completed_actions]
            if isinstance(setup_warnings, str):
                setup_warnings = [setup_warnings]
            if completed_actions:
                error_lines.extend(("", "Completed before the failure:", *(f"• {item}" for item in completed_actions)))
            if setup_warnings:
                error_lines.extend(("", "Warnings:", *(f"• {item}" for item in setup_warnings)))
            raise RuntimeError("\n".join(error_lines))
        return result
    finally:
        shutil.rmtree(temporary_dir, ignore_errors=True)


def choose_direct_adapter() -> EthernetAdapter:
    adapters = discover_ethernet_adapters()
    direct = [a for a in adapters if not a.has_gateway]
    if not direct:
        if adapters:
            raise RuntimeError(
                "A physical Ethernet link is up, but every Ethernet adapter has a default gateway.\n\n"
                "EtherDrop refuses to use it because it looks like a normal LAN rather than a direct cable."
            )
        raise RuntimeError(
            "No active physical Ethernet cable was detected.\n\n"
            "Connect the two laptops directly with Ethernet, then click Rescan."
        )

    direct.sort(key=lambda a: min(a.rx_bps or 0, a.tx_bps or 0), reverse=True)
    return direct[0]


def ipv6_scope_tuple(ip: str, port: int, if_index: int) -> tuple[str, int, int, int]:
    return (ip, port, 0, if_index)


def configure_stream_socket(sock: socket.socket, automatic_buffers: bool = False) -> None:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    if not automatic_buffers:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SOCKET_BUFFER)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCKET_BUFFER)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)


def socket_diagnostics(sock: socket.socket) -> dict[str, str | int]:
    def endpoint(value) -> str:
        if not value:
            return "Not connected"
        host, port, *_ = value
        scope = value[3] if len(value) > 3 else 0
        suffix = f"%{scope}" if scope else ""
        return f"[{host}{suffix}]:{port}"

    return {
        "Local TCP endpoint": endpoint(sock.getsockname()),
        "Remote TCP endpoint": endpoint(sock.getpeername()),
        "Actual send buffer": sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF),
        "Actual receive buffer": sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF),
        "TCP keepalive": "Enabled" if sock.getsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE) else "Disabled",
        "TCP no-delay": "Enabled" if sock.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY) else "Disabled",
    }


def emit_transfer(events: queue.Queue, transfer_id: str, action: str, **details) -> None:
    events.put(("transfer", transfer_id, action, details))


def send_frame(sock: socket.socket, payload: dict) -> None:
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(raw) > MAX_CONTROL_FRAME:
        raise ValueError("Control frame too large.")
    sock.sendall(struct.pack("!I", len(raw)))
    sock.sendall(raw)


def recv_exact(sock: socket.socket, count: int) -> bytes:
    out = bytearray(count)
    view = memoryview(out)
    pos = 0
    while pos < count:
        got = sock.recv_into(view[pos:])
        if got == 0:
            raise ConnectionError("Connection closed unexpectedly.")
        pos += got
    return bytes(out)


def recv_frame(sock: socket.socket) -> dict:
    size = struct.unpack("!I", recv_exact(sock, 4))[0]
    if size <= 0 or size > MAX_CONTROL_FRAME:
        raise ValueError("Invalid control frame.")
    return json.loads(recv_exact(sock, size).decode("utf-8"))


def safe_relative_path(value: str) -> Path:
    p = PurePosixPath(value)
    if "\\" in value or ":" in value or p.is_absolute() or not p.parts:
        raise ValueError("Unsafe file path.")
    if any(part in ("", ".", "..") for part in p.parts):
        raise ValueError("Unsafe file path.")
    return Path(*p.parts)


def unique_transfer_root(base: Path, peer_name: str) -> Path:
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in peer_name)[:80] or "peer"
    stamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    candidate = base / f"{stamp}_from_{safe_name}"
    n = 2
    while candidate.exists():
        candidate = base / f"{stamp}_from_{safe_name}_{n}"
        n += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def windows_move_transfer(source: Path, destination: Path, cancel_event: threading.Event,
                          owner: int, created: set[Path]) -> None:
    """Let the Windows shell merge folders and ask about conflicting files."""
    pointer, word, text = ctypes.c_void_p, ctypes.c_uint32, ctypes.c_wchar_p
    ole32, shell32 = ctypes.windll.ole32, ctypes.windll.shell32
    ole32.CoInitializeEx.argtypes = [pointer, word]
    ole32.CoCreateInstance.argtypes = [pointer, pointer, word, pointer, pointer]
    ole32.CoTaskMemFree.argtypes = [pointer]
    shell32.SHCreateItemFromParsingName.argtypes = [text, pointer, pointer, pointer]

    def guid(value):
        return ctypes.create_string_buffer(uuid.UUID(value).bytes_le, 16)

    def call(item, index, types=(), *args):
        table = ctypes.cast(item, ctypes.POINTER(ctypes.POINTER(pointer))).contents
        method = ctypes.WINFUNCTYPE(ctypes.c_long, pointer, *types)(table[index])
        return method(item, *args)

    def check(result):
        if result < 0:
            if result & 0xFFFFFFFF in (0x80004004, 0x800704C7, 0x80270000):
                raise TransferCancelled("Transfer cancelled while saving files.")
            raise ctypes.WinError(result)

    def item_path(item):
        name = pointer()
        check(call(item, 5, (word, pointer), 0x80058000, ctypes.byref(name)))  # SIGDN_FILESYSPATH
        try:
            return Path(ctypes.wstring_at(name))
        finally:
            ole32.CoTaskMemFree(name)

    def shell_item(path):
        item = pointer()
        check(shell32.SHCreateItemFromParsingName(str(path), None, shell_iid, ctypes.byref(item)))
        return item

    existing = set()
    for path in source.rglob("*"):
        target = destination / path.relative_to(source)
        if target.exists():
            existing.add(target)
        else:
            created.add(target)

    errors, skipped = [], []
    references = [1]
    sink_iid = uuid.UUID("04b0f1a7-9490-44bc-96e1-4296a31252e2").bytes_le
    unknown_iid = uuid.UUID("00000000-0000-0000-c000-000000000046").bytes_le

    def query(this, iid, output):
        if ctypes.string_at(iid, 16) not in (unknown_iid, sink_iid):
            output[0] = None
            return -2147467262  # E_NOINTERFACE
        output[0] = this
        references[0] += 1
        return 0

    def add_ref(this):
        references[0] += 1
        return references[0]

    def release(this):
        references[0] -= 1
        return references[0]

    def progress(*args):
        return -2147467260 if cancel_event.is_set() else 0  # E_ABORT

    def finish(this, result):
        if result < 0:
            errors.append(result)
        return 0

    def moved(this, flags, item, folder, name, result, new_item):
        if result < 0:
            errors.append(result)
        elif result == 0x00270005:  # COPYENGINE_S_USER_IGNORED
            skipped.append(item)
        elif new_item:
            try:
                path = item_path(new_item)
                path.resolve().relative_to(destination)
                if path not in existing:
                    created.add(path)
                    if path.is_dir():
                        created.update(path.rglob("*"))
            except Exception:
                return -2147467259  # E_FAIL
        return progress()

    # IFileOperationProgressSink, in COM vtable order. Unused notifications are no-ops.
    signatures = [
        (query, (pointer, ctypes.POINTER(pointer))), (add_ref, ()), (release, ()),
        (progress, ()), (finish, (ctypes.c_long,)),
        (progress, (word, pointer, text)), (progress, (word, pointer, text, ctypes.c_long, pointer)),
        (progress, (word, pointer, pointer, text)),
        (moved, (word, pointer, pointer, text, ctypes.c_long, pointer)),
        (progress, (word, pointer, pointer, text)),
        (progress, (word, pointer, pointer, text, ctypes.c_long, pointer)),
        (progress, (word, pointer)), (progress, (word, pointer, ctypes.c_long, pointer)),
        (progress, (word, pointer, text)),
        (progress, (word, pointer, text, text, word, ctypes.c_long, pointer)),
        (progress, (word, word)), (progress, ()), (progress, ()), (progress, ()),
    ]
    callbacks = [ctypes.WINFUNCTYPE(ctypes.c_long, pointer, *types)(callback)
                 for callback, types in signatures]
    table = (pointer * len(callbacks))(*(ctypes.cast(callback, pointer).value for callback in callbacks))
    sink = ctypes.pointer(ctypes.cast(table, pointer))
    operation, folder = pointer(), pointer()
    shell_iid = guid("43826d1e-e718-42ee-bc55-a1e261c37bfe")
    finished = threading.Event()
    thread_id = ctypes.windll.kernel32.GetCurrentThreadId()

    def close_cancelled_dialogs():
        user32 = ctypes.windll.user32
        window_callback = ctypes.WINFUNCTYPE(ctypes.c_int, pointer, ctypes.c_ssize_t)
        user32.EnumThreadWindows.argtypes = [word, window_callback, ctypes.c_ssize_t]
        user32.IsWindowVisible.argtypes = [pointer]
        user32.PostMessageW.argtypes = [pointer, word, ctypes.c_size_t, ctypes.c_ssize_t]

        def close_window(window, context):
            if user32.IsWindowVisible(window):
                user32.PostMessageW(window, 0x0010, 0, 0)  # WM_CLOSE, like Cancel in the shell dialog
            return 1

        callback = window_callback(close_window)
        while not finished.wait(0.1):
            if cancel_event.is_set():
                user32.EnumThreadWindows(thread_id, callback, 0)

    check(ole32.CoInitializeEx(None, 2))  # COINIT_APARTMENTTHREADED
    try:
        check(ole32.CoCreateInstance(guid("3ad05575-8857-4850-9277-11b85bdb8e09"), None, 1,
                                    guid("947aab5f-0a5c-4c13-b4d6-4bf7836fc9f8"), ctypes.byref(operation)))
        check(call(operation, 5, (word,), 0x0004 | 0x0200))  # FOF_SILENT | FOF_NOCONFIRMMKDIR
        check(call(operation, 9, (pointer,), owner))
        cookie = word()
        check(call(operation, 3, (pointer, pointer), sink, ctypes.byref(cookie)))
        folder = shell_item(destination)
        for path in source.iterdir():
            if cancel_event.is_set():
                raise TransferCancelled("Transfer cancelled while saving files.")
            item = shell_item(path)
            try:
                check(call(operation, 14, (pointer, pointer, text, pointer), item, folder, None, None))
            finally:
                call(item, 2)
        threading.Thread(target=close_cancelled_dialogs, daemon=True).start()
        result = call(operation, 21)
        aborted = ctypes.c_int()
        check(call(operation, 22, (pointer,), ctypes.byref(aborted)))
        for error in errors:
            check(error)
        check(result)
        if cancel_event.is_set() or (aborted.value and not skipped):
            raise TransferCancelled("Transfer cancelled while saving files.")
    finally:
        finished.set()
        if folder:
            call(folder, 2)
        if operation:
            call(operation, 2)
        ole32.CoUninitialize()


class ReceivedOutput:
    def __init__(self, destination: Path, peer_name: str, wrap: bool):
        self.destination = destination.resolve()
        self.root = unique_transfer_root(self.destination, peer_name) if wrap else self.destination
        self.data_root = self.root if wrap else Path(tempfile.mkdtemp(prefix=".etherdrop-transfer-", dir=self.destination))
        self.created: set[Path] = set()
        self.wrap = wrap

    def save(self, cancel_event: threading.Event, owner: int) -> None:
        if not self.wrap:
            windows_move_transfer(self.data_root, self.destination, cancel_event, owner, self.created)
            self._remove_staging()

    def _remove_staging(self) -> None:
        path = self.data_root.resolve()
        if path.parent != self.destination:
            raise ValueError("Transfer output is outside the chosen destination.")
        if path.exists():
            shutil.rmtree(path)

    def cancel(self) -> None:
        self._remove_staging()
        for path in sorted(self.created, key=lambda value: len(value.parts), reverse=True):
            resolved = path.resolve()
            if resolved == self.destination or not resolved.is_relative_to(self.destination):
                raise ValueError("Transfer output is outside the chosen destination.")
            if path.is_dir():
                path.rmdir()
            elif path.exists():
                path.unlink()


def build_transfer_items(
    paths: list[Path],
    cancel_event: threading.Event | None = None,
) -> tuple[list[TransferItem], int]:
    items: list[TransferItem] = []
    total = 0
    used_roots: set[str] = set()

    def unique_root_name(name: str) -> str:
        candidate = name
        i = 2
        while candidate.casefold() in used_roots:
            candidate = f"{name}_{i}"
            i += 1
        used_roots.add(candidate.casefold())
        return candidate

    for selected in paths:
        if cancel_event and cancel_event.is_set():
            raise TransferCancelled("Transfer cancelled while scanning selected files.")
        selected = selected.resolve()
        if not selected.exists() or selected.is_symlink():
            continue

        root_name = unique_root_name(selected.name)

        if selected.is_file():
            info = selected.stat()
            size = info.st_size
            items.append(TransferItem(selected, PurePosixPath(root_name).as_posix(), size, info.st_mtime_ns))
            total += size
            continue

        if selected.is_dir():
            for dirpath, dirnames, filenames in os.walk(selected, followlinks=False):
                if cancel_event and cancel_event.is_set():
                    raise TransferCancelled("Transfer cancelled while scanning selected files.")
                dirnames[:] = [d for d in dirnames if not (Path(dirpath) / d).is_symlink()]
                for filename in filenames:
                    if cancel_event and cancel_event.is_set():
                        raise TransferCancelled("Transfer cancelled while scanning selected files.")
                    src = Path(dirpath) / filename
                    try:
                        if src.is_symlink() or not src.is_file():
                            continue
                        info = src.stat()
                        size = info.st_size
                    except OSError:
                        continue
                    rel = src.relative_to(selected)
                    remote = PurePosixPath(root_name, *rel.parts).as_posix()
                    items.append(TransferItem(src, remote, size, info.st_mtime_ns))
                    total += size

    return items, total


class DiscoveryService:
    def __init__(self, adapter: EthernetAdapter, events: queue.Queue, role: str):
        self.adapter = adapter
        self.events = events
        self.role = role
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.peer_ip: str | None = None
        self.peer_name: str | None = None
        self.peer_last_seen = 0.0

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="discovery", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def _announce(self, sock: socket.socket) -> None:
        payload = json.dumps(
            {
                "magic": MAGIC,
                "version": PROTOCOL_VERSION,
                "session": SESSION_ID,
                "hostname": socket.gethostname(),
                "role": self.role,
                "ready": True,
                "transfer_port": TRANSFER_PORT,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        sock.sendto(payload, (DISCOVERY_GROUP, DISCOVERY_PORT, 0, self.adapter.if_index))

    def _run(self) -> None:
        sock = None
        try:
            sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)

            mreq = socket.inet_pton(socket.AF_INET6, DISCOVERY_GROUP) + struct.pack("@I", self.adapter.if_index)
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP, mreq)
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_IF, self.adapter.if_index)
            sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_MULTICAST_HOPS, 1)
            sock.bind(("::", DISCOVERY_PORT))
            sock.settimeout(0.25)

            last_announce = 0.0
            while not self.stop_event.is_set():
                now = time.monotonic()
                if now - last_announce >= ANNOUNCE_INTERVAL:
                    try:
                        self._announce(sock)
                    except OSError:
                        pass
                    last_announce = now

                try:
                    data, addr = sock.recvfrom(4096)
                except socket.timeout:
                    data = None
                    addr = None

                if data and addr:
                    try:
                        msg = json.loads(data.decode("utf-8"))
                        if (
                            msg.get("magic") == MAGIC
                            and msg.get("version") == PROTOCOL_VERSION
                            and msg.get("session") != SESSION_ID
                            and msg.get("role") in ("sender", "receiver")
                            and msg.get("role") != self.role
                        ):
                            source_ip = addr[0].split("%")[0]
                            if source_ip.lower().startswith("fe80:"):
                                self.peer_ip = source_ip
                                self.peer_name = str(msg.get("hostname") or "Other laptop")
                                self.peer_last_seen = time.monotonic()
                                self.events.put(("peer", self.peer_name, self.peer_ip, str(msg["role"])))
                    except Exception:
                        pass

                if self.peer_ip and time.monotonic() - self.peer_last_seen > PEER_TIMEOUT:
                    self.peer_ip = None
                    self.peer_name = None
                    self.events.put(("peer_lost",))
        except Exception as exc:
            self.events.put(("error", f"Discovery failed: {exc}"))
        finally:
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass


class WifiDiscoveryService(DiscoveryService):
    def __init__(self, adapter, events, role):
        super().__init__(adapter, events, role)
        self.peers = {}
        self.token = uuid.uuid4().hex

    def _accept_announcement(self, msg, source_ip, now):
        if (msg.get("magic") != MAGIC or msg.get("version") != PROTOCOL_VERSION
                or msg.get("mode") != "wifi" or msg.get("session") == SESSION_ID
                or msg.get("role") not in ("sender", "receiver") or msg.get("role") == self.role
                or not isinstance(msg.get("session"), str) or not msg["session"]
                or ipaddress.ip_address(source_ip) not in self.adapter.network):
            return
        session = msg["session"]
        name = str(msg.get("hostname") or "Other laptop")
        self.peers[session] = (name, source_ip, msg["role"], now)
        self.events.put(("wifi_peer", self.token, session, name, source_ip, msg["role"]))

    def _expire_peers(self, now):
        for session, peer in list(self.peers.items()):
            if now - peer[3] > PEER_TIMEOUT:
                del self.peers[session]
                self.events.put(("wifi_peer_lost", self.token, session))

    def _run(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                # Windows receives subnet broadcasts on a wildcard listener. Outgoing
                # broadcasts use a separate socket bound to the selected interface.
                sock.bind(("", DISCOVERY_PORT))
                sock.settimeout(0.25)
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as announce:
                    announce.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    announce.bind((self.adapter.address, 0))
                    last = 0.0
                    while not self.stop_event.is_set():
                        now = time.monotonic()
                        if now - last >= ANNOUNCE_INTERVAL:
                            payload = json.dumps({"magic": MAGIC, "version": PROTOCOL_VERSION,
                                "mode": "wifi", "session": SESSION_ID, "hostname": socket.gethostname(),
                                "role": self.role, "transfer_port": TRANSFER_PORT}).encode("utf-8")
                            announce.sendto(payload, (str(self.adapter.network.broadcast_address), DISCOVERY_PORT))
                            last = now
                        try:
                            data, addr = sock.recvfrom(4096)
                            self._accept_announcement(json.loads(data.decode("utf-8")), addr[0], now)
                        except socket.timeout:
                            pass
                        except (ValueError, TypeError, AttributeError):
                            pass
                        self._expire_peers(time.monotonic())
        except OSError as exc:
            if not self.stop_event.is_set():
                self.events.put(("wifi_discovery_error", self.token, str(exc)))


def close_transfer_socket(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    sock.close()


class TransferChannel:
    """Heartbeats keep approval and Windows dialogs separate from a lost connection."""

    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.sock.settimeout(TRANSFER_TIMEOUT)
        self.send_lock = threading.Lock()
        self.closed = threading.Event()
        threading.Thread(target=self._heartbeat, daemon=True, name="transfer-heartbeat").start()

    def send(self, payload: dict) -> None:
        with self.send_lock:
            try:
                send_frame(self.sock, payload)
            except OSError as exc:
                raise TransferInterrupted(str(exc)) from exc

    def receive(self) -> dict:
        while True:
            try:
                payload = recv_frame(self.sock)
            except OSError as exc:
                raise TransferInterrupted(str(exc)) from exc
            if payload.get("type") != "ping":
                return payload

    def send_bytes(self, block) -> None:
        try:
            self.sock.sendall(block)
        except OSError as exc:
            raise TransferInterrupted(str(exc)) from exc

    def receive_bytes(self, block) -> int:
        try:
            got = self.sock.recv_into(block)
        except OSError as exc:
            raise TransferInterrupted(str(exc)) from exc
        if not got:
            raise TransferInterrupted("Connection closed unexpectedly.")
        return got

    def send_file_frame(self, payload: dict) -> None:
        # The caller holds send_lock across metadata, file data, and the hash trailer.
        try:
            send_frame(self.sock, payload)
        except OSError as exc:
            raise TransferInterrupted(str(exc)) from exc

    def _heartbeat(self) -> None:
        while not self.closed.wait(TRANSFER_HEARTBEAT_INTERVAL):
            # File data holds this lock, so a heartbeat never enters the byte stream.
            if not self.send_lock.acquire(timeout=0.1):
                continue
            try:
                send_frame(self.sock, {"type": "ping"})
            except OSError:
                self.close()
                return
            finally:
                self.send_lock.release()

    def close(self) -> None:
        self.closed.set()
        close_transfer_socket(self.sock)


@dataclass
class IncomingTransfer:
    offer: dict
    peer_ip: str
    decision: IncomingTransferDecision = field(default_factory=IncomingTransferDecision)
    lock: threading.Lock = field(default_factory=threading.Lock)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    output: ReceivedOutput | None = None
    index: int = 0
    offset: int = 0
    done: int = 0
    current: dict | None = None
    hasher: object = None
    saved_files: dict = field(default_factory=dict)
    started: float = 0.0
    result: dict | None = None
    cancel_reason: str = "Transfer cancelled by the receiver."
    aborted: bool = False

    @property
    def transfer_id(self) -> str:
        return self.offer["transfer_id"]


class ReceiverService:
    def __init__(self, adapter: EthernetAdapter, events: queue.Queue, coordinator: threading.Lock):
        self.adapter = adapter
        self.events = events
        self.coordinator = coordinator
        self.stop_event = threading.Event()
        self.server_socket: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.state_lock = threading.Lock()
        self.session: IncomingTransfer | None = None
        self.active_transfer_id: str | None = None
        self.active_socket: socket.socket | None = None
        self.active_cancel: threading.Event | None = None
        self.active_decision: IncomingTransferDecision | None = None
        self.active_send_lock: threading.Lock | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="receiver", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.cancel()
        if self.server_socket:
            self.server_socket.close()

    def _request_cancel(self, session: IncomingTransfer, reason: str) -> None:
        session.cancel_reason = reason
        session.cancel_event.set()
        session.decision.reject(reason)
        with self.state_lock:
            conn = self.active_socket if self.session is session else None
            send_lock = self.active_send_lock
        if conn:
            if send_lock and send_lock.acquire(blocking=False):
                try:
                    send_frame(conn, {"type": "cancel", "reason": reason})
                except OSError:
                    pass
                finally:
                    send_lock.release()
            close_transfer_socket(conn)

    def cancel(self, transfer_id: str | None = None) -> None:
        with self.state_lock:
            session = self.session
        if not session or session.result or (transfer_id and transfer_id != session.transfer_id):
            return
        self._request_cancel(session, "Transfer cancelled by the receiver.")

        def cleanup():
            with session.lock:
                self._finish_cancel(session)

        # Cleanup also runs when the receiver is paused, with no connection worker.
        threading.Thread(target=cleanup, name="transfer-cleanup").start()

    def _finish(self, session: IncomingTransfer, result: dict, action: str, **details) -> None:
        if session.result:
            return
        session.result = result
        with self.state_lock:
            self.active_transfer_id = None
            self.active_cancel = None
            self.active_decision = None
        self.coordinator.release()
        emit_transfer(self.events, session.transfer_id, action, **details)

    def _finish_cancel(self, session: IncomingTransfer) -> None:
        if session.result:
            return
        try:
            if session.output:
                session.output.cancel()
        except Exception as exc:
            output = session.output
            message = f"{session.cancel_reason} Could not remove the new output: {exc}"
            self._finish(session, {"type": "error", "reason": message}, "failed",
                         message=message, error_type=type(exc).__name__, cleanup="Incomplete",
                         destination=str(output.data_root if output.data_root.exists() else output.root))
        else:
            self._finish(session, {"type": "error" if session.aborted else "cancel", "reason": session.cancel_reason},
                         "failed" if session.aborted else "cancelled",
                         message=session.cancel_reason,
                         cleanup="New transfer output removed" if session.output else "No output created")

    def _run(self) -> None:
        srv = None
        try:
            srv = socket.socket(adapter_family(self.adapter), socket.SOCK_STREAM)
            self.server_socket = srv
            if not isinstance(self.adapter, WifiAdapter):
                srv.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            configure_stream_socket(srv, automatic_buffers=isinstance(self.adapter, WifiAdapter))
            srv.bind(adapter_endpoint(self.adapter, TRANSFER_PORT))
            srv.listen(2)
            srv.settimeout(0.5)
            while not self.stop_event.is_set():
                try:
                    conn, addr = srv.accept()
                except socket.timeout:
                    continue
                except OSError:
                    if self.stop_event.is_set():
                        break
                    raise
                threading.Thread(target=self._handle_connection, args=(conn, addr),
                                 daemon=True, name="incoming-transfer").start()
        except Exception as exc:
            if not self.stop_event.is_set():
                self.events.put(("error", f"Receiver failed: {exc}"))
        finally:
            if srv:
                srv.close()

    def _handle_connection(self, conn: socket.socket, addr) -> None:
        configure_stream_socket(conn, automatic_buffers=isinstance(self.adapter, WifiAdapter))
        channel = TransferChannel(conn)
        session = None
        try:
            offer = channel.receive()
            if offer.get("magic") != MAGIC or offer.get("version") != PROTOCOL_VERSION:
                raise ValueError("Both laptops need the same EtherDrop version.")
            transfer_id = str(offer.get("transfer_id") or "")
            if not transfer_id:
                raise ValueError("Missing transfer identifier.")
            peer_ip = str(addr[0]).split("%")[0]
            with self.state_lock:
                existing = self.session
                matched = existing and existing.transfer_id == transfer_id and existing.peer_ip == peer_ip
                if offer.get("type") in ("cancel", "abort"):
                    session = existing if matched else None
                elif offer.get("type") != "offer":
                    raise ValueError("Invalid EtherDrop connection.")
                elif matched:
                    if any(offer.get(key) != existing.offer.get(key)
                           for key in ("manifest", "total_bytes", "file_count", "verify", "wrap")):
                        raise ValueError("The transfer contents have changed.")
                    session = existing
                elif offer.get("resume"):
                    channel.send({"type": "reject", "reason": "This transfer is no longer available. Send it again."})
                    return
                elif self.stop_event.is_set() or not self.coordinator.acquire(blocking=False):
                    channel.send({"type": "reject", "reason": "This laptop is already handling another transfer."})
                    return
                else:
                    session = self.session = IncomingTransfer(offer, peer_ip)
                    self.active_transfer_id = transfer_id
                    self.active_cancel = session.cancel_event
                    self.active_decision = session.decision
                    emit_transfer(self.events, transfer_id, "incoming_offer",
                                  peer=offer.get("hostname") or "Other laptop", peer_ip=peer_ip,
                                  total=offer["total_bytes"], file_count=offer["file_count"],
                                  verify=offer["verify"], wrap=offer.get("wrap", True),
                                  roots=offer.get("roots", []), decision=session.decision)

            if offer.get("type") in ("cancel", "abort"):
                if session:
                    session.aborted = offer["type"] == "abort"
                    self._request_cancel(session, str(offer.get("reason") or "Transfer cancelled by the sender."))
                    with session.lock:
                        self._finish_cancel(session)
                        channel.send(session.result)
                else:
                    channel.send({"type": "cancel", "reason": "No output created."})
                return

            with session.lock:
                if session.result:
                    channel.send(session.result)
                    return
                with self.state_lock:
                    self.active_socket = conn
                    self.active_send_lock = channel.send_lock
                try:
                    self._receive_transfer(channel, session)
                except TransferInterrupted:
                    if session.cancel_event.is_set():
                        self._finish_cancel(session)
                    elif not session.result:
                        emit_transfer(self.events, transfer_id, "paused", done=session.done,
                                      total=offer["total_bytes"], message="Connection interrupted. Waiting to reconnect — keep both apps open.")
                except TransferCancelled:
                    self._finish_cancel(session)
                    try:
                        channel.send(session.result)
                    except OSError:
                        pass
                except Exception as exc:
                    if session.cancel_event.is_set():
                        self._finish_cancel(session)
                    else:
                        self._finish(session, {"type": "error", "reason": str(exc)}, "failed",
                                     message=str(exc), error_type=type(exc).__name__,
                                     destination=str(session.output.data_root) if session.output else "Not created")
                    try:
                        channel.send(session.result)
                    except OSError:
                        pass
        except Exception as exc:
            if session and not session.result:
                with session.lock:
                    if session.cancel_event.is_set():
                        self._finish_cancel(session)
                    else:
                        self._finish(session, {"type": "error", "reason": str(exc)}, "failed",
                                     message=str(exc), error_type=type(exc).__name__,
                                     destination=str(session.output.data_root) if session.output else "Not created")
            try:
                channel.send({"type": "error", "reason": str(exc)})
            except OSError:
                pass
        finally:
            with self.state_lock:
                if self.active_socket is conn:
                    self.active_socket = None
                    self.active_send_lock = None
            channel.close()

    def _receive_transfer(self, channel: TransferChannel, session: IncomingTransfer) -> None:
        offer, decision = session.offer, session.decision
        tid = session.transfer_id
        verify = bool(offer["verify"])
        count, total = int(offer["file_count"]), int(offer["total_bytes"])
        while not decision.ready.wait(0.2):
            if session.cancel_event.is_set():
                raise TransferCancelled(session.cancel_reason)
            readable, _, _ = select.select([channel.sock], [], [], 0)
            if readable:
                try:
                    pending = recv_frame(channel.sock)
                except OSError as exc:
                    raise TransferInterrupted(str(exc)) from exc
                if pending.get("type") != "ping":
                    raise ValueError("Expected receiver approval.")
        if session.cancel_event.is_set():
            raise TransferCancelled(session.cancel_reason)
        if decision.destination is None:
            self._finish(session, {"type": "reject", "reason": decision.reason}, "rejected", message=decision.reason)
            channel.send(session.result)
            return

        resumed = session.output is not None
        if not resumed:
            destination = decision.destination.resolve()
            destination.mkdir(parents=True, exist_ok=True)
            session.output = ReceivedOutput(destination, str(offer.get("hostname") or "Other laptop"), bool(offer.get("wrap", True)))
            session.started = time.monotonic()
        output = session.output
        if resumed:
            for relative, signature in session.saved_files.items():
                info = (output.data_root / relative).stat()
                if (info.st_size, info.st_mtime_ns) != signature:
                    raise RuntimeError(f"Received file changed during interruption: {relative}. Send the transfer again.")
        disk = shutil.disk_usage(output.destination)
        emit_transfer(self.events, tid, "resumed" if resumed else "start", direction="Receiving",
                      peer=offer.get("hostname"), peer_ip=session.peer_ip, total=total, file_count=count,
                      verify=verify, wrap=output.wrap, destination=str(output.root), done=session.done,
                      index=session.index, socket=socket_diagnostics(channel.sock), storage={
                          "Receiver volume total": human_bytes(disk.total),
                          "Receiver volume free before transfer": human_bytes(disk.free),
                      })
        channel.send({"type": "accept", "destination": str(output.root), "disk_total": disk.total,
                      "disk_free": disk.free, "index": session.index, "offset": session.offset, "done": session.done})

        reusable = bytearray(BLOCK_SIZE)
        view = memoryview(reusable)
        while session.index < count:
            if session.cancel_event.is_set():
                raise TransferCancelled(session.cancel_reason)
            meta = channel.receive()
            if meta.get("type") != "file":
                raise ValueError("Expected file metadata.")
            relative = safe_relative_path(str(meta["path"]))
            size = int(meta["size"])
            if size < 0 or int(meta.get("offset", 0)) != session.offset:
                raise ValueError("Invalid file size or resume position.")
            current = {"path": relative.as_posix(), "size": size}
            if session.current and current != session.current:
                raise ValueError("The resumed file does not match the original transfer.")
            if session.current is None:
                session.current = current
                session.hasher = hashlib.sha256() if verify else None
            received_file = (output.data_root / relative).resolve()
            if not received_file.is_relative_to(output.data_root):
                raise ValueError("File path is outside the transfer destination.")
            received_file.parent.mkdir(parents=True, exist_ok=True)
            emit_transfer(self.events, tid, "file_start", index=session.index + 1, file_count=count,
                          path=relative.as_posix(), destination=str(output.root / relative), size=size)
            last_progress = 0.0
            try:
                with open(received_file, "r+b" if received_file.exists() else "w+b", buffering=0) as target:
                    target.seek(session.offset)
                    target.truncate()
                    while session.offset < size:
                        if session.cancel_event.is_set():
                            raise TransferCancelled(session.cancel_reason)
                        wanted = min(BLOCK_SIZE, size - session.offset)
                        filled = 0
                        while filled < wanted:
                            got = channel.receive_bytes(view[filled:wanted])
                            filled += got
                        block = view[:filled]
                        target.write(block)
                        if session.hasher:
                            session.hasher.update(block)
                        session.offset += filled
                        session.done += filled
                        now = time.monotonic()
                        if now - last_progress >= 0.10:
                            emit_transfer(self.events, tid, "progress", done=session.done, total=total,
                                          current_file_done=session.offset, current_file_size=size, current=relative.as_posix())
                            last_progress = now
            finally:
                # Windows finalizes the modification time when the file handle closes.
                info = received_file.stat()
                session.saved_files[relative.as_posix()] = (info.st_size, info.st_mtime_ns)
            digest = ""
            if verify:
                trailer = channel.receive()
                digest = session.hasher.hexdigest()
                if trailer.get("type") != "hash" or digest != trailer.get("sha256"):
                    raise RuntimeError(f"SHA-256 verification failed for {relative.as_posix()}")
            # Save the checkpoint before acknowledging it: a lost ACK skips this file on reconnect.
            session.index += 1
            session.offset = 0
            session.current = None
            session.hasher = None
            emit_transfer(self.events, tid, "file_done", index=session.index, path=relative.as_posix(), size=size, sha256=digest)
            channel.send({"type": "file_ok"})

        if channel.receive().get("type") != "done":
            raise ValueError("Transfer did not end correctly.")
        if session.cancel_event.is_set():
            raise TransferCancelled(session.cancel_reason)
        if not output.wrap:
            emit_transfer(self.events, tid, "phase", phase="Saving files",
                          message="Saving to the chosen destination. Resolve any Windows replace/skip prompts on the receiver.")
            saving_finished = threading.Event()

            def drain_heartbeats():
                while not saving_finished.is_set():
                    try:
                        if channel.receive().get("type") != "ping":
                            return
                    except OSError:
                        return

            threading.Thread(target=drain_heartbeats, daemon=True, name="save-connection-monitor").start()
            try:
                output.save(session.cancel_event, decision.owner)
            finally:
                saving_finished.set()
        if session.cancel_event.is_set():
            raise TransferCancelled(session.cancel_reason)
        elapsed = max(time.monotonic() - session.started, 0.001)
        # Cache completion before sending its ACK, so reconnecting never repeats the Windows save.
        self._finish(session, {"type": "done_ok"}, "done", done=session.done,
                     average_bps=session.done / elapsed, destination=str(output.root))
        channel.send(session.result)


class Sender:
    def __init__(self, adapter: EthernetAdapter, events: queue.Queue, coordinator: threading.Lock):
        self.adapter = adapter
        self.events = events
        self.coordinator = coordinator
        self.cancel_event = threading.Event()
        self.state_lock = threading.Lock()
        self.active_socket: socket.socket | None = None
        self.active_transfer_id: str | None = None

    def cancel(self, transfer_id: str | None = None) -> None:
        with self.state_lock:
            if transfer_id and transfer_id != self.active_transfer_id:
                return
            if self.cancel_event.is_set():
                return
            self.cancel_event.set()
            sock = self.active_socket
        if sock:
            close_transfer_socket(sock)

    def send(self, peer_ip: str, peer_name: str, paths: list[Path], verify: bool, wrap: bool = True) -> str | None:
        if not self.coordinator.acquire(blocking=False):
            return None
        transfer_id = uuid.uuid4().hex
        self.cancel_event.clear()
        with self.state_lock:
            self.active_transfer_id = transfer_id
        threading.Thread(target=self._send_worker,
                         args=(transfer_id, peer_ip, peer_name, paths, verify, None, wrap),
                         daemon=True, name="sender").start()
        return transfer_id

    def _connect(self, peer_ip: str) -> TransferChannel:
        sock = socket.socket(adapter_family(self.adapter), socket.SOCK_STREAM)
        configure_stream_socket(sock, automatic_buffers=isinstance(self.adapter, WifiAdapter))
        with self.state_lock:
            self.active_socket = sock
        try:
            sock.bind(adapter_endpoint(self.adapter, 0))
            sock.settimeout(5)
            sock.connect(adapter_endpoint(self.adapter, TRANSFER_PORT, peer_ip))
            return TransferChannel(sock)
        except Exception:
            close_transfer_socket(sock)
            raise

    def _notify_stop(self, peer_ip: str, transfer_id: str, reason: str, failed: bool = False) -> None:
        waiting = False
        while True:
            channel = None
            try:
                channel = self._connect(peer_ip)
                channel.send({"magic": MAGIC, "version": PROTOCOL_VERSION, "transfer_id": transfer_id,
                              "type": "abort" if failed else "cancel", "reason": reason})
                reply = channel.receive()
                if reply.get("type") == "error":
                    raise RuntimeError(str(reply.get("reason") or "Receiver cleanup failed."))
                return
            except OSError:
                if failed:
                    raise RuntimeError(f"{reason} Receiver unreachable; cancel on that laptop to remove its paused output.")
                if not waiting:
                    emit_transfer(self.events, transfer_id, "phase", phase="Cancelling",
                                  message="Waiting to reconnect so the receiver can remove the new output. Keep both apps open.")
                    waiting = True
            finally:
                if channel:
                    channel.close()
            time.sleep(RECONNECT_DELAY)

    def _send_worker(self, transfer_id: str, peer_ip: str, peer_name: str, paths: list[Path],
                     verify: bool, prepared: tuple | None = None, wrap: bool = True) -> None:
        channel = None
        offered = False
        started = 0.0
        try:
            emit_transfer(self.events, transfer_id, "phase", phase="Scanning selected files", message="Reading names and sizes.")
            items, total = prepared if prepared is not None else build_transfer_items(paths, self.cancel_event)
            if self.cancel_event.is_set():
                raise TransferCancelled("Transfer cancelled while scanning files.")
            if not items:
                raise RuntimeError("No transferable files were selected.")
            roots = sorted({PurePosixPath(item.relative).parts[0] for item in items}, key=str.casefold)
            manifest = hashlib.sha256(json.dumps([(i.relative, i.size, i.modified_ns) for i in items]).encode()).hexdigest()
            offer = {"magic": MAGIC, "type": "offer", "version": PROTOCOL_VERSION,
                     "transfer_id": transfer_id, "hostname": socket.gethostname(), "manifest": manifest,
                     "total_bytes": total, "file_count": len(items), "verify": verify, "wrap": wrap, "roots": roots}
            emit_transfer(self.events, transfer_id, "prepared", peer=peer_name, peer_ip=peer_ip,
                          total=total, file_count=len(items), verify=verify, wrap=wrap, roots=roots)
            emit_transfer(self.events, transfer_id, "phase", phase="Connecting", message=f"Connecting to {peer_name}.")
            retrying = False
            while True:
                if self.cancel_event.is_set():
                    raise TransferCancelled("Transfer cancelled by the sender.")
                try:
                    try:
                        channel = self._connect(peer_ip)
                    except OSError as exc:
                        raise TransferInterrupted(str(exc)) from exc
                    # Until acceptance, retry the same offer. An unreceived first offer is safe to repeat.
                    channel.send({**offer, "resume": bool(started)})
                    offered = True
                    responses = queue.Queue()
                    connection = channel

                    def read_responses(connection=connection, responses=responses):
                        try:
                            while True:
                                response = connection.receive()
                                responses.put(response)
                                if response.get("type") in ("cancel", "error", "reject", "done_ok"):
                                    if response.get("type") != "done_ok":
                                        connection.close()
                                    return
                        except Exception as exc:
                            responses.put(exc)
                            connection.close()

                    threading.Thread(target=read_responses, daemon=True, name="sender-response-monitor").start()

                    def response():
                        value = responses.get()
                        if isinstance(value, Exception):
                            raise value
                        kind = value.get("type")
                        if kind == "cancel":
                            raise TransferCancelled(str(value.get("reason") or "The receiver cancelled the transfer."))
                        if kind == "reject":
                            raise TransferRejected(str(value.get("reason") or "The receiver declined the transfer."))
                        if kind == "error":
                            raise RuntimeError(str(value.get("reason") or "The receiver could not save the transfer."))
                        return value

                    if not started:
                        emit_transfer(self.events, transfer_id, "phase", phase="Waiting for receiver",
                                      message="The receiver must choose a destination folder and accept.")
                    reply = response()
                    if reply.get("type") == "done_ok":
                        break
                    if reply.get("type") != "accept":
                        raise RuntimeError("The receiver returned an invalid response.")
                    index, offset = int(reply["index"]), int(reply["offset"])
                    sent_total = int(reply["done"])
                    if not 0 <= index <= len(items) or (index < len(items) and not 0 <= offset <= items[index].size):
                        raise ValueError("The receiver returned an invalid resume position.")
                    if retrying:
                        for item in items:
                            info = item.source.stat()
                            if (info.st_size, info.st_mtime_ns) != (item.size, item.modified_ns):
                                raise RuntimeError(f"Source file changed during interruption: {item.relative}. Send the transfer again.")
                    emit_transfer(self.events, transfer_id, "resumed" if started else "start", direction="Sending",
                                  peer=peer_name, peer_ip=peer_ip, total=total, file_count=len(items), verify=verify,
                                  destination=reply["destination"], done=sent_total, index=index,
                                  socket=socket_diagnostics(channel.sock), storage={
                                      "Receiver volume total": human_bytes(reply["disk_total"]),
                                      "Receiver volume free before transfer": human_bytes(reply["disk_free"]),
                                  })
                    if not started:
                        started = time.monotonic()
                    retrying = False
                    reusable = bytearray(BLOCK_SIZE)
                    view = memoryview(reusable)
                    for file_index in range(index, len(items)):
                        item = items[file_index]
                        info = item.source.stat()
                        if (info.st_size, info.st_mtime_ns) != (item.size, item.modified_ns):
                            raise RuntimeError(f"Source file changed: {item.relative}. Send the transfer again.")
                        emit_transfer(self.events, transfer_id, "file_start", index=file_index + 1,
                                      file_count=len(items), path=item.relative, source=str(item.source), size=item.size)
                        hasher = hashlib.sha256() if verify else None
                        with open(item.source, "rb", buffering=0) as source:
                            if offset and hasher:
                                emit_transfer(self.events, transfer_id, "phase", phase="Preparing to resume",
                                              message="Checking the saved portion of the current file.")
                                remaining = offset
                                while remaining:
                                    if self.cancel_event.is_set():
                                        raise TransferCancelled("Transfer cancelled by the sender.")
                                    n = source.readinto(view[:min(BLOCK_SIZE, remaining)])
                                    if not n:
                                        raise RuntimeError(f"Source file changed: {item.relative}")
                                    hasher.update(view[:n])
                                    remaining -= n
                                emit_transfer(self.events, transfer_id, "phase", phase="Transferring",
                                              message="Continuing from saved progress.")
                            else:
                                source.seek(offset)
                            with channel.send_lock:
                                channel.send_file_frame({"type": "file", "path": item.relative, "size": item.size, "offset": offset})
                                file_done, last_progress = offset, 0.0
                                while file_done < item.size:
                                    if self.cancel_event.is_set():
                                        raise TransferCancelled("Transfer cancelled by the sender.")
                                    n = source.readinto(view[:min(BLOCK_SIZE, item.size - file_done)])
                                    if not n:
                                        raise RuntimeError(f"Source file changed: {item.relative}")
                                    block = view[:n]
                                    if hasher:
                                        hasher.update(block)
                                    channel.send_bytes(block)
                                    file_done += n
                                    sent_total += n
                                    now = time.monotonic()
                                    if now - last_progress >= 0.10:
                                        emit_transfer(self.events, transfer_id, "progress", done=sent_total, total=total,
                                                      current_file_done=file_done, current_file_size=item.size, current=item.relative)
                                        last_progress = now
                                digest = hasher.hexdigest() if hasher else ""
                                if verify:
                                    channel.send_file_frame({"type": "hash", "sha256": digest})
                        info = item.source.stat()
                        if (info.st_size, info.st_mtime_ns) != (item.size, item.modified_ns):
                            raise RuntimeError(f"Source file changed: {item.relative}. Send the transfer again.")
                        if response().get("type") != "file_ok":
                            raise RuntimeError(f"Receiver did not confirm {item.relative}")
                        emit_transfer(self.events, transfer_id, "file_done", index=file_index + 1,
                                      path=item.relative, size=item.size, sha256=digest)
                        offset = 0
                    channel.send({"type": "done"})
                    if not wrap:
                        emit_transfer(self.events, transfer_id, "phase", phase="Waiting for receiver",
                                      message="The receiver is saving files. Resolve any Windows replace/skip prompts on that laptop.")
                    if response().get("type") != "done_ok":
                        raise RuntimeError("Receiver did not confirm transfer completion.")
                    break
                except TransferInterrupted:
                    if self.cancel_event.is_set():
                        raise TransferCancelled("Transfer cancelled by the sender.")
                    if not retrying:
                        emit_transfer(self.events, transfer_id, "paused", total=total,
                                      message="Connection interrupted. Waiting to reconnect — keep both apps open.")
                    retrying = True
                finally:
                    if channel:
                        channel.close()
                        channel = None
                self.cancel_event.wait(RECONNECT_DELAY)
            elapsed = max(time.monotonic() - (started or time.monotonic()), 0.001)
            emit_transfer(self.events, transfer_id, "done", done=total, average_bps=total / elapsed)
        except TransferRejected as exc:
            emit_transfer(self.events, transfer_id, "rejected", message=str(exc))
        except TransferCancelled as exc:
            if offered and self.cancel_event.is_set():
                try:
                    self._notify_stop(peer_ip, transfer_id, str(exc))
                except Exception as cleanup_error:
                    emit_transfer(self.events, transfer_id, "failed", message=str(cleanup_error))
                    return
            emit_transfer(self.events, transfer_id, "cancelled", message=str(exc))
        except Exception as exc:
            message = str(exc)
            if offered:
                try:
                    self._notify_stop(peer_ip, transfer_id, message, failed=True)
                except Exception as cleanup_error:
                    message = str(cleanup_error)
            emit_transfer(self.events, transfer_id, "failed", message=message, error_type=type(exc).__name__)
        finally:
            if channel:
                channel.close()
            with self.state_lock:
                self.active_socket = None
                self.active_transfer_id = None
            self.coordinator.release()
            emit_transfer(self.events, transfer_id, "worker_stopped")


class SenderGroup:
    def __init__(self, adapter, events, coordinator):
        self.adapter, self.events, self.coordinator = adapter, events, coordinator
        self.cancel_event = threading.Event()
        self.lock = threading.Lock()
        self.workers = {}
        self.cancelled = set()
        self.remaining = set()

    def send(self, peers, paths, verify, wrap=True):
        if not self.coordinator.acquire(blocking=False):
            return None
        recipients = {uuid.uuid4().hex: peer for peer in peers}
        with self.lock:
            self.cancel_event.clear()
            self.cancelled.clear()
            self.remaining = set(recipients)
            self.workers = {tid: Sender(self.adapter, self.events, threading.Lock()) for tid in recipients}
        threading.Thread(target=self._prepare, args=(recipients, list(paths), verify, wrap), daemon=True).start()
        return recipients

    def _prepare(self, recipients, paths, verify, wrap):
        try:
            prepared = build_transfer_items(paths, self.cancel_event)
            if not prepared[0]:
                raise RuntimeError("No transferable files were selected.")
        except Exception as exc:
            for tid in recipients:
                emit_transfer(self.events, tid, "cancelled" if self.cancel_event.is_set() else "failed", message=str(exc))
                emit_transfer(self.events, tid, "worker_stopped")
            return
        for tid, peer in recipients.items():
            with self.lock:
                worker = self.workers[tid]
                cancelled = tid in self.cancelled or self.cancel_event.is_set()
                if not cancelled:
                    worker.coordinator.acquire()
                    worker.active_transfer_id = tid
            if cancelled:
                emit_transfer(self.events, tid, "cancelled", message="Transfer cancelled before connecting.")
                emit_transfer(self.events, tid, "worker_stopped")
            else:
                threading.Thread(target=worker._send_worker,
                    args=(tid, peer["ip"], peer["name"], paths, verify, prepared, wrap), daemon=True).start()

    def cancel(self, transfer_id=None):
        with self.lock:
            ids = [transfer_id] if transfer_id else list(self.workers)
            if transfer_id is None:
                self.cancel_event.set()
            for tid in ids:
                self.cancelled.add(tid)
                worker = self.workers.get(tid)
                if worker:
                    worker.cancel()

    def worker_stopped(self, transfer_id):
        with self.lock:
            if transfer_id not in self.remaining:
                return False
            self.remaining.remove(transfer_id)
            if self.remaining:
                return False
            self.coordinator.release()
            return True


def human_bytes(value: float) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    value = float(value)
    for unit in units:
        if abs(value) < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def human_duration(seconds: float | None) -> str:
    if seconds is None or seconds < 0:
        return "Unknown"
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {secs:02d}s"
    if minutes:
        return f"{minutes}m {secs:02d}s"
    return f"{secs}s"


def set_system_awake(required: bool) -> tuple[bool, str]:
    if platform.system() != "Windows":
        return False, "Unavailable on this operating system"
    flags = ES_CONTINUOUS | ES_SYSTEM_REQUIRED if required else ES_CONTINUOUS
    try:
        result = ctypes.windll.kernel32.SetThreadExecutionState(flags)
    except Exception as exc:
        return False, f"Unavailable: {exc}"
    if not result:
        return False, "Windows rejected the keep-awake request"
    if required:
        return True, "Active — automatic system sleep is blocked during the transfer"
    return True, "Released"


class TransferView(tk.Frame):
    def __init__(
        self,
        parent: tk.Tk,
        transfer_id: str,
        direction: str,
        adapter: EthernetAdapter,
        cancel_callback,
        close_callback,
        peer: str = "Unknown",
        peer_ip: str = "Unknown",
        verify: bool = False,
        sources: list[Path] | None = None,
    ):
        super().__init__(parent)
        self.adapter_for_badge = adapter
        self.parent = parent
        self.transfer_id = transfer_id
        self.cancel_callback = cancel_callback
        self.close_callback = close_callback
        self.finished = False
        self.cancel_requested = False
        self.created_monotonic = time.monotonic()
        self.transfer_started_monotonic: float | None = None
        self.last_progress_monotonic: float | None = None
        self.last_progress_bytes = 0
        self.last_activity_monotonic = self.created_monotonic
        self.instant_bps = 0.0
        self.peak_bps = 0.0
        self.details: dict[str, str] = {}
        self.detail_items: dict[str, str] = {}
        self.log_entries: list[str] = []
        self.accept_button: ttk.Button | None = None

        self.monitor_dpi, self.ui_scale = parent.monitor_dpi, parent.ui_scale
        self.configure(background=COLOR_BG)

        self.phase_var = tk.StringVar(value="Preparing")
        self.message_var = tk.StringVar(value="Preparing your transfer…")
        self.percent_var = tk.StringVar(value="0.0%")
        self.transferred_var = tk.StringVar(value="0 B")
        self.rate_var = tk.StringVar(value="Waiting")
        self.eta_var = tk.StringVar(value="Unknown")
        self.elapsed_var = tk.StringVar(value="0s")

        self.peer_display_var = tk.StringVar(value=peer)
        self.contents_var = tk.StringVar(value="Preparing files…")
        self.current_file_var = tk.StringVar(value="")
        self.destination_var = tk.StringVar(value="")
        self._build_ui(direction)
        self.set_details(
            {
                "Transfer ID": transfer_id,
                "Direction": direction,
                "State": "Preparing",
                "Phase": "Preparing",
                "Protocol": f"{MAGIC} / version {PROTOCOL_VERSION}",
                "App session ID": SESSION_ID,
                "Transfer view opened": datetime.now().astimezone().isoformat(timespec="seconds"),
                "Process ID": str(os.getpid()),
                "Executable": sys.executable,
                "Application path": str(Path(__file__).resolve()),
                "Python runtime": sys.version.replace("\n", " "),
                "Operating system": platform.platform(),
                "Architecture": platform.machine(),
                "DPI awareness": DPI_AWARENESS_MODE,
                "Monitor DPI": f"{self.monitor_dpi} DPI ({self.ui_scale * 100:.0f}% scale)",
                "Tk text scaling": f"{float(self.tk.call('tk', 'scaling')):.4f}",
                "Worker model": "Background network/file thread with Tk UI event queue",
                "Local computer": socket.gethostname(),
                "Peer computer": peer,
                "Peer address": peer_ip,
                "Transport": "TCP over local Wi-Fi / IPv4" if isinstance(adapter, WifiAdapter) else "TCP over IPv6 link-local / direct physical Ethernet",
                "Adapter": adapter.name,
                "Interface index": str(adapter.if_index),
                "Local address": adapter.address if isinstance(adapter, WifiAdapter) else f"{adapter.link_local}%{adapter.if_index}",
                "Adapter MAC": adapter.mac or "Unavailable",
                "Negotiated link speed": adapter.link_speed or "Unavailable",
                "Receive link capacity": f"{human_bytes(adapter.rx_bps / 8)}/s ({adapter.rx_bps} bit/s)",
                "Transmit link capacity": f"{human_bytes(adapter.tx_bps / 8)}/s ({adapter.tx_bps} bit/s)",
                "Default gateway": "Present" if adapter.has_gateway else "None (direct-link requirement met)",
                "Discovery endpoint": f"{adapter.network.broadcast_address}:{DISCOVERY_PORT}/UDP" if isinstance(adapter, WifiAdapter) else f"[{DISCOVERY_GROUP}%{adapter.if_index}]:{DISCOVERY_PORT}/UDP",
                "Transfer port": f"{TRANSFER_PORT}/TCP",
                "Application block size": f"{human_bytes(BLOCK_SIZE)} ({BLOCK_SIZE} bytes)",
                "Requested socket buffer": "Automatic (managed by Windows)" if isinstance(adapter, WifiAdapter) else f"{human_bytes(SOCKET_BUFFER)} ({SOCKET_BUFFER} bytes)",
                "Integrity verification": "SHA-256 enabled" if verify else "Disabled",
                "Selected source paths": " | ".join(str(path) for path in (sources or [])) or "Supplied by sender",
                "Power behavior": "Automatic system sleep blocked; display sleep is allowed",
                "Minimized behavior": "Transfer threads continue while the window is minimized",
                "Actual sleep/hibernation": "Networking pauses; the transfer resumes only if Windows preserves the TCP connection",
                "Cancellation behavior": "Immediately closes the active transfer socket",
            }
        )
        self.add_log(f"Transfer view opened for {direction.lower()} transfer {transfer_id}.")
        self.winfo_toplevel().after(250, self._tick)

    def _build_ui(self, direction: str) -> None:
        outer = ttk.Frame(self, style="App.TFrame", padding=(32, 22))
        outer.pack(fill="both", expand=True)
        heading = ttk.Frame(outer, style="App.TFrame")
        heading.pack(fill="x", pady=(0, 16))
        ttk.Label(heading, text="Send files" if direction == "Sending" else "Receive files", style="Title.TLabel").pack(side="left")
        mode_badge(heading, "wifi" if isinstance(self.adapter_for_badge, WifiAdapter) else "ethernet").pack(side="right")
        navigation = ttk.Frame(outer, style="App.TFrame")
        navigation.pack(fill="x", pady=(0, 18))
        self.overview_button = ttk.Button(navigation, text="Overview", command=lambda: self._show_transfer_page(False), style="SelectedSegment.TButton")
        self.overview_button.pack(side="left")
        self.details_button = ttk.Button(navigation, text="Details", command=lambda: self._show_transfer_page(True), style="Segment.TButton")
        self.details_button.pack(side="left", padx=(4, 0))
        self.page_container = ttk.Frame(outer, style="App.TFrame")
        self.page_container.pack(fill="both", expand=True)
        self.overview = ttk.Frame(self.page_container, style="App.TFrame")
        self.overview.pack(fill="both", expand=True)
        self.phase_label = ttk.Label(self.overview, textvariable=self.phase_var, style="Phase.TLabel")
        self.phase_label.pack(anchor="w", pady=(6, 8))
        ttk.Label(self.overview, textvariable=self.peer_display_var, style="Hero.TLabel").pack(anchor="w")
        ttk.Label(self.overview, textvariable=self.contents_var, style="Subtitle.TLabel", wraplength=750).pack(anchor="w", pady=(8, 0))
        ttk.Label(self.overview, textvariable=self.message_var, style="Subtitle.TLabel", wraplength=750).pack(anchor="w", pady=(14, 20))
        self.progress_area = ttk.Frame(self.overview, style="App.TFrame")
        self.progress = ttk.Progressbar(self.progress_area, maximum=100, style="Modern.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(4, 8))
        progress_line = ttk.Frame(self.progress_area, style="App.TFrame")
        progress_line.pack(fill="x")
        ttk.Label(progress_line, textvariable=self.transferred_var, style="Subtitle.TLabel").pack(side="left")
        ttk.Label(progress_line, textvariable=self.percent_var, style="Subtitle.TLabel").pack(side="right")
        metrics = RoundedCard(self.overview, height=95)
        self.metrics_card = metrics
        for column, (label, variable) in enumerate((("Speed", self.rate_var), ("Time remaining", self.eta_var), ("Elapsed", self.elapsed_var))):
            box = ttk.Frame(metrics.body, style="Card.TFrame")
            box.grid(row=0, column=column, sticky="w")
            ttk.Label(box, text=label, style="MetricLabel.TLabel").pack(anchor="w")
            ttk.Label(box, textvariable=variable, style="MetricValue.TLabel").pack(anchor="w", pady=(4, 0))
            metrics.body.columnconfigure(column, weight=1)

        self.diagnostics = ttk.Frame(self.page_container, style="App.TFrame")
        diagnostic_nav = ttk.Frame(self.diagnostics, style="App.TFrame")
        diagnostic_nav.pack(fill="x", pady=(0, 12))
        self.fields_button = ttk.Button(diagnostic_nav, text="All diagnostics", style="Selected.Ghost.TButton", command=lambda: self._show_diagnostic_log(False))
        self.fields_button.pack(side="left")
        self.log_button = ttk.Button(diagnostic_nav, text="Activity log", style="Ghost.TButton", command=lambda: self._show_diagnostic_log(True))
        self.log_button.pack(side="left", padx=(8, 0))
        ttk.Button(diagnostic_nav, text="Copy diagnostics", command=self.copy_diagnostics, style="Ghost.TButton").pack(side="right")
        details_tab = ttk.Frame(self.diagnostics, style="Card.TFrame", padding=8)
        log_tab = ttk.Frame(self.diagnostics, style="Card.TFrame", padding=8)
        self.fields_page, self.log_page = details_tab, log_tab
        details_tab.pack(fill="both", expand=True)
        self.detail_tree = ttk.Treeview(details_tab, columns=("value",), show="tree headings", selectmode="browse", height=8)
        self.detail_tree.heading("#0", text="Field")
        self.detail_tree.heading("value", text="Value")
        self.detail_tree.column("#0", width=230, minwidth=160, stretch=False)
        self.detail_tree.column("value", width=500, minwidth=200, stretch=True)
        scroll = ttk.Scrollbar(details_tab, orient="vertical", command=self.detail_tree.yview)
        horizontal = ttk.Scrollbar(details_tab, orient="horizontal", command=self.detail_tree.xview)
        self.detail_tree.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        horizontal.pack(side="bottom", fill="x")
        scroll.pack(side="right", fill="y")
        self.detail_tree.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_tab, wrap="word", state="disabled", height=8, font=("Consolas", 10),
            bg=COLOR_SURFACE, fg=COLOR_TEXT, selectbackground=COLOR_SURFACE_ALT,
            relief="flat", borderwidth=0, padx=12, pady=12)
        log_scroll = ttk.Scrollbar(log_tab, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log_text.pack(fill="both", expand=True)
        self.actions = ttk.Frame(outer, style="App.TFrame")
        self.actions.pack(fill="x", pady=(18, 0))
        self.action_button = ttk.Button(self.actions, text="Cancel transfer", command=self._cancel_or_close, style="Danger.TButton")
        self.action_button.pack(side="right")

    def _show_transfer_page(self, details):
        show_view(self.diagnostics if details else self.overview,
                  self.overview if details else self.diagnostics)
        self.overview_button.configure(style="Segment.TButton" if details else "SelectedSegment.TButton")
        self.details_button.configure(style="SelectedSegment.TButton" if details else "Segment.TButton")

    def _show_diagnostic_log(self, log):
        show_view(self.log_page if log else self.fields_page,
                  self.fields_page if log else self.log_page)
        self.fields_button.configure(style="Ghost.TButton" if log else "Selected.Ghost.TButton")
        self.log_button.configure(style="Selected.Ghost.TButton" if log else "Ghost.TButton")

    def _show_progress(self):
        if not self.progress_area.winfo_manager():
            self.progress_area.pack(fill="x")
            self.metrics_card.pack(fill="x", pady=(22, 16))

    def offer_destination_choice(self, callback) -> None:
        if self.accept_button:
            return

        def choose() -> None:
            if self.finished or self.cancel_requested:
                return
            self.accept_button.config(state="disabled")
            callback()

        self.action_button.configure(text="Decline")
        self.accept_button = ttk.Button(
            self.actions,
            text="Choose destination & accept",
            command=choose,
            style="Cyan.TButton",
        )
        self.accept_button.pack(side="right", padx=(0, 8))

    def set_detail(self, name: str, value) -> None:
        text_value = str(value)
        self.details[name] = text_value
        if name == "Peer computer":
            self.peer_display_var.set(text_value)
        elif name in ("Top-level items", "File count", "Total bytes"):
            items = self.details.get("Top-level items", "")
            count = self.details.get("File count", "?")
            size = self.details.get("Total bytes", "").split(" (")[0]
            self.contents_var.set(f"{count} files · {size}" + (f"\n{items}" if items else ""))
        elif name == "Current relative path":
            self.current_file_var.set(text_value)
        elif name in ("Receiver destination", "Chosen destination parent", "Partial data location"):
            if text_value != "Unknown":
                label = "Partial files" if name == "Partial data location" else "Save to"
                self.destination_var.set(f"{label}: {text_value}")
        item = self.detail_items.get(name)
        if item:
            self.detail_tree.item(item, values=(text_value,))
        else:
            self.detail_items[name] = self.detail_tree.insert("", "end", text=name, values=(text_value,))

    def set_details(self, values: dict) -> None:
        for name, value in values.items():
            self.set_detail(name, value)

    def add_log(self, message: str) -> None:
        stamp = datetime.now().astimezone().isoformat(timespec="milliseconds")
        entry = f"{stamp}  {message}"
        self.log_entries.append(entry)
        self.log_text.config(state="normal")
        self.log_text.insert("end", entry + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")
        self.last_activity_monotonic = time.monotonic()
        self.set_detail("Last activity", stamp)

    def set_phase(self, phase: str, message: str = "") -> None:
        self.phase_var.set(phase)
        phase_lower = phase.lower()
        if phase_lower in ("cancelling", "declining"):
            self.phase_label.config(style="WarningPhase.TLabel")
        elif phase_lower in ("failed", "cancelled", "declined"):
            self.phase_label.config(style="DangerPhase.TLabel")
        else:
            self.phase_label.config(style="Phase.TLabel")
        self.set_detail("Phase", phase)
        if message:
            self.message_var.set(message)
            self.add_log(message)

    def apply_event(self, action: str, data: dict) -> None:
        if action == "phase":
            self.set_phase(str(data.get("phase") or "Working"), str(data.get("message") or ""))

        elif action == "paused":
            self.instant_bps = 0.0
            self.last_progress_monotonic = None
            self.rate_var.set("Waiting")
            self.eta_var.set("Waiting")
            self.set_detail("State", "Waiting to reconnect")
            self.set_phase("Connection interrupted", str(data.get("message") or "Waiting to reconnect — keep both apps open."))

        elif action == "resumed":
            self.instant_bps = 0.0
            self.last_progress_monotonic = None
            self.set_details(data.get("socket", {}))
            self.set_detail("Files completed", data.get("index", 0))
            self.set_detail("State", "Transferring")
            self._apply_progress(data)
            self.set_phase("Transferring", "Connection restored. Continuing from saved progress.")

        elif action == "prepared":
            self.set_details(
                {
                    "Peer computer": data.get("peer", "Unknown"),
                    "Peer address": data.get("peer_ip", "Unknown"),
                    "Top-level items": " | ".join(data.get("roots", [])) or "None",
                    "File count": data.get("file_count", 0),
                    "Total bytes": f"{human_bytes(data.get('total', 0))} ({data.get('total', 0)} bytes)",
                    "Integrity verification": "SHA-256 enabled" if data.get("verify") else "Disabled",
                }
            )
            self.add_log(f"Scan complete: {data.get('file_count', 0)} files, {human_bytes(data.get('total', 0))}.")

        elif action == "connected":
            self.set_details(data.get("socket", {}))
            self.set_detail("Connection established", datetime.now().astimezone().isoformat(timespec="seconds"))
            self.add_log("Direct TCP connection established.")

        elif action == "start":
            self._show_progress()
            if self.accept_button:
                self.accept_button.pack_forget()
            self.action_button.configure(text="Cancel transfer")
            self.transfer_started_monotonic = time.monotonic()
            self.last_progress_monotonic = None
            self.set_details(
                {
                    "State": "Transferring",
                    "Peer computer": data.get("peer", "Unknown"),
                    "Peer address": data.get("peer_ip", "Unknown"),
                    "File count": data.get("file_count", 0),
                    "Total bytes": f"{human_bytes(data.get('total', 0))} ({data.get('total', 0)} bytes)",
                    "Integrity verification": "SHA-256 enabled" if data.get("verify") else "Disabled",
                    "Receiver destination": data.get("destination", "Unknown"),
                    "Transfer started": datetime.now().astimezone().isoformat(timespec="seconds"),
                    **data.get("socket", {}),
                    **data.get("storage", {}),
                }
            )
            self.set_phase("Transferring", "Both laptops accepted the transfer and are synchronized.")

        elif action == "file_start":
            self.set_details(
                {
                    "Current file number": f"{data.get('index', 0)} of {data.get('file_count', self.details.get('File count', '?'))}",
                    "Current relative path": data.get("path", ""),
                    "Current file size": f"{human_bytes(data.get('size', 0))} ({data.get('size', 0)} bytes)",
                    "Current source": data.get("source", "Supplied by sender"),
                    "Current destination": data.get("destination", self.details.get("Receiver destination", "Unknown")),
                }
            )
            self.add_log(
                f"File {data.get('index', 0)} started: {data.get('path', '')} ({human_bytes(data.get('size', 0))})."
            )

        elif action == "progress":
            self._apply_progress(data)

        elif action == "file_done":
            self.set_detail("Files completed", data.get("index", 0))
            digest = str(data.get("sha256") or "")
            if digest:
                self.set_detail("Latest verified SHA-256", digest)
                self.set_detail("Files SHA-256 verified", data.get("index", 0))
                self.add_log(f"File verified and confirmed: {data.get('path', '')} — SHA-256 {digest}")
            else:
                self.add_log(f"File confirmed: {data.get('path', '')}")

        elif action == "done":
            self.progress["value"] = 100
            self.percent_var.set("100.0%")
            self.rate_var.set(f"{human_bytes(data.get('average_bps', 0))}/s")
            self.set_detail("Average speed", f"{human_bytes(data.get('average_bps', 0))}/s")
            if data.get("destination"):
                self.set_detail("Receiver destination", data["destination"])
            self._finish("Completed", "Transfer completed and was confirmed by both laptops.")

        elif action == "rejected":
            self._finish("Declined", str(data.get("message") or "Transfer declined."))

        elif action == "cancelled":
            if data.get("cleanup"):
                self.set_detail("Cancellation cleanup", data["cleanup"])
                self.destination_var.set(data["cleanup"])
                self.add_log(data["cleanup"])
            elif data.get("destination"):
                self.set_detail("Partial data location", data["destination"])
            self._finish("Cancelled", str(data.get("message") or "Transfer cancelled."))

        elif action == "failed":
            if data.get("cleanup"):
                self.set_detail("Cancellation cleanup", data["cleanup"])
            if data.get("error_type"):
                self.set_detail("Error type", data["error_type"])
            if data.get("destination"):
                self.set_detail("Partial data location", data["destination"])
            self._finish("Failed", str(data.get("message") or "Transfer failed."))

    def _apply_progress(self, data: dict) -> None:
        self._show_progress()
        now = time.monotonic()
        done = int(data.get("done") or 0)
        total = int(data.get("total") or 0)
        if self.last_progress_monotonic is not None:
            delta_time = max(now - self.last_progress_monotonic, 0.001)
            self.instant_bps = max(0.0, (done - self.last_progress_bytes) / delta_time)
            self.peak_bps = max(self.peak_bps, self.instant_bps)
        self.last_progress_monotonic = now
        self.last_progress_bytes = done
        self.last_activity_monotonic = now

        percent = done / total * 100 if total else 100.0
        remaining = max(total - done, 0)
        elapsed = max(now - (self.transfer_started_monotonic or self.created_monotonic), 0.001)
        average_bps = done / elapsed
        eta = remaining / average_bps if average_bps > 0 else None
        file_done = int(data.get("current_file_done") or 0)
        file_size = int(data.get("current_file_size") or 0)
        file_percent = file_done / file_size * 100 if file_size else 100.0

        self.progress["value"] = percent
        self.percent_var.set(f"{percent:.1f}%")
        self.transferred_var.set(f"{human_bytes(done)} / {human_bytes(total)}")
        self.rate_var.set(f"{human_bytes(self.instant_bps)}/s")
        self.eta_var.set(human_duration(eta))
        self.set_details(
            {
                "Overall progress": f"{percent:.2f}%",
                "Bytes transferred": f"{human_bytes(done)} ({done} bytes)",
                "Bytes remaining": f"{human_bytes(remaining)} ({remaining} bytes)",
                "Current speed": f"{human_bytes(self.instant_bps)}/s ({self.instant_bps:.0f} bytes/s)",
                "Average speed": f"{human_bytes(average_bps)}/s ({average_bps:.0f} bytes/s)",
                "Peak observed speed": f"{human_bytes(self.peak_bps)}/s ({self.peak_bps:.0f} bytes/s)",
                "Estimated time remaining": human_duration(eta),
                "Current relative path": data.get("current", ""),
                "Current file progress": f"{file_percent:.2f}% — {human_bytes(file_done)} of {human_bytes(file_size)}",
            }
        )

    def _finish(self, state: str, message: str) -> None:
        if self.finished:
            return
        self.finished = True
        self.phase_var.set(state)
        self.message_var.set(message)
        if state == "Completed":
            self.phase_label.config(style="SuccessPhase.TLabel")
        elif state in ("Cancelled", "Declined", "Failed"):
            self.phase_label.config(style="DangerPhase.TLabel")
        else:
            self.phase_label.config(style="WarningPhase.TLabel")
        self.set_details(
            {
                "State": state,
                "Phase": state,
                "Finished": datetime.now().astimezone().isoformat(timespec="seconds"),
            }
        )
        self.add_log(message)
        if self.accept_button:
            self.accept_button.config(state="disabled")
        group_panel = self.close_callback is None
        self.action_button.config(text="Finished" if group_panel else "Done",
                                  state="disabled" if group_panel else "normal", style="Accent.TButton")
        if self.accept_button:
            self.accept_button.pack_forget()

    def _tick(self) -> None:
        if not self.winfo_exists() or self.finished:
            return
        start = self.transfer_started_monotonic or self.created_monotonic
        elapsed = time.monotonic() - start
        self.elapsed_var.set(human_duration(elapsed))
        self.set_detail("Elapsed time", human_duration(elapsed))
        self.set_detail("Seconds since last activity", f"{max(time.monotonic() - self.last_activity_monotonic, 0):.1f}")
        self.winfo_toplevel().after(250, self._tick)

    def _cancel_or_close(self) -> None:
        if self.finished:
            self._close()
            return
        if self.cancel_requested:
            return
        self.cancel_requested = True
        self.set_detail("Cancellation requested", datetime.now().astimezone().isoformat(timespec="seconds"))
        self.set_phase("Cancelling", "Stopping disk and network activity…")
        if self.accept_button:
            self.accept_button.config(state="disabled")
        self.action_button.config(text="Cancelling…", state="disabled")
        self.cancel_callback()

    def copy_diagnostics(self) -> None:
        lines = [f"{APP_NAME} transfer diagnostics", "", "DETAILS"]
        lines.extend(f"{name}: {value}" for name, value in self.details.items())
        lines.extend(("", "ACTIVITY LOG", *self.log_entries))
        self.clipboard_clear()
        self.clipboard_append("\n".join(lines))
        self.update()

    def _close(self) -> None:
        self.close_callback(self)


class TransferPanel(TransferView):
    pass


class GroupTransferDialog(tk.Frame):
    def __init__(self, parent, recipients, paths, verify):
        super().__init__(parent, bg=COLOR_BG)
        self.parent = parent
        self.transfer_id = "group"
        self.finished = False
        self.panels = {}
        self.rows = {}
        self.monitor_dpi, self.ui_scale = parent.monitor_dpi, parent.ui_scale
        top = ttk.Frame(self, style="App.TFrame", padding=(32, 16))
        top.pack(fill="x")
        ttk.Label(top, text=f"{len(recipients)} receivers", style="Subtitle.TLabel").pack(side="left")
        self.action_button = ttk.Button(top, text="Cancel all", style="Danger.TButton", command=self._cancel_or_close)
        self.action_button.pack(side="right")
        receivers = ttk.Frame(self, style="Card.TFrame")
        receivers.pack(fill="x", padx=32)
        self.summary = ttk.Treeview(receivers, columns=("status", "progress", "speed"), show="tree headings", height=min(len(recipients), 3))
        for name, title in (("#0", "Receiver"), ("status", "Status"), ("progress", "Progress"), ("speed", "Speed")):
            self.summary.heading(name, text=title)
            self.summary.column(name, width=165, minwidth=100)
        scroll = ttk.Scrollbar(receivers, orient="vertical", command=self.summary.yview)
        self.summary.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.summary.pack(fill="both", expand=True)
        self.container = tk.Frame(self, bg=COLOR_BG)
        self.container.pack(fill="both", expand=True)
        self.container.monitor_dpi, self.container.ui_scale = self.monitor_dpi, self.ui_scale
        for tid, peer in recipients.items():
            self.summary.insert("", "end", iid=tid, text=peer["name"], values=("Preparing", "0%", "Waiting"))
            self.rows[tid] = ["Preparing", "0%", "Waiting"]
            self.panels[tid] = TransferPanel(self.container, tid, "Sending", parent.adapter,
                lambda tid=tid: parent.sender.cancel(tid), None,
                peer=peer["name"], peer_ip=peer["ip"], verify=verify, sources=paths)
        self.summary.bind("<<TreeviewSelect>>", self._select)
        self.summary.selection_set(next(iter(recipients)))
        self._select()

    def _select(self, event=None):
        finish_motion(self.container)
        begin_motion(self.container)
        for panel in self.panels.values():
            panel.pack_forget()
        selected = self.summary.selection()
        if selected:
            show_view(self.panels[selected[0]])

    def apply_transfer(self, tid, action, data):
        panel = self.panels.get(tid)
        if not panel:
            return
        panel.apply_event(action, data)
        row = self.rows[tid]
        if action in ("phase", "start", "prepared", "paused", "resumed", "done", "failed", "rejected", "cancelled"):
            row[0] = data.get("phase") or {"done": "Completed", "rejected": "Declined", "failed": "Failed",
                "cancelled": "Cancelled", "prepared": "Prepared", "start": "Transferring",
                "paused": "Waiting to reconnect", "resumed": "Transferring"}.get(action, action)
        if action in ("progress", "paused", "resumed"):
            row[1], row[2] = panel.percent_var.get(), panel.rate_var.get()
        if action == "done":
            row[1] = "100%"
        self.summary.item(tid, values=row)

    def complete(self):
        self.finished = True
        self.action_button.configure(text="Done", style="Accent.TButton", state="normal")

    def set_detail(self, name, value):
        for panel in self.panels.values():
            panel.set_detail(name, value)

    def add_log(self, message):
        for panel in self.panels.values():
            panel.add_log(message)

    def _cancel_or_close(self):
        if self.finished:
            self.parent._transfer_dialog_closed(self)
        else:
            self.parent.sender.cancel()
            self.action_button.configure(text="Cancelling…", state="disabled")

class WindowsFileDrop:
    class Point(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class Format(ctypes.Structure):
        _fields_ = [("format", ctypes.c_ushort), ("device", ctypes.c_void_p),
                    ("aspect", ctypes.c_uint), ("index", ctypes.c_long), ("medium", ctypes.c_uint)]

    class Medium(ctypes.Structure):
        _fields_ = [("type", ctypes.c_uint), ("handle", ctypes.c_void_p), ("release", ctypes.c_void_p)]

    def __init__(self, widget: tk.Widget, events: queue.Queue):
        self.widget = widget
        self.events = events
        self.handle = widget.winfo_id()
        self.enabled = False
        self.accept_files = False
        self.references = 1
        self.shell32 = ctypes.windll.shell32
        self.ole32 = ctypes.windll.ole32
        self.user32 = ctypes.windll.user32
        pointer, word = ctypes.c_void_p, ctypes.c_uint
        effect = ctypes.POINTER(word)
        self.user32.GetAncestor.argtypes, self.user32.GetAncestor.restype = [pointer, word], pointer
        self.user32.GetWindowRect.argtypes = [pointer, pointer]
        self.window_handle = self.user32.GetAncestor(self.handle, 2)
        self.shell32.DragQueryFileW.argtypes = [pointer, word, ctypes.c_wchar_p, word]
        self.shell32.DragQueryFileW.restype = word
        self.ole32.OleInitialize.argtypes = [pointer]
        self.ole32.RegisterDragDrop.argtypes = [pointer, pointer]
        self.ole32.RevokeDragDrop.argtypes = [pointer]
        self.ole32.ReleaseStgMedium.argtypes = [pointer]
        self.file_format = self.Format(15, None, 1, -1, 1)  # CF_HDROP, DVASPECT_CONTENT, TYMED_HGLOBAL
        methods = [
            (ctypes.c_long, (pointer, pointer, ctypes.POINTER(pointer)), self._query_interface),
            (word, (pointer,), self._add_ref),
            (word, (pointer,), self._release),
            (ctypes.c_long, (pointer, pointer, word, self.Point, effect), self._drag_enter),
            (ctypes.c_long, (pointer, word, self.Point, effect), self._drag_over),
            (ctypes.c_long, (pointer,), self._drag_leave),
            (ctypes.c_long, (pointer, pointer, word, self.Point, effect), self._drop),
        ]
        # Windows calls these while Tcl is waiting for messages: only native APIs and the queue are used.
        self.callbacks = [ctypes.WINFUNCTYPE(result, *args)(method) for result, args, method in methods]
        self.table = (pointer * len(self.callbacks))(*(ctypes.cast(method, pointer) for method in self.callbacks))
        self.object = (pointer * 1)(ctypes.cast(self.table, pointer))
        self.interface = ctypes.cast(self.object, pointer)
        result = self.ole32.OleInitialize(None)
        if result < 0:
            raise ctypes.WinError(result)
        # Explorer targets the actual top-level window; the drop effect restricts it to the list.
        result = self.ole32.RegisterDragDrop(self.window_handle, self.interface)
        if result < 0:
            self.ole32.OleUninitialize()
            raise ctypes.WinError(result)
        widget.bind("<Map>", lambda event: self._enable(True), add="+")
        widget.bind("<Unmap>", lambda event: self._enable(False), add="+")
        widget.bind("<Destroy>", self._destroy, add="+")

    def _enable(self, enabled):
        self.enabled = enabled

    def _query_interface(self, this, iid, output):
        if ctypes.string_at(iid, 16) not in (
                uuid.UUID("00000000-0000-0000-c000-000000000046").bytes_le,
                uuid.UUID("00000122-0000-0000-c000-000000000046").bytes_le):
            output[0] = None
            return -2147467262  # E_NOINTERFACE
        output[0] = this
        self._add_ref(this)
        return 0

    def _add_ref(self, this):
        self.references += 1
        return self.references

    def _release(self, this):
        self.references -= 1
        return self.references

    def _data_call(self, data, index, *args):
        pointer = ctypes.c_void_p
        table = ctypes.cast(data, ctypes.POINTER(ctypes.POINTER(pointer))).contents
        method = ctypes.WINFUNCTYPE(ctypes.c_long, pointer, *([pointer] * len(args)))(table[index])
        return method(data, *args)

    def _set_effect(self, point, effect):
        rect = (ctypes.c_long * 4)()
        allowed = (self.enabled and self.accept_files
                   and self.user32.GetWindowRect(self.handle, rect)
                   and rect[0] <= point.x < rect[2] and rect[1] <= point.y < rect[3])
        effect[0] = effect[0] & 1 if allowed else 0  # DROPEFFECT_COPY; never move source files.

    def _drag_enter(self, this, data, keys, point, effect):
        self.accept_files = self._data_call(data, 5, ctypes.byref(self.file_format)) == 0
        self._set_effect(point, effect)
        return 0

    def _drag_over(self, this, keys, point, effect):
        self._set_effect(point, effect)
        return 0

    def _drag_leave(self, this):
        self.accept_files = False
        return 0

    def _drop(self, this, data, keys, point, effect):
        self._set_effect(point, effect)
        if effect[0]:
            medium = self.Medium()
            result = self._data_call(data, 3, ctypes.byref(self.file_format), ctypes.byref(medium))
            if result < 0:
                effect[0] = 0
                return result
            try:
                paths = []
                count = self.shell32.DragQueryFileW(medium.handle, 0xFFFFFFFF, None, 0)
                for index in range(count):
                    size = self.shell32.DragQueryFileW(medium.handle, index, None, 0) + 1
                    name = ctypes.create_unicode_buffer(size)
                    self.shell32.DragQueryFileW(medium.handle, index, name, size)
                    paths.append(name.value)
                self.events.put(("files_dropped", self.widget, paths))
            finally:
                self.ole32.ReleaseStgMedium(ctypes.byref(medium))
        self.accept_files = False
        return 0

    def _destroy(self, event):
        self._enable(False)
        self.ole32.RevokeDragDrop(self.window_handle)
        self.ole32.OleUninitialize()


class EtherDropApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.monitor_dpi, self.ui_scale = configure_tk_dpi(self)
        assets = Path(__file__).resolve().parent / "assets"
        self.iconbitmap(default=str(assets / "etherdrop.ico"))
        configure_modern_theme(self)
        self.title(APP_NAME)
        set_scaled_window_geometry(self, 880, 820, 820, 820, self.ui_scale)
        self.motion_callback = None
        self.motion_parent = None
        self.motion_prepared = False

        self.events: queue.Queue = queue.Queue()
        self.coordinator = threading.Lock()
        self.close_after_transfer = False
        self.mode = "ethernet"
        self.wifi_peers = {}
        self.role: str | None = None
        self.adapter: EthernetAdapter | None = None
        self.discovery: DiscoveryService | None = None
        self.receiver: ReceiverService | None = None
        self.sender: Sender | None = None

        self.peer_ip: str | None = None
        self.peer_name: str | None = None
        self.peer_role: str | None = None
        self.peer_last_seen = 0.0
        self.selected_paths: list[Path] = []
        self.last_destination = Path.home() / "Downloads"
        self.transfer_dialog: TransferView | GroupTransferDialog | None = None
        self.active_transfer_id: str | None = None
        self.keep_awake_active = False
        self.scan_token = 0
        self.listbox: tk.Listbox | None = None
        self.send_button: ttk.Button | None = None
        self.progress: ttk.Progressbar | None = None
        self.link_label: ttk.Label | None = None
        self.setup_button: ttk.Button | None = None
        self.setup_dialog: tk.Frame | None = None
        self.setup_in_progress = False
        self.update_busy = False
        self._closing = False
        self.update_installing = False
        self.update_button: ttk.Button | None = None
        self.update_dialog: tk.Frame | None = None
        self.release_notes_dialog: tk.Frame | None = None
        self.update_state = load_update_state()
        self.update_var = tk.StringVar(value="Check for updates")
        self.update_progress_var = tk.DoubleVar(value=0)

        self.screen = None
        self.page = None
        self.page_neutral = False
        self.page_close_callback = None
        self.connection_error = ""
        self.connection_state = None
        self.peer_tree = None
        self.connection_summary_var = tk.StringVar(value="Searching…")
        self.selection_var = tk.StringVar(value="No files selected")
        self.selected_path_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Connect the two laptops directly with Ethernet.")
        self.adapter_var = tk.StringVar(value="Ethernet: not detected")
        self.peer_var = tk.StringVar(value="Peer: searching…")
        self.link_var = tk.StringVar(value="○ NOT CONNECTED")
        self.sync_var = tk.StringVar(value="Waiting for a live heartbeat from the other laptop.")
        self.speed_var = tk.StringVar(value="")
        self.current_var = tk.StringVar(value="")
        self.wrap_var = tk.BooleanVar(value=True)
        self.verify_var = tk.BooleanVar(value=False)

        for mode in THEMES:
            apply_mode_theme(self, mode)
        apply_mode_theme(self, self.mode)
        self._build_role_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._drain_events)
        self.after(250, self._connection_tick)
        self.after(500, self.check_for_updates)
        self.after(300, self._show_startup_notes)

    def _clear_window(self) -> None:
        begin_motion(self)
        self._dismiss_page(animate=False)
        for child in self.winfo_children():
            if child is not getattr(self, "motion_overlay", None):
                child.destroy()
        self.link_label = None
        self.setup_button = None
        self.update_button = None
        self.listbox = None
        self.send_button = None
        self.connection_state = None
        self.peer_tree = None

    def _show_page(self, title, back_text="Back", close_callback=None, neutral=False):
        begin_motion(self)
        self._dismiss_page(animate=False)
        self.page_neutral = neutral
        if neutral:
            apply_mode_theme(self, "neutral")
        self.page = ttk.Frame(self, style="App.TFrame", padding=(32, 24))
        show_view(self.page, self.screen)
        self.page_close_callback = close_callback
        header = ttk.Frame(self.page, style="App.TFrame")
        header.pack(fill="x", pady=(0, 18))
        ttk.Button(header, text=back_text, image=icon_image(self, "arrow-left"), compound="left",
                   command=self._dismiss_page, style="Ghost.TButton").pack(side="left")
        if not neutral:
            mode_badge(header, self.mode).pack(side="right")
        ttk.Label(self.page, text=title, style="Title.TLabel").pack(anchor="w", pady=(0, 18))
        return self.page

    def _dismiss_page(self, animate=True):
        if self.page is not None:
            if animate:
                begin_motion(self)
            callback = self.page_close_callback
            self.page.destroy()
            self.page = None
            self.page_close_callback = None
            if self.page_neutral:
                apply_mode_theme(self, self.mode)
                self.page_neutral = False
            if callback:
                callback()
            if self.screen is not None and self.screen.winfo_exists():
                show_view(self.screen, animate=animate)

    def _build_update_button(self, parent: ttk.Frame) -> None:
        controls = ttk.Frame(parent, style="App.TFrame")
        controls.pack(side="right", anchor="n")
        self.update_button = ttk.Button(controls, textvariable=self.update_var,
            command=lambda: self.check_for_updates(manual=True), style="Ghost.TButton")
        self.update_button.pack(anchor="e")
        ttk.Label(controls, text=f"Version {APP_VERSION}", style="Small.TLabel").pack(anchor="e", padx=10, pady=(2, 0))
        self.update_button.configure(state="disabled" if self.update_busy else "normal")

    def _set_update_busy(self, busy: bool, text: str = "Check for updates") -> None:
        self.update_busy = busy
        self.update_var.set(text)
        if self.update_button:
            self.update_button.configure(state="disabled" if busy else "normal")

    def check_for_updates(self, manual: bool = False) -> None:
        if self.update_busy:
            return
        self._set_update_busy(True, "Checking…")

        def worker():
            try:
                self.events.put(("update_checked", latest_release(), manual))
            except Exception as exc:
                self.events.put(("update_error", str(exc), manual))

        threading.Thread(target=worker, daemon=True).start()

    def _offer_update(self, release: dict | None, manual: bool) -> None:
        if self.transfer_dialog or self.setup_in_progress or self.release_notes_dialog:
            self.after(1000, lambda: self._offer_update(release, manual))
            return
        self._set_update_busy(False)
        if release is None or version_tuple(release["version"]) <= version_tuple(APP_VERSION):
            if manual:
                notes = release["notes"] if release and version_tuple(release["version"]) == version_tuple(APP_VERSION) else bundled_release_notes()
                self._show_release_notes("You're up to date", notes)
            return
        page = self._show_page("Update available", neutral=True)
        ttk.Label(page, text=f"EtherDrop {release['version']} · Installed v{APP_VERSION}", style="Subtitle.TLabel").pack(anchor="w")
        self._notes_body(page, release["notes"])
        if not getattr(sys, "frozen", False):
            ttk.Label(page, text="Self-updating is available in the standalone EXE. Download the latest EXE from GitHub.",
                      style="Subtitle.TLabel", wraplength=700).pack(anchor="w", pady=12)
            ttk.Button(page, text="Open releases", command=lambda: os.startfile(f"https://github.com/{GITHUB_REPOSITORY}/releases/latest")).pack(anchor="e")
        else:
            ttk.Label(page, text="EtherDrop will close briefly, install the update, and reopen.", style="Subtitle.TLabel").pack(anchor="w", pady=12)
            ttk.Button(page, text="Download & restart", command=lambda: self._download_offered_update(release), style="Accent.TButton").pack(anchor="e")

    def _download_offered_update(self, release):
        page = self._show_page("Updating EtherDrop", neutral=True)
        for child in page.winfo_children():
            if isinstance(child, ttk.Frame):
                child.destroy()
        self.update_dialog = page
        self._set_update_busy(True, "Downloading…")
        self.update_installing = True
        self.update_progress_var.set(0)
        self.update_var.set(f"0.0 / {release['asset']['size'] / 1_000_000:.1f} MB · 0.0 MB/s")
        ttk.Label(page, textvariable=self.update_var, style="Subtitle.TLabel").pack(anchor="w", pady=16)
        ttk.Progressbar(page, maximum=100, variable=self.update_progress_var,
                        style="Modern.Horizontal.TProgressbar").pack(fill="x", pady=(0, 16))
        ttk.Label(page, text="EtherDrop will restart when the download finishes.", style="Subtitle.TLabel").pack(anchor="w")

        def worker():
            try:
                self.events.put(("update_downloaded", download_update(release, self.events)))
            except Exception as exc:
                self.events.put(("update_error", str(exc), True))
        threading.Thread(target=worker, daemon=True).start()

    def _show_startup_notes(self) -> None:
        if self.update_state.get("seen_version") == APP_VERSION:
            return
        if self.transfer_dialog or self.setup_in_progress:
            self.after(1000, self._show_startup_notes)
            return
        title = "EtherDrop updated" if self.update_state.get("seen_version") else "Welcome to EtherDrop"
        self._show_release_notes(title, bundled_release_notes())

    def _notes_body(self, parent, notes):
        body = RoundedCard(parent, padding=16, height=280)
        body.pack(fill="x", pady=(16, 0))
        text = tk.Text(body.body, wrap="word", bg=COLOR_SURFACE, fg=COLOR_TEXT, font=("Segoe UI", 11),
                       relief="flat", padx=8, pady=8, borderwidth=0)
        scrollbar = ttk.Scrollbar(body.body, orient="vertical", command=text.yview)
        scrollbar.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        text.configure(yscrollcommand=scrollbar.set)
        text.insert("1.0", notes)
        text.configure(state="disabled")

    def _show_release_notes(self, title: str, notes: str) -> None:
        def close():
            self.update_state["seen_version"] = APP_VERSION
            try:
                save_update_state(self.update_state)
            except OSError:
                pass
            self.release_notes_dialog = None
        page = self._show_page(title, close_callback=close, neutral=True)
        self.release_notes_dialog = page
        ttk.Label(page, text=f"What's new in EtherDrop {APP_VERSION}", style="Subtitle.TLabel").pack(anchor="w")
        self._notes_body(page, notes)
        ttk.Button(page, text="Continue", command=self._dismiss_page, style="Accent.TButton").pack(anchor="e", pady=(20, 0))

    def _handle_update_error(self, message: str, manual: bool) -> None:
        if self.update_dialog:
            self._dismiss_page()
            self.update_dialog = None
        self.update_installing = False
        self._set_update_busy(False)
        if manual:
            self._show_message("Couldn't update EtherDrop", message, neutral=True)

    def _show_message(self, title, message, neutral=False):
        page = self._show_page(title, neutral=neutral)
        ttk.Label(page, text=message, style="Subtitle.TLabel", wraplength=720, justify="left").pack(anchor="w")
        ttk.Button(page, text="Done", command=self._dismiss_page, style="Accent.TButton").pack(anchor="e", side="bottom")

    def _build_role_ui(self) -> None:
        self._clear_window()
        outer = ttk.Frame(self, style="App.TFrame", padding=(48, 28))
        self.screen = outer
        show_view(outer)
        top = ttk.Frame(outer, style="App.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="EtherDrop", style="Hero.TLabel").pack(side="left", anchor="n")
        self._build_update_button(top)
        intro = ttk.Frame(outer, style="App.TFrame")
        intro.pack(fill="x", pady=(8, 32))
        ttk.Label(intro, text="Send and receive files nearby.", style="Subtitle.TLabel").pack(anchor="w", pady=(8, 0))
        modes = ttk.Frame(outer, style="App.TFrame")
        ttk.Label(outer, text="Connection", style="Subtitle.TLabel").pack(anchor="w", pady=(0, 10))
        modes.pack(anchor="w", pady=(0, 16))
        for mode, label in (("ethernet", "Ethernet"), ("wifi", "Wi-Fi")):
            ttk.Button(modes, text=label, image=icon_image(self, "wifi" if mode == "wifi" else "ethernet-port", "ink" if self.mode == mode else "muted"),
                compound="left", command=lambda mode=mode: self._select_mode(mode),
                style="SelectedSegment.TButton" if self.mode == mode else "Segment.TButton").pack(side="left", padx=(0, 4))
        ttk.Label(outer, text="Connect with a cable between the laptops." if self.mode == "ethernet" else "Connect every laptop to the same Wi-Fi network.",
                  style="Subtitle.TLabel").pack(anchor="w", pady=(0, 24))
        ttk.Label(outer, text="Start a transfer", style="Title.TLabel", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(16, 16))
        roles = ttk.Frame(outer, style="App.TFrame")
        roles.pack(anchor="w", pady=(8, 0))
        for role, title, description, icon in (
            ("sender", "Send files", "Choose files and folders to share.", "upload"),
            ("receiver", "Receive files", "Review incoming files and choose where to save them.", "download"),
        ):
            ttk.Button(roles, text=f"   {title}\n   {description}", width=43,
                       image=icon_image(self, icon, self.mode, 36), compound="left",
                       command=lambda role=role: self.select_role(role),
                       style="Role.TButton").pack(fill="x", pady=(0, 12))
        footer = ttk.Frame(outer, style="App.TFrame")
        footer.pack(fill="x", side="bottom", pady=(18, 0))
        ttk.Button(footer, text="How it works", command=self._show_help, style="Ghost.TButton").pack(side="right")

    def _show_help(self):
        page = self._show_page("How it works")
        text = ("1. Connect both laptops with Ethernet, or join the same Wi-Fi network.\n\n"
                "2. Choose Send on one laptop and Receive on the others.\n\n"
                "3. Add files or folders, then send. Every receiver chooses a destination and approves independently.\n\n"
                "Ethernet uses an isolated physical wired adapter with no gateway. Wi-Fi sends to all discovered receivers.\n\n"
                "Open Connection for adapter details and setup. During a transfer, Details contains the full diagnostics and activity log.")
        ttk.Label(page, text=text, style="Subtitle.TLabel", wraplength=700, justify="left").pack(anchor="w")

    def _select_mode(self, mode):
        if mode == self.mode and self.screen is not None:
            return
        begin_motion(self)
        self.mode = mode
        apply_mode_theme(self, mode)
        self._build_role_ui()

    def select_role(self, role: str) -> None:
        if role not in ("sender", "receiver"):
            return
        begin_motion(self)
        self.shutdown_services()
        self.role = role
        self._build_main_ui()
        self.after(100, self.rescan)

    def _build_main_ui(self) -> None:
        self._clear_window()
        outer = ttk.Frame(self, style="App.TFrame", padding=(32, 24))
        self.screen = outer
        show_view(outer)
        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x")
        ttk.Button(header, text="Back", image=icon_image(self, "arrow-left"), compound="left",
                   command=self._change_role, style="Ghost.TButton").pack(side="left")
        mode_badge(header, self.mode).pack(side="right")
        ttk.Label(outer, text="Send files" if self.role == "sender" else "Receive files", style="Title.TLabel").pack(anchor="w", pady=(20, 18))
        info = ttk.Frame(outer, style="App.TFrame")
        info.pack(fill="x", pady=(0, 14))
        ttk.Label(info, textvariable=self.connection_summary_var, style="Subtitle.TLabel").pack(side="left")
        ttk.Button(info, text="Connection", command=self._show_connection,
                   style="Ghost.TButton").pack(side="right")
        self.main_content = ttk.Frame(outer, style="App.TFrame")
        self.main_content.pack(fill="both", expand=True)
        self.file_workspace = ttk.Frame(self.main_content, style="App.TFrame")
        self.connection_state = ttk.Frame(self.main_content, style="App.TFrame")
        center = ttk.Frame(self.connection_state, style="App.TFrame")
        center.place(relx=.5, rely=.43, anchor="center")
        self.state_icon = tk.Label(center, bg=COLOR_BG)
        self.state_icon.pack(pady=(0, 18))
        self.state_title = ttk.Label(center, style="Title.TLabel")
        self.state_title.pack()
        self.state_message = ttk.Label(center, style="Subtitle.TLabel", wraplength=580, justify="center")
        self.state_message.pack(pady=(10, 0))
        self.state_actions = ttk.Frame(center, style="App.TFrame")
        self.state_actions.pack(pady=(24, 0))
        ttk.Button(self.state_actions, text="Rescan", image=icon_image(self, "refresh-cw", "muted"),
                   compound="left", command=self.rescan).pack(side="left")
        ttk.Button(self.state_actions, text="Connection settings", command=self._show_connection,
                   style="Ghost.TButton").pack(side="left", padx=(8, 0))
        if self.role == "sender":
            files = RoundedCard(self.file_workspace, height=280)
            files.pack(fill="both", expand=True)
            section_head = ttk.Frame(files.body, style="Card.TFrame")
            section_head.pack(fill="x", pady=(0, 14))
            ttk.Label(section_head, textvariable=self.selection_var, style="CardTitle.TLabel").pack(side="left")
            ttk.Button(section_head, text="Clear", command=self.clear_selection, style="Link.TButton").pack(side="right")
            buttons = ttk.Frame(files.body, style="Card.TFrame")
            buttons.pack(fill="x", pady=(0, 12))
            ttk.Button(buttons, text="Add files…", image=icon_image(self, "file", "muted"), compound="left", command=self.add_files, style="Card.TButton").pack(side="left")
            ttk.Button(buttons, text="Add folder…", image=icon_image(self, "folder", "muted"), compound="left", command=self.add_folder, style="Card.TButton").pack(side="left", padx=(8, 0))
            file_list = ttk.Frame(files.body, style="Card.TFrame")
            file_list.pack(fill="both", expand=True)
            self.listbox = tk.Listbox(file_list, height=4, activestyle="none", bg=COLOR_SURFACE, fg=COLOR_TEXT,
                selectbackground=COLOR_SURFACE_ALT, selectforeground=COLOR_TEXT, highlightthickness=0,
                relief="flat", borderwidth=0, font=("Segoe UI", 11))
            scroll = ttk.Scrollbar(file_list, orient="vertical", command=self.listbox.yview)
            self.listbox.configure(yscrollcommand=scroll.set)
            scroll.pack(side="right", fill="y")
            self.listbox.pack(fill="both", expand=True)
            self.listbox.bind("<<ListboxSelect>>", self._selected_file_changed)
            self.listbox.file_drop = WindowsFileDrop(self.listbox, self.events)
            ttk.Label(files.body, textvariable=self.selected_path_var, style="CardMuted.TLabel", wraplength=740).pack(anchor="w", pady=(8, 0))
            footer = ttk.Frame(self.file_workspace, style="App.TFrame")
            footer.pack(fill="x", pady=(18, 0))
            ttk.Button(footer, text="Transfer options", image=icon_image(self, "settings-2", "muted"), compound="left",
                       command=self._show_transfer_options, style="Ghost.TButton").pack(side="left")
            self.send_button = ttk.Button(footer, text="Send", command=self.send_selected, state="disabled", style="Accent.TButton")
            self.send_button.pack(side="right", ipadx=25)
            self.refresh_list()
        self.progress = ttk.Progressbar(outer, maximum=100, style="Modern.Horizontal.TProgressbar")
        self._refresh_connection_ui()

    def _refresh_connection_ui(self):
        if self.connection_state is None or not self.connection_state.winfo_exists():
            return
        if self.adapter and self.role == "sender" and not self.connection_error:
            self.connection_state.pack_forget()
            if not self.file_workspace.winfo_manager():
                self.file_workspace.pack(fill="both", expand=True)
            return
        self.file_workspace.pack_forget()
        if not self.connection_state.winfo_manager():
            self.connection_state.pack(fill="both", expand=True)
        if self.connection_error:
            icon = "wifi-off" if self.mode == "wifi" else "unplug"
            title = f"{self.mode_label} needs attention"
            message = self.connection_error
            actions = True
        elif not self.adapter:
            icon, title = "refresh-cw", f"Checking {self.mode_label}…"
            message = "Looking for a connected Wi-Fi network." if self.mode == "wifi" else "Looking for a direct Ethernet connection."
            actions = False
        elif not self.peer_ip:
            expected = "receiver" if self.role == "sender" else "sender"
            icon, title = "wifi" if self.mode == "wifi" else "ethernet-port", f"Looking for a {expected}…"
            message = f"Open EtherDrop on the other laptop and choose {'Receive' if self.role == 'sender' else 'Send'} files."
            message += "\nUse the same Wi-Fi network and Wi-Fi mode." if self.mode == "wifi" else "\nUse Ethernet mode on both laptops."
            actions = True
        else:
            icon, title = "download", "Waiting for files"
            message = "Choose where to save each transfer when it arrives."
            actions = False
        self.state_icon.configure(image=icon_image(self, icon, self.mode, 48))
        self.state_title.configure(text=title)
        self.state_message.configure(text=message)
        if actions:
            self.state_actions.pack(pady=(24, 0))
        else:
            self.state_actions.pack_forget()

    def _selected_file_changed(self, event=None):
        selected = self.listbox.curselection()
        self.selected_path_var.set(str(self.selected_paths[selected[0]]) if selected and self.selected_paths else "")

    def _show_transfer_options(self):
        page = self._show_page("Transfer options")
        card = RoundedCard(page, height=235)
        card.pack(fill="x")
        ttk.Checkbutton(card.body, text="Wrap transfer in a folder", variable=self.wrap_var, style="Card.TCheckbutton").pack(anchor="w")
        ttk.Label(card.body, text="Create a separate folder in the chosen destination. Turn off to save items directly.",
                  style="CardMuted.TLabel", wraplength=650).pack(anchor="w", pady=(12, 24))
        ttk.Checkbutton(card.body, text="Verify files with SHA-256", variable=self.verify_var, style="Card.TCheckbutton").pack(anchor="w")
        ttk.Label(card.body, text="Checks every file during transfer. Leave off for maximum speed.", style="CardMuted.TLabel", wraplength=650).pack(anchor="w", pady=(12, 0))

    def _show_connection(self):
        page = self._show_page("Connection")
        card = RoundedCard(page, height=220)
        card.pack(fill="x")
        self.link_label = ttk.Label(card.body, textvariable=self.link_var, style="Waiting.TLabel")
        self.link_label.pack(anchor="w", pady=(0, 14))
        for variable in (self.adapter_var, self.peer_var, self.sync_var):
            ttk.Label(card.body, textvariable=variable, style="Card.TLabel", wraplength=700).pack(anchor="w", pady=(0, 10))
        if self.mode == "wifi":
            self.peer_list = ttk.Frame(page, style="Card.TFrame")
            self.peer_tree = ttk.Treeview(self.peer_list, columns=("address",), show="tree headings", height=1)
            self.peer_tree.heading("#0", text="Laptop")
            self.peer_tree.heading("address", text="Address")
            self.peer_tree.column("#0", width=260)
            self.peer_tree.column("address", width=230)
            scroll = ttk.Scrollbar(self.peer_list, orient="vertical", command=self.peer_tree.yview)
            self.peer_tree.configure(yscrollcommand=scroll.set)
            scroll.pack(side="right", fill="y")
            self.peer_tree.pack(fill="x")
            self._refresh_peer_list()
        controls = ttk.Frame(page, style="App.TFrame")
        controls.pack(fill="x", pady=(18, 0))
        ttk.Button(controls, text="Rescan", image=icon_image(self, "refresh-cw", "muted"), compound="left", command=self.rescan).pack(side="left")
        if self.mode == "ethernet":
            self.setup_button = ttk.Button(controls, text="Set up Ethernet", command=self.auto_configure_ethernet)
            self.setup_button.pack(side="left", padx=10)
        ttk.Label(page, textvariable=self.status_var, style="Subtitle.TLabel", wraplength=700).pack(anchor="w", pady=18)

    def _change_role(self) -> None:
        begin_motion(self)
        self.shutdown_services()
        self.role = None
        self._build_role_ui()

    def _set_link_state(self, text: str, state: str) -> None:
        self.link_var.set(text.replace("●  ", "").replace("○ ", "").capitalize())
        if state != "synced":
            self.connection_summary_var.set("Searching…" if state == "waiting" else "Needs attention")
        if self.link_label and self.link_label.winfo_exists():
            style = {
                "synced": "Sync.TLabel",
                "lost": "Lost.TLabel",
                "waiting": "Waiting.TLabel",
            }.get(state, "Waiting.TLabel")
            self.link_label.config(style=style)

    def auto_configure_ethernet(self) -> None:
        if self.setup_in_progress or self.transfer_dialog:
            return
        page = self._show_page("Set up Ethernet")
        ttk.Label(page, text=("Connect the cable directly to the other laptop. Windows will request administrator permission.\n\n"
            "EtherDrop checks for an active physical Ethernet adapter without a gateway, enables IPv6 if needed, "
            "adds direct-link firewall rules, and disables supported selective-suspend settings. "
            "The adapter restarts only if enabling IPv6 requires it.\n\n"
            "Wi-Fi, IPv4, DNS, DHCP, MTU, and router settings stay unchanged."),
            style="Subtitle.TLabel", wraplength=720, justify="left").pack(anchor="w")
        ttk.Button(page, text="Configure Ethernet", command=self._begin_ethernet_setup, style="Accent.TButton").pack(anchor="e", side="bottom")

    def _begin_ethernet_setup(self):
        page = self._show_page("Configuring Ethernet")
        for child in page.winfo_children():
            if isinstance(child, ttk.Frame):
                child.destroy()
        self.setup_dialog = page
        self.setup_in_progress = True
        self.shutdown_services()
        self._set_link_state("Configuring", "waiting")
        self.status_var.set("Waiting for Ethernet configuration and administrator approval…")
        progress = ttk.Progressbar(page, mode="indeterminate", style="Modern.Horizontal.TProgressbar")
        progress.pack(fill="x", pady=24)
        progress.start(12)
        ttk.Label(page, textvariable=self.status_var, style="Subtitle.TLabel", wraplength=700).pack(anchor="w")

        def worker():
            try:
                report = run_ethernet_autoconfigure(Path(sys.executable).resolve())
                self.events.put(("setup_done", report))
            except Exception as exc:
                self.events.put(("setup_error", str(exc)))
        threading.Thread(target=worker, daemon=True, name="ethernet-auto-setup").start()

    def _close_setup_dialog(self) -> None:
        if self.setup_dialog:
            self._dismiss_page()
        self.setup_dialog = None

    @staticmethod
    def _report_values(report: dict, key: str) -> list[str]:
        values = report.get(key) or []
        if isinstance(values, str):
            return [values]
        return [str(value) for value in values]

    def _handle_setup_done(self, report: dict) -> None:
        self.setup_in_progress = False
        self._close_setup_dialog()
        if self.setup_button and self.setup_button.winfo_exists():
            self.setup_button.config(state="normal")

        actions = self._report_values(report, "Actions")
        warnings = self._report_values(report, "Warnings")
        lines = [
            f"Adapter: {report.get('Adapter', 'Unknown')}",
            f"IPv6 link-local: {report.get('LinkLocal', 'Unknown')}",
            "",
            "Completed:",
            *(f"• {action}" for action in actions),
        ]
        if warnings:
            lines.extend(("", "Warnings:", *(f"• {warning}" for warning in warnings)))
        self._show_message("Ethernet configured", "\n".join(lines))
        self.status_var.set("Ethernet configuration completed. Rescanning the direct link…")
        self.after(200, self.rescan)

    def _handle_setup_error(self, message: str) -> None:
        self.setup_in_progress = False
        self._close_setup_dialog()
        if self.setup_button and self.setup_button.winfo_exists():
            self.setup_button.config(state="normal")
        self._set_link_state("●  SETUP NOT COMPLETED", "lost")
        self.status_var.set(message)
        self._show_message("Ethernet setup", message)
        self.after(200, self.rescan)

    def shutdown_services(self) -> None:
        if self.discovery:
            self.discovery.stop()
        if self.receiver:
            self.receiver.stop()
        if self.sender:
            self.sender.cancel()
        self.discovery = None
        self.receiver = None
        self.sender = None
        self.adapter = None
        self.peer_ip = None
        self.peer_name = None
        self.peer_role = None
        self.peer_last_seen = 0.0
        self.wifi_peers.clear()
        self.connection_error = ""
        self.connection_summary_var.set("Checking connection…")

    def rescan(self) -> None:
        if not self.role:
            return
        self.shutdown_services()
        self.scan_token += 1
        token = self.scan_token
        role = self.role
        self.adapter_var.set(f"{self.mode_label}: scanning…")
        expected = "receiver" if role == "sender" else "sender"
        self.peer_var.set(f"Peer: searching for a {expected}…")
        self._set_link_state("●  SEARCHING", "waiting")
        self.connection_summary_var.set(f"Checking {self.mode_label}…")
        self.status_var.set(f"Checking the {self.mode_label} connection…")
        self.sync_var.set("Waiting for a live heartbeat from the other laptop.")
        if self.send_button:
            self.send_button.config(state="disabled")
        self._refresh_connection_ui()
        self.update_idletasks()

        def worker():
            try:
                if self.mode == "wifi":
                    adapters = discover_wifi_adapters()
                    if not adapters:
                        raise RuntimeError("No connected physical Wi-Fi adapter with an IPv4 address was found. Connect to Wi-Fi, then rescan.")
                    self.events.put(("wifi_adapters", token, role, adapters))
                else:
                    adapter = choose_direct_adapter()
                    self.events.put(("adapter", token, role, adapter))
            except Exception as exc:
                self.events.put(("adapter_error", token, role, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _start_services(self, adapter: EthernetAdapter) -> None:
        if not self.role:
            return
        self.adapter = adapter
        self.discovery = WifiDiscoveryService(adapter, self.events, self.role) if self.mode == "wifi" else DiscoveryService(adapter, self.events, self.role)
        if self.role == "receiver":
            self.receiver = ReceiverService(adapter, self.events, self.coordinator)
            self.receiver.start()
        else:
            self.sender = SenderGroup(adapter, self.events, self.coordinator) if self.mode == "wifi" else Sender(adapter, self.events, self.coordinator)
        self.discovery.start()

    @property
    def mode_label(self):
        return "Wi-Fi" if self.mode == "wifi" else "Ethernet"

    def _choose_wifi_adapter(self, adapters, token, role):
        if len(adapters) == 1:
            self.events.put(("adapter", token, role, adapters[0]))
            return
        page = self._show_page("Choose a Wi-Fi adapter")
        def choose(adapter):
            self._dismiss_page()
            self.events.put(("adapter", token, role, adapter))
        for adapter in adapters:
            ttk.Button(page, text=f"{adapter.name} · {adapter.address}",
                       command=lambda adapter=adapter: choose(adapter)).pack(fill="x", pady=6)

    def _refresh_wifi_peers(self):
        peers = list(self.wifi_peers.values())
        self.peer_ip = peers[0]["ip"] if peers else None
        self.peer_name = peers[0]["name"] if peers else None
        self.peer_var.set(f"{len(peers)} {'receiver' if self.role == 'sender' else 'sender'}(s) discovered")
        self.connection_error = ""
        self._refresh_peer_list()
        self._set_link_state(f"{len(peers)} laptops discovered" if peers else "Searching", "synced" if peers else "waiting")
        if peers:
            role = "receiver" if self.role == "sender" else "sender"
            self.connection_summary_var.set(f"{len(peers)} {role}{'s' if len(peers) != 1 else ''} connected")
        else:
            self.connection_summary_var.set(f"Looking for a {'receiver' if self.role == 'sender' else 'sender'}…")
        self.sync_var.set("Receivers discovered on the local Wi-Fi network." if peers else "Waiting for local Wi-Fi discovery.")
        if not self.transfer_dialog:
            self.status_var.set("Ready to send to all discovered receivers." if peers and self.role == "sender" else "Waiting for a transfer offer." if peers else "Searching on Wi-Fi…")
        self._refresh_send_state()
        self._refresh_connection_ui()

    def _refresh_peer_list(self):
        if self.peer_tree is None or not self.peer_tree.winfo_exists():
            return
        self.peer_tree.delete(*self.peer_tree.get_children())
        for session, peer in self.wifi_peers.items():
            self.peer_tree.insert("", "end", iid=session, text=peer["name"], values=(peer["ip"],))
        if self.wifi_peers:
            self.peer_tree.configure(height=min(len(self.wifi_peers), 4))
            self.peer_list.pack(fill="x", pady=(16, 0))
        else:
            self.peer_list.pack_forget()

    def add_files(self) -> None:
        self._add_selected_paths(filedialog.askopenfilenames(title="Choose files to send"))

    def add_folder(self) -> None:
        path = filedialog.askdirectory(title="Choose folder to send")
        self._add_selected_paths([path] if path else [])

    def _add_selected_paths(self, paths) -> None:
        for p in paths:
            path = Path(p)
            if path not in self.selected_paths:
                self.selected_paths.append(path)
        self.refresh_list()

    def clear_selection(self) -> None:
        self.selected_paths.clear()
        self.refresh_list()

    def refresh_list(self) -> None:
        if not self.listbox:
            return
        self.listbox.delete(0, tk.END)
        self.selection_var.set(f"{len(self.selected_paths)} items selected" if self.selected_paths else "Files to share")
        self.selected_path_var.set("")
        if not self.selected_paths:
            self.listbox.insert(tk.END, "Drop files or folders here, or use Add files / Add folder.")
            self.listbox.itemconfig(0, foreground=COLOR_MUTED)
        else:
            for path in self.selected_paths:
                self.listbox.insert(tk.END, f"  {path.name}" + (" /" if path.is_dir() else ""))
        self._refresh_send_state()

    def _refresh_send_state(self) -> None:
        if not self.send_button:
            return
        dialog_active = bool(self.transfer_dialog and self.transfer_dialog.winfo_exists())
        enabled = bool(self.peer_ip and self.selected_paths and self.sender and self.adapter and not dialog_active)
        self.send_button.config(state="normal" if enabled else "disabled")

    def send_selected(self) -> None:
        if not self.sender or not self.peer_ip or not self.peer_name:
            self.status_var.set("No other EtherDrop laptop is connected.")
            return
        if not self.selected_paths:
            return

        self.send_button.config(state="disabled")
        self.progress["value"] = 0
        self.status_var.set("Preparing transfer…")
        self.speed_var.set("")
        if self.mode == "wifi":
            recipients = self.sender.send(list(self.wifi_peers.values()), list(self.selected_paths),
                                          bool(self.verify_var.get()), bool(self.wrap_var.get()))
            if not recipients:
                self._refresh_send_state()
                return
            self._dismiss_page()
            self.transfer_dialog = GroupTransferDialog(self, recipients, list(self.selected_paths), bool(self.verify_var.get()))
            show_view(self.transfer_dialog, self.screen)
            self.keep_awake_active, power_status = set_system_awake(True)
            self.transfer_dialog.set_detail("Windows keep-awake request", power_status)
            self._refresh_send_state()
            return
        transfer_id = self.sender.send(
            self.peer_ip,
            self.peer_name,
            list(self.selected_paths),
            bool(self.verify_var.get()),
            bool(self.wrap_var.get()),
        )
        if not transfer_id:
            self.status_var.set("This laptop is already handling another transfer.")
            self._refresh_send_state()
            return
        self._open_transfer_dialog(
            transfer_id=transfer_id,
            direction="Sending",
            peer=self.peer_name,
            peer_ip=self.peer_ip,
            verify=bool(self.verify_var.get()),
            sources=list(self.selected_paths),
            cancel_callback=lambda: self.sender.cancel(transfer_id) if self.sender else None,
        )

    def _open_transfer_dialog(
        self,
        transfer_id: str,
        direction: str,
        peer: str,
        peer_ip: str,
        verify: bool,
        sources: list[Path] | None,
        cancel_callback,
    ) -> TransferView:
        if not self.adapter:
            raise RuntimeError("Network adapter is unavailable.")
        self.active_transfer_id = transfer_id
        self._dismiss_page()
        dialog = TransferPanel(
            self,
            transfer_id,
            direction,
            self.adapter,
            cancel_callback,
            self._transfer_dialog_closed,
            peer=peer,
            peer_ip=peer_ip,
            verify=verify,
            sources=sources,
        )
        show_view(dialog, self.screen)
        self.transfer_dialog = dialog
        self.keep_awake_active, power_status = set_system_awake(True)
        dialog.set_detail("Windows keep-awake request", power_status)
        self._refresh_send_state()
        return dialog

    def _transfer_dialog_closed(self, dialog: TransferView) -> None:
        if self.transfer_dialog is dialog:
            self.transfer_dialog = None
            self.active_transfer_id = None
        self._build_main_ui()
        if self.mode == "wifi":
            self._refresh_wifi_peers()
        self._refresh_send_state()

    def _release_keep_awake(self) -> None:
        if self.keep_awake_active:
            _, status = set_system_awake(False)
            self.keep_awake_active = False
            if self.transfer_dialog and self.transfer_dialog.winfo_exists():
                self.transfer_dialog.set_detail("Windows keep-awake request", status)

    def _choose_incoming_destination(
        self,
        transfer_id: str,
        decision: IncomingTransferDecision,
        dialog: TransferView,
    ) -> None:
        if not dialog.winfo_exists() or transfer_id != self.active_transfer_id:
            decision.reject("The receiver window closed before a destination was selected.")
            return
        if dialog.cancel_requested:
            decision.reject("Transfer cancelled before a destination was selected.")
            return
        initial = self.last_destination if self.last_destination.exists() else Path.home()
        selected = filedialog.askdirectory(
            parent=dialog,
            title="Choose where to save this incoming transfer",
            initialdir=str(initial),
            mustexist=True,
        )
        if dialog.finished or dialog.cancel_requested or transfer_id != self.active_transfer_id:
            decision.reject("The transfer ended before a destination was confirmed.")
            return
        if selected:
            self.last_destination = Path(selected)
            dialog.set_detail("Chosen destination parent", selected)
            dialog.set_phase("Accepting", "Destination confirmed. Synchronizing acceptance with the sender…")
            decision.accept(Path(selected), self.winfo_id())
        else:
            dialog.set_phase("Declining", "No destination folder was selected; declining the transfer.")
            decision.reject("The receiver did not choose a destination folder.")

    def _handle_transfer_event(self, transfer_id: str, action: str, data: dict) -> None:
        if isinstance(self.transfer_dialog, GroupTransferDialog):
            if transfer_id not in self.transfer_dialog.panels:
                return
            if action == "worker_stopped":
                if self.sender.worker_stopped(transfer_id):
                    self.transfer_dialog.complete()
                    self._release_keep_awake()
                    self.status_var.set("Group transfer finished. Review each laptop’s result.")
            else:
                self.transfer_dialog.apply_transfer(transfer_id, action, data)
            return
        if action == "incoming_offer":
            decision: IncomingTransferDecision = data["decision"]
            if self.update_installing:
                decision.reject("EtherDrop is installing an update. Please retry after it restarts.")
                return
            if self.role != "receiver" or not self.receiver:
                decision.reject("This laptop is not in receiver mode.")
                return
            if self.transfer_dialog and self.transfer_dialog.winfo_exists():
                decision.reject("Please wait until the previous transfer result is closed.")
                return
            dialog = self._open_transfer_dialog(
                transfer_id=transfer_id,
                direction="Receiving",
                peer=str(data.get("peer") or "Unknown"),
                peer_ip=str(data.get("peer_ip") or "Unknown"),
                verify=bool(data.get("verify")),
                sources=None,
                cancel_callback=lambda: self.receiver.cancel(transfer_id) if self.receiver else None,
            )
            dialog.set_details(
                {
                    "State": "Awaiting receiver approval",
                    "Phase": "Destination required",
                    "Top-level items": " | ".join(data.get("roots", [])) or "Not supplied",
                    "File count": data.get("file_count", 0),
                    "Total bytes": f"{human_bytes(data.get('total', 0))} ({data.get('total', 0)} bytes)",
                    "Save layout": "Separate transfer folder" if data.get("wrap", True) else "Directly in chosen destination",
                }
            )
            dialog.set_phase(
                "Destination required",
                "Review the offer, then choose where it will be saved. Nothing is accepted until you confirm.",
            )
            dialog.offer_destination_choice(
                lambda: self._choose_incoming_destination(transfer_id, decision, dialog)
            )
            self.status_var.set(f"Incoming offer from {data.get('peer', 'peer')} — awaiting your destination choice.")
            return

        dialog = self.transfer_dialog
        if dialog and dialog.winfo_exists() and dialog.transfer_id == transfer_id:
            dialog.apply_event(action, data)

        if action == "phase":
            self.status_var.set(str(data.get("message") or data.get("phase") or "Working…"))
        elif action == "paused":
            self.status_var.set("Connection interrupted. Waiting to reconnect — keep both apps open.")
            self.speed_var.set("Waiting to reconnect")
        elif action == "resumed":
            self.progress["value"] = data.get("done", 0) / data["total"] * 100 if data.get("total") else 100
            self.status_var.set("Connection restored. Continuing from saved progress.")
            self.speed_var.set("")
        elif action == "prepared":
            self.status_var.set(f"Prepared {data.get('file_count', 0)} file(s) — {human_bytes(data.get('total', 0))}.")
        elif action == "start":
            self.progress["value"] = 0
            self.status_var.set(f"{data.get('direction', 'Transferring')} {data.get('file_count', 0)} file(s).")
            self.current_var.set(str(data.get("destination") or ""))
        elif action == "file_start":
            self.current_var.set(str(data.get("path") or ""))
        elif action == "progress":
            done = int(data.get("done") or 0)
            total = int(data.get("total") or 0)
            pct = done / total * 100 if total else 100
            self.progress["value"] = pct
            self.speed_var.set(f"{pct:.1f}% — {human_bytes(done)} of {human_bytes(total)}")
        elif action == "done":
            self.progress["value"] = 100
            self.status_var.set("Transfer completed and confirmed by both laptops.")
            self.speed_var.set(f"Average: {human_bytes(data.get('average_bps', 0))}/s")
            self._release_keep_awake()
            self._refresh_send_state()
        elif action in ("rejected", "cancelled", "failed"):
            label = {"rejected": "declined", "cancelled": "cancelled", "failed": "failed"}[action]
            self.status_var.set(f"Transfer {label}: {data.get('message', '')}")
            self.speed_var.set("")
            self._release_keep_awake()
            self._refresh_send_state()

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]

                if kind == "update_checked":
                    self._offer_update(event[1], event[2])

                elif kind == "files_dropped":
                    _, widget, paths = event
                    if (self.role == "sender" and self.listbox is widget and self.page is None
                            and self.transfer_dialog is None and widget.winfo_ismapped()):
                        self._add_selected_paths(paths)

                elif kind == "update_progress":
                    self.update_var.set(f"{event[1] / 1_000_000:.1f} / {event[2] / 1_000_000:.1f} MB · {event[3] / 1_000_000:.1f} MB/s")
                    self.update_progress_var.set(event[1] / event[2] * 100)

                elif kind == "update_error":
                    self._handle_update_error(event[1], event[2])

                elif kind == "update_downloaded":
                    staging = event[1]
                    try:
                        launch_updater(staging)
                    except Exception as exc:
                        shutil.rmtree(staging)
                        self._handle_update_error(str(exc), True)
                    else:
                        self.shutdown_services()
                        self._release_keep_awake()
                        self._closing = True
                        self.destroy()
                        return

                elif kind == "wifi_adapters":
                    _, token, role, adapters = event
                    if token == self.scan_token and role == self.role:
                        self._choose_wifi_adapter(adapters, token, role)

                elif kind in ("wifi_peer", "wifi_peer_lost", "wifi_discovery_error"):
                    if not isinstance(self.discovery, WifiDiscoveryService) or event[1] != self.discovery.token:
                        continue
                    if kind == "wifi_peer":
                        _, _, session, name, address, role = event
                        self.wifi_peers[session] = {"name": name, "ip": address, "role": role}
                    elif kind == "wifi_peer_lost":
                        self.wifi_peers.pop(event[2], None)
                    else:
                        self.status_var.set(f"Wi-Fi discovery failed: {event[2]}")
                        self.connection_error = self.status_var.get()
                        self._set_link_state("Discovery failed", "lost")
                        continue
                    self._refresh_wifi_peers()

                elif kind == "adapter":
                    _, token, role, adapter = event
                    if token != self.scan_token or role != self.role:
                        continue
                    self._start_services(adapter)
                    speed = adapter.link_speed or human_bytes(min(adapter.rx_bps, adapter.tx_bps) / 8) + "/s"
                    self.adapter_var.set(f"{self.mode_label}: {adapter.name} — {speed} — {'local network' if self.mode == 'wifi' else 'direct-link mode'}")
                    expected = "receiver" if self.role == "sender" else "sender"
                    self.status_var.set(f"{self.mode_label} ready. Waiting for the {expected} laptop…")
                    self.connection_error = ""
                    self.connection_summary_var.set(f"Looking for a {expected}…")

                elif kind == "adapter_error":
                    _, token, role, message = event
                    if token != self.scan_token or role != self.role:
                        continue
                    self.adapter_var.set(f"{self.mode_label}: unavailable")
                    self.status_var.set(message)
                    self.connection_error = message
                    self.peer_var.set("Peer: not connected")
                    self._set_link_state("●  NOT CONNECTED", "lost")

                elif kind == "peer":
                    self.connection_error = ""
                    self.peer_name, self.peer_ip, self.peer_role = event[1], event[2], event[3]
                    self.peer_last_seen = time.monotonic()
                    label = self.peer_role.capitalize()
                    scope = self.adapter.if_index if self.adapter else 0
                    self.peer_var.set(f"{label}: {self.peer_name} — [{self.peer_ip}%{scope}]")
                    self._set_link_state("Linked & synced", "synced")
                    self.connection_summary_var.set(f"Connected to {self.peer_name}")
                    if self.transfer_dialog and self.transfer_dialog.winfo_exists():
                        self.transfer_dialog.set_detail(
                            "Latest peer discovery heartbeat",
                            datetime.now().astimezone().isoformat(timespec="seconds"),
                        )
                        self.transfer_dialog.set_detail("Discovery synchronization", "Linked")
                    if not self.transfer_dialog:
                        self.status_var.set("Both laptops are connected and ready." if self.role == "receiver" else "Ready to send.")
                    self._refresh_send_state()

                elif kind == "peer_lost":
                    self.peer_ip = None
                    self.peer_name = None
                    self.peer_role = None
                    expected = "receiver" if self.role == "sender" else "sender"
                    self.peer_var.set(f"Peer: searching for a {expected}…")
                    self._set_link_state("●  CONNECTION LOST", "lost")
                    self.sync_var.set("The peer heartbeat stopped. Check the cable and the other laptop.")
                    self.connection_error = "The connection to the other laptop was lost.\nCheck the cable and keep EtherDrop open on both laptops, then rescan."
                    self.status_var.set(self.connection_error)
                    if self.transfer_dialog and self.transfer_dialog.winfo_exists():
                        self.transfer_dialog.set_detail("Discovery synchronization", "Heartbeat lost")
                        self.transfer_dialog.add_log("Peer discovery heartbeat was lost; the TCP transfer determines final status.")
                    self._refresh_send_state()

                elif kind == "setup_done":
                    self._handle_setup_done(event[1])

                elif kind == "setup_error":
                    self._handle_setup_error(event[1])

                elif kind == "transfer":
                    _, transfer_id, action, data = event
                    self._handle_transfer_event(transfer_id, action, data)

                elif kind == "error":
                    self.status_var.set(event[1])
                    self.connection_error = event[1]
                    self.speed_var.set("")
                    self._refresh_send_state()

        except queue.Empty:
            pass
        finally:
            if not self._closing:
                self._refresh_connection_ui()
                self.after(100, self._drain_events)

    def _connection_tick(self) -> None:
        if self.mode == "ethernet" and self.peer_ip and self.peer_last_seen:
            age = max(time.monotonic() - self.peer_last_seen, 0.0)
            self.sync_var.set(f"Live peer heartbeat received {age:.1f}s ago — both clients are synchronized.")
            if self.transfer_dialog and self.transfer_dialog.winfo_exists():
                self.transfer_dialog.set_detail("Peer heartbeat age", f"{age:.1f}s")
        self.after(250, self._connection_tick)

    def _close(self) -> None:
        if self.update_installing:
            self.update_var.set("Please wait for the download to finish.")
            return
        if self.setup_in_progress:
            self.status_var.set("Complete or cancel the Windows administrator prompt first.")
            return
        if self.coordinator.locked() and (self.sender or self.receiver):
            if not self.close_after_transfer:
                self.close_after_transfer = True
                if self.sender:
                    self.sender.cancel()
                if self.receiver:
                    self.receiver.cancel()
                self.status_var.set("Cancelling the transfer and removing new output before closing…")
            self.after(100, self._close)
            return
        self.shutdown_services()
        self._release_keep_awake()
        self._closing = True
        self.destroy()



def main() -> None:
    if platform.system() != "Windows":
        print("EtherDrop is currently Windows-only.", file=sys.stderr)
        raise SystemExit(1)

    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_NAME)
    app = EtherDropApp()
    app.mainloop()


if __name__ == "__main__":
    main()
