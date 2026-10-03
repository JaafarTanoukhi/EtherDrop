from __future__ import annotations

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
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "EtherDrop"
APP_VERSION = "1.0.0"
GITHUB_REPOSITORY = "JaafarTanoukhi/EtherDrop"
RELEASE_ASSET = "EtherDrop.exe"
PROTOCOL_VERSION = 2
MAGIC = "ETHERDROP_V2"
DISCOVERY_PORT = 45670
TRANSFER_PORT = 45671
DISCOVERY_GROUP = "ff02::1"
ANNOUNCE_INTERVAL = 1.0
PEER_TIMEOUT = 4.0

BLOCK_SIZE = 8 * 1024 * 1024
SOCKET_BUFFER = 4 * 1024 * 1024
MAX_CONTROL_FRAME = 1024 * 1024

SESSION_ID = uuid.uuid4().hex

ES_CONTINUOUS = 0x80000000
ES_SYSTEM_REQUIRED = 0x00000001

COLOR_BG = "#08111F"
COLOR_SURFACE = "#101B2E"
COLOR_SURFACE_ALT = "#16243B"
COLOR_PANEL = "#0C1728"
COLOR_BORDER = "#243653"
COLOR_TEXT = "#F4F7FB"
COLOR_MUTED = "#91A2BC"
COLOR_ACCENT = "#7567FF"
COLOR_ACCENT_HOVER = "#897DFF"
COLOR_CYAN = "#35C8E6"
COLOR_CYAN_HOVER = "#59D5ED"
COLOR_SUCCESS = "#35D399"
COLOR_WARNING = "#F4B84A"
COLOR_DANGER = "#F0657A"
COLOR_DANGER_HOVER = "#F47C8E"

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
    window.geometry(f"{actual_width}x{actual_height}")
    window.minsize(actual_min_width, actual_min_height)


enable_high_dpi_awareness()


def configure_modern_theme(root: tk.Misc) -> None:
    style = ttk.Style(root)
    style.theme_use("clam")

    root.configure(background=COLOR_BG)
    style.configure(".", font=("Segoe UI", 10), background=COLOR_BG, foreground=COLOR_TEXT)
    style.configure("App.TFrame", background=COLOR_BG)
    style.configure("Card.TFrame", background=COLOR_SURFACE)
    style.configure("Panel.TFrame", background=COLOR_PANEL)

    style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT)
    style.configure("Hero.TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 25, "bold"))
    style.configure("Title.TLabel", background=COLOR_BG, foreground=COLOR_TEXT, font=("Segoe UI", 20, "bold"))
    style.configure("Subtitle.TLabel", background=COLOR_BG, foreground=COLOR_MUTED, font=("Segoe UI", 10))
    style.configure("Card.TLabel", background=COLOR_SURFACE, foreground=COLOR_TEXT)
    style.configure("CardTitle.TLabel", background=COLOR_SURFACE, foreground=COLOR_TEXT, font=("Segoe UI", 12, "bold"))
    style.configure("CardMuted.TLabel", background=COLOR_SURFACE, foreground=COLOR_MUTED)
    style.configure("MetricLabel.TLabel", background=COLOR_SURFACE, foreground=COLOR_MUTED, font=("Segoe UI", 9))
    style.configure("MetricValue.TLabel", background=COLOR_SURFACE, foreground=COLOR_TEXT, font=("Segoe UI", 11, "bold"))
    style.configure("AccentText.TLabel", background=COLOR_BG, foreground=COLOR_ACCENT, font=("Segoe UI", 10, "bold"))

    style.configure("RoleBadge.TLabel", background=COLOR_ACCENT, foreground="#FFFFFF", padding=(12, 5), font=("Segoe UI", 9, "bold"))
    style.configure("ReceiverBadge.TLabel", background=COLOR_CYAN, foreground=COLOR_BG, padding=(12, 5), font=("Segoe UI", 9, "bold"))
    style.configure("Sync.TLabel", background=COLOR_SURFACE, foreground=COLOR_SUCCESS, font=("Segoe UI", 12, "bold"))
    style.configure("Waiting.TLabel", background=COLOR_SURFACE, foreground=COLOR_WARNING, font=("Segoe UI", 12, "bold"))
    style.configure("Lost.TLabel", background=COLOR_SURFACE, foreground=COLOR_DANGER, font=("Segoe UI", 12, "bold"))
    style.configure("Phase.TLabel", background=COLOR_ACCENT, foreground="#FFFFFF", padding=(12, 5), font=("Segoe UI", 9, "bold"))
    style.configure("SuccessPhase.TLabel", background=COLOR_SUCCESS, foreground=COLOR_BG, padding=(12, 5), font=("Segoe UI", 9, "bold"))
    style.configure("WarningPhase.TLabel", background=COLOR_WARNING, foreground=COLOR_BG, padding=(12, 5), font=("Segoe UI", 9, "bold"))
    style.configure("DangerPhase.TLabel", background=COLOR_DANGER, foreground="#FFFFFF", padding=(12, 5), font=("Segoe UI", 9, "bold"))

    style.configure(
        "TButton",
        background=COLOR_SURFACE_ALT,
        foreground=COLOR_TEXT,
        borderwidth=0,
        focusthickness=0,
        focuscolor=COLOR_SURFACE_ALT,
        padding=(14, 9),
        font=("Segoe UI", 10, "bold"),
    )
    style.map(
        "TButton",
        background=[("active", COLOR_BORDER), ("pressed", COLOR_PANEL), ("disabled", COLOR_SURFACE)],
        foreground=[("disabled", "#53627A")],
    )
    style.configure("Accent.TButton", background=COLOR_ACCENT, foreground="#FFFFFF")
    style.map("Accent.TButton", background=[("active", COLOR_ACCENT_HOVER), ("pressed", "#6254E8"), ("disabled", "#34315B")])
    style.configure("Cyan.TButton", background=COLOR_CYAN, foreground=COLOR_BG)
    style.map("Cyan.TButton", background=[("active", COLOR_CYAN_HOVER), ("pressed", "#25B5D2")])
    style.configure("Danger.TButton", background=COLOR_DANGER, foreground="#FFFFFF")
    style.map("Danger.TButton", background=[("active", COLOR_DANGER_HOVER), ("pressed", "#D95168")])
    style.configure("Ghost.TButton", background=COLOR_SURFACE, foreground=COLOR_MUTED, padding=(11, 7))
    style.map("Ghost.TButton", background=[("active", COLOR_SURFACE_ALT)], foreground=[("active", COLOR_TEXT)])

    style.configure(
        "Card.TLabelframe",
        background=COLOR_SURFACE,
        bordercolor=COLOR_BORDER,
        borderwidth=1,
        relief="solid",
    )
    style.configure(
        "Card.TLabelframe.Label",
        background=COLOR_SURFACE,
        foreground=COLOR_MUTED,
        font=("Segoe UI", 9, "bold"),
    )
    style.configure("Card.TCheckbutton", background=COLOR_SURFACE, foreground=COLOR_MUTED, padding=3)
    style.map(
        "Card.TCheckbutton",
        background=[("active", COLOR_SURFACE)],
        foreground=[("active", COLOR_TEXT)],
        indicatorcolor=[("selected", COLOR_ACCENT), ("!selected", COLOR_PANEL)],
    )

    style.configure(
        "Modern.Horizontal.TProgressbar",
        background=COLOR_ACCENT,
        troughcolor=COLOR_PANEL,
        bordercolor=COLOR_PANEL,
        lightcolor=COLOR_ACCENT,
        darkcolor=COLOR_ACCENT,
        thickness=10,
    )
    style.configure("TNotebook", background=COLOR_BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", background=COLOR_SURFACE, foreground=COLOR_MUTED, padding=(16, 9), borderwidth=0)
    style.map(
        "TNotebook.Tab",
        background=[("selected", COLOR_SURFACE_ALT), ("active", COLOR_SURFACE_ALT)],
        foreground=[("selected", COLOR_TEXT), ("active", COLOR_TEXT)],
    )
    style.configure(
        "Treeview",
        background=COLOR_PANEL,
        fieldbackground=COLOR_PANEL,
        foreground=COLOR_TEXT,
        bordercolor=COLOR_BORDER,
        rowheight=29,
        relief="flat",
    )
    style.map("Treeview", background=[("selected", COLOR_ACCENT)], foreground=[("selected", "#FFFFFF")])
    style.configure(
        "Treeview.Heading",
        background=COLOR_SURFACE_ALT,
        foreground=COLOR_MUTED,
        bordercolor=COLOR_BORDER,
        relief="flat",
        padding=(8, 8),
        font=("Segoe UI", 9, "bold"),
    )
    style.map("Treeview.Heading", background=[("active", COLOR_BORDER)])
    style.configure("TScrollbar", background=COLOR_SURFACE_ALT, troughcolor=COLOR_PANEL, bordercolor=COLOR_PANEL, arrowcolor=COLOR_MUTED)


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
class TransferItem:
    source: Path
    relative: str
    size: int


@dataclass
class IncomingTransferDecision:
    ready: threading.Event = field(default_factory=threading.Event)
    destination: Path | None = None
    reason: str = "Transfer declined by the receiver."

    def accept(self, destination: Path) -> None:
        if self.ready.is_set():
            return
        self.destination = destination
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
        with urlopen(request, timeout=30) as response, downloaded.open("wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)
                digest.update(block)
                done += len(block)
                events.put(("update_progress", done, asset["size"]))
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


def configure_stream_socket(sock: socket.socket) -> None:
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
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
    if p.is_absolute() or not p.parts:
        raise ValueError("Unsafe file path.")
    if any(part in ("", ".", "..") for part in p.parts):
        raise ValueError("Unsafe file path.")
    if ":" in p.parts[0]:
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
            size = selected.stat().st_size
            items.append(TransferItem(selected, PurePosixPath(root_name).as_posix(), size))
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
                        size = src.stat().st_size
                    except OSError:
                        continue
                    rel = src.relative_to(selected)
                    remote = PurePosixPath(root_name, *rel.parts).as_posix()
                    items.append(TransferItem(src, remote, size))
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


class ReceiverService:
    def __init__(self, adapter: EthernetAdapter, events: queue.Queue, coordinator: threading.Lock):
        self.adapter = adapter
        self.events = events
        self.coordinator = coordinator
        self.stop_event = threading.Event()
        self.server_socket: socket.socket | None = None
        self.thread: threading.Thread | None = None
        self.state_lock = threading.Lock()
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
            try:
                self.server_socket.close()
            except OSError:
                pass

    def cancel(self, transfer_id: str | None = None) -> None:
        with self.state_lock:
            if transfer_id and transfer_id != self.active_transfer_id:
                return
            cancel_event = self.active_cancel
            decision = self.active_decision
            conn = self.active_socket
            send_lock = self.active_send_lock
        if cancel_event:
            cancel_event.set()
        if decision:
            decision.reject("Transfer cancelled by the receiver.")
        if conn:
            try:
                if send_lock:
                    with send_lock:
                        send_frame(conn, {"type": "cancel", "reason": "Transfer cancelled by the receiver."})
                else:
                    send_frame(conn, {"type": "cancel", "reason": "Transfer cancelled by the receiver."})
            except OSError:
                pass
            try:
                conn.shutdown(socket.SHUT_RD)
            except OSError:
                pass

    def _run(self) -> None:
        srv = None
        try:
            srv = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            self.server_socket = srv
            srv.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            configure_stream_socket(srv)
            srv.bind(ipv6_scope_tuple(self.adapter.link_local, TRANSFER_PORT, self.adapter.if_index))
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

                threading.Thread(
                    target=self._handle_connection,
                    args=(conn, addr),
                    daemon=True,
                    name="incoming-transfer",
                ).start()

        except Exception as exc:
            if not self.stop_event.is_set():
                self.events.put(("error", f"Receiver failed: {exc}"))
        finally:
            if srv:
                try:
                    srv.close()
                except OSError:
                    pass

    def _handle_connection(self, conn: socket.socket, addr) -> None:
        configure_stream_socket(conn)
        acquired = False
        transfer_id = ""
        transfer_root: Path | None = None
        cancel_event = threading.Event()
        send_lock = threading.Lock()

        def send_reply(payload: dict) -> None:
            with send_lock:
                send_frame(conn, payload)

        try:
            offer = recv_frame(conn)
            if offer.get("magic") != MAGIC or offer.get("type") != "offer":
                raise ValueError("Invalid EtherDrop connection.")

            transfer_id = str(offer.get("transfer_id") or "")
            if not transfer_id:
                raise ValueError("Missing transfer identifier.")

            if not self.coordinator.acquire(blocking=False):
                send_frame(conn, {"type": "reject", "reason": "This laptop is already handling another transfer."})
                return
            acquired = True

            peer_name = str(offer.get("hostname") or "Other laptop")
            peer_ip = str(addr[0]).split("%")[0]
            verify = bool(offer.get("verify"))
            expected_total = int(offer.get("total_bytes") or 0)
            file_count = int(offer.get("file_count") or 0)
            roots = [str(value) for value in offer.get("roots", [])]
            decision = IncomingTransferDecision()

            with self.state_lock:
                self.active_transfer_id = transfer_id
                self.active_socket = conn
                self.active_cancel = cancel_event
                self.active_decision = decision
                self.active_send_lock = send_lock

            emit_transfer(
                self.events,
                transfer_id,
                "incoming_offer",
                peer=peer_name,
                peer_ip=peer_ip,
                total=expected_total,
                file_count=file_count,
                verify=verify,
                roots=roots,
                decision=decision,
            )

            while not decision.ready.wait(0.2):
                if self.stop_event.is_set() or cancel_event.is_set():
                    raise TransferCancelled("Transfer cancelled while waiting for a destination.")
                readable, _, _ = select.select([conn], [], [], 0)
                if readable and conn.recv(1, socket.MSG_PEEK) == b"":
                    raise TransferCancelled("The sender cancelled before a destination was selected.")

            if cancel_event.is_set():
                raise TransferCancelled("Transfer cancelled by the receiver.")
            if decision.destination is None:
                send_reply({"type": "reject", "reason": decision.reason})
                emit_transfer(self.events, transfer_id, "rejected", message=decision.reason)
                return

            destination = decision.destination.resolve()
            destination.mkdir(parents=True, exist_ok=True)
            transfer_root = unique_transfer_root(destination, peer_name)
            disk = shutil.disk_usage(destination)
            storage = {
                "Receiver volume total": f"{human_bytes(disk.total)} ({disk.total} bytes)",
                "Receiver volume free before transfer": f"{human_bytes(disk.free)} ({disk.free} bytes)",
                "Receiver free space after payload (estimated)": (
                    f"{human_bytes(disk.free - expected_total)} ({disk.free - expected_total} bytes)"
                ),
            }
            send_reply(
                {
                    "type": "accept",
                    "destination": str(transfer_root),
                    "disk_total": disk.total,
                    "disk_free": disk.free,
                },
            )
            emit_transfer(
                self.events,
                transfer_id,
                "start",
                direction="Receiving",
                peer=peer_name,
                peer_ip=peer_ip,
                total=expected_total,
                file_count=file_count,
                verify=verify,
                destination=str(transfer_root),
                socket=socket_diagnostics(conn),
                storage=storage,
            )

            received_total = 0
            started = time.monotonic()
            reusable = bytearray(BLOCK_SIZE)
            view = memoryview(reusable)

            for file_index in range(1, file_count + 1):
                if cancel_event.is_set():
                    raise TransferCancelled("Transfer cancelled by the receiver.")

                meta = recv_frame(conn)
                if meta.get("type") != "file":
                    raise ValueError("Expected file metadata.")

                rel = safe_relative_path(str(meta["path"]))
                size = int(meta["size"])
                if size < 0:
                    raise ValueError("Invalid file size.")

                dest = transfer_root / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                emit_transfer(
                    self.events,
                    transfer_id,
                    "file_start",
                    index=file_index,
                    file_count=file_count,
                    path=rel.as_posix(),
                    destination=str(dest),
                    size=size,
                )

                hasher = hashlib.sha256() if verify else None
                remaining = size
                file_done = 0
                last_progress = 0.0
                with open(dest, "wb", buffering=0) as f:
                    while remaining:
                        if cancel_event.is_set():
                            raise TransferCancelled("Transfer cancelled by the receiver.")
                        wanted = min(BLOCK_SIZE, remaining)
                        filled = 0

                        while filled < wanted:
                            got = conn.recv_into(view[filled:wanted])
                            if got == 0:
                                raise TransferCancelled("The sender cancelled during file data.")
                            filled += got

                        block = view[:filled]
                        f.write(block)
                        if hasher:
                            hasher.update(block)

                        remaining -= filled
                        file_done += filled
                        received_total += filled

                        now = time.monotonic()
                        if now - last_progress >= 0.10:
                            emit_transfer(
                                self.events,
                                transfer_id,
                                "progress",
                                done=received_total,
                                total=expected_total,
                                current_file_done=file_done,
                                current_file_size=size,
                                current=rel.as_posix(),
                            )
                            last_progress = now

                digest = ""
                if verify:
                    trailer = recv_frame(conn)
                    if trailer.get("type") != "hash":
                        raise ValueError("Missing hash trailer.")
                    digest = hasher.hexdigest()
                    expected = str(trailer.get("sha256") or "")
                    if digest.lower() != expected.lower():
                        try:
                            dest.unlink()
                        except OSError:
                            pass
                        raise IOError(f"SHA-256 verification failed for {rel.as_posix()}")

                send_reply({"type": "file_ok"})
                emit_transfer(
                    self.events,
                    transfer_id,
                    "file_done",
                    index=file_index,
                    path=rel.as_posix(),
                    size=size,
                    sha256=digest,
                )

            final = recv_frame(conn)
            if final.get("type") != "done":
                raise ValueError("Transfer did not end correctly.")
            send_reply({"type": "done_ok"})

            elapsed = max(time.monotonic() - started, 0.001)
            emit_transfer(
                self.events,
                transfer_id,
                "done",
                done=received_total,
                average_bps=received_total / elapsed,
                destination=str(transfer_root),
            )

        except TransferCancelled as exc:
            if transfer_id:
                emit_transfer(
                    self.events,
                    transfer_id,
                    "cancelled",
                    message=str(exc),
                    destination=str(transfer_root) if transfer_root else "Not created",
                )
        except Exception as exc:
            if transfer_id:
                peer_ended = isinstance(exc, ConnectionError) and str(exc) == "Connection closed unexpectedly."
                action = "cancelled" if cancel_event.is_set() or peer_ended else "failed"
                message = "The sender cancelled or cleanly closed the transfer." if peer_ended else str(exc)
                emit_transfer(
                    self.events,
                    transfer_id,
                    action,
                    message=message,
                    error_type=type(exc).__name__,
                    destination=str(transfer_root) if transfer_root else "Not created",
                )
            elif not self.stop_event.is_set():
                self.events.put(("error", f"Incoming connection failed: {exc}"))
        finally:
            with self.state_lock:
                if self.active_transfer_id == transfer_id:
                    self.active_transfer_id = None
                    self.active_socket = None
                    self.active_cancel = None
                    self.active_decision = None
                    self.active_send_lock = None
            try:
                conn.close()
            except OSError:
                pass
            if acquired:
                self.coordinator.release()


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
            self.cancel_event.set()
            sock = self.active_socket
        if sock:
            try:
                sock.shutdown(socket.SHUT_WR)
            except OSError:
                pass

    def send(self, peer_ip: str, peer_name: str, paths: list[Path], verify: bool) -> str | None:
        if not self.coordinator.acquire(blocking=False):
            return None
        transfer_id = uuid.uuid4().hex
        self.cancel_event.clear()
        with self.state_lock:
            self.active_transfer_id = transfer_id
        threading.Thread(
            target=self._send_worker,
            args=(transfer_id, peer_ip, peer_name, paths, verify),
            daemon=True,
            name="sender",
        ).start()
        return transfer_id

    def _send_worker(
        self,
        transfer_id: str,
        peer_ip: str,
        peer_name: str,
        paths: list[Path],
        verify: bool,
    ) -> None:
        sock = None
        responses: queue.Queue = queue.Queue()
        remote_cancel_event = threading.Event()
        remote_cancel_reason = [""]

        def read_responses() -> None:
            while True:
                try:
                    response = recv_frame(sock)
                except Exception as exc:
                    responses.put(("error", exc))
                    return
                if response.get("type") == "cancel":
                    remote_cancel_reason[0] = str(
                        response.get("reason") or "The receiver cancelled the transfer."
                    )
                    remote_cancel_event.set()
                    responses.put(("cancel", response))
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    return
                responses.put(("response", response))

        def wait_for_response() -> dict:
            kind, value = responses.get()
            if kind == "cancel":
                raise TransferCancelled(remote_cancel_reason[0])
            if kind == "error":
                raise value
            return value

        try:
            emit_transfer(self.events, transfer_id, "phase", phase="Scanning selected files", message="Reading names and sizes.")
            items, total = build_transfer_items(paths, self.cancel_event)
            if self.cancel_event.is_set():
                raise TransferCancelled("Transfer cancelled while scanning files.")
            if not items:
                raise RuntimeError("No transferable files were selected.")

            roots = sorted({PurePosixPath(item.relative).parts[0] for item in items}, key=str.casefold)
            emit_transfer(
                self.events,
                transfer_id,
                "prepared",
                peer=peer_name,
                peer_ip=peer_ip,
                total=total,
                file_count=len(items),
                verify=verify,
                roots=roots,
            )

            sock = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            configure_stream_socket(sock)
            with self.state_lock:
                self.active_socket = sock

            emit_transfer(self.events, transfer_id, "phase", phase="Connecting", message=f"Opening a direct TCP connection to {peer_name}.")
            sock.bind(ipv6_scope_tuple(self.adapter.link_local, 0, self.adapter.if_index))
            sock.settimeout(10)
            sock.connect(ipv6_scope_tuple(peer_ip, TRANSFER_PORT, self.adapter.if_index))
            sock.settimeout(None)
            if self.cancel_event.is_set():
                raise TransferCancelled("Transfer cancelled while connecting.")
            emit_transfer(self.events, transfer_id, "connected", socket=socket_diagnostics(sock))
            threading.Thread(
                target=read_responses,
                daemon=True,
                name="sender-response-monitor",
            ).start()

            send_frame(
                sock,
                {
                    "magic": MAGIC,
                    "type": "offer",
                    "version": PROTOCOL_VERSION,
                    "transfer_id": transfer_id,
                    "hostname": socket.gethostname(),
                    "total_bytes": total,
                    "file_count": len(items),
                    "verify": verify,
                    "roots": roots,
                },
            )
            emit_transfer(
                self.events,
                transfer_id,
                "phase",
                phase="Waiting for receiver",
                message="The receiver must choose a destination folder and accept.",
            )
            reply = wait_for_response()
            if reply.get("type") == "cancel":
                raise TransferCancelled(str(reply.get("reason") or "The receiver cancelled the transfer."))
            if reply.get("type") == "reject":
                raise TransferRejected(str(reply.get("reason") or "The receiver declined the transfer."))
            if reply.get("type") != "accept":
                raise RuntimeError("The receiver returned an invalid response.")

            remote_destination = str(reply.get("destination") or "Chosen on receiver")
            disk_total = int(reply.get("disk_total") or 0)
            disk_free = int(reply.get("disk_free") or 0)
            storage = {
                "Receiver volume total": f"{human_bytes(disk_total)} ({disk_total} bytes)" if disk_total else "Unavailable",
                "Receiver volume free before transfer": (
                    f"{human_bytes(disk_free)} ({disk_free} bytes)" if disk_free else "Unavailable"
                ),
                "Receiver free space after payload (estimated)": (
                    f"{human_bytes(disk_free - total)} ({disk_free - total} bytes)" if disk_free else "Unavailable"
                ),
            }
            emit_transfer(
                self.events,
                transfer_id,
                "start",
                direction="Sending",
                peer=peer_name,
                peer_ip=peer_ip,
                total=total,
                file_count=len(items),
                verify=verify,
                destination=remote_destination,
                socket=socket_diagnostics(sock),
                storage=storage,
            )

            sent_total = 0
            started = time.monotonic()
            reusable = bytearray(BLOCK_SIZE)
            view = memoryview(reusable)

            for file_index, item in enumerate(items, 1):
                if self.cancel_event.is_set():
                    raise TransferCancelled("Transfer cancelled by the sender.")

                send_frame(sock, {"type": "file", "path": item.relative, "size": item.size})
                emit_transfer(
                    self.events,
                    transfer_id,
                    "file_start",
                    index=file_index,
                    file_count=len(items),
                    path=item.relative,
                    source=str(item.source),
                    size=item.size,
                )
                hasher = hashlib.sha256() if verify else None
                file_done = 0
                last_progress = 0.0

                with open(item.source, "rb", buffering=0) as f:
                    while True:
                        if self.cancel_event.is_set():
                            raise TransferCancelled("Transfer cancelled by the sender.")

                        n = f.readinto(reusable)
                        if not n:
                            break

                        block = view[:n]
                        if hasher:
                            hasher.update(block)
                        sock.sendall(block)
                        file_done += n
                        sent_total += n

                        now = time.monotonic()
                        if now - last_progress >= 0.10:
                            emit_transfer(
                                self.events,
                                transfer_id,
                                "progress",
                                done=sent_total,
                                total=total,
                                current_file_done=file_done,
                                current_file_size=item.size,
                                current=item.relative,
                            )
                            last_progress = now

                digest = hasher.hexdigest() if hasher else ""
                if verify:
                    send_frame(sock, {"type": "hash", "sha256": digest})

                ack = wait_for_response()
                if ack.get("type") == "cancel":
                    raise TransferCancelled(str(ack.get("reason") or "The receiver cancelled the transfer."))
                if ack.get("type") != "file_ok":
                    raise RuntimeError(f"Receiver did not confirm {item.relative}")
                emit_transfer(
                    self.events,
                    transfer_id,
                    "file_done",
                    index=file_index,
                    path=item.relative,
                    size=item.size,
                    sha256=digest,
                )

            send_frame(sock, {"type": "done"})
            final = wait_for_response()
            if final.get("type") == "cancel":
                raise TransferCancelled(str(final.get("reason") or "The receiver cancelled the transfer."))
            if final.get("type") != "done_ok":
                raise RuntimeError("Receiver did not confirm transfer completion.")

            elapsed = max(time.monotonic() - started, 0.001)
            emit_transfer(self.events, transfer_id, "done", done=sent_total, average_bps=sent_total / elapsed)

        except TransferRejected as exc:
            emit_transfer(self.events, transfer_id, "rejected", message=str(exc))
        except TransferCancelled as exc:
            emit_transfer(self.events, transfer_id, "cancelled", message=str(exc))
        except Exception as exc:
            remote_cancel = remote_cancel_reason[0] if remote_cancel_event.is_set() else ""
            action = "cancelled" if self.cancel_event.is_set() or remote_cancel else "failed"
            emit_transfer(
                self.events,
                transfer_id,
                action,
                message=remote_cancel or str(exc),
                error_type=type(exc).__name__,
            )
        finally:
            with self.state_lock:
                self.active_socket = None
                self.active_transfer_id = None
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass
            self.coordinator.release()


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


class TransferDialog(tk.Toplevel):
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
        self.parent = parent
        self.transfer_id = transfer_id
        self.cancel_callback = cancel_callback
        self.close_callback = close_callback
        self.finished = False
        self.cancel_requested = False
        self.minimized = False
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

        self.title(f"{APP_NAME} — {direction} diagnostics")
        self.monitor_dpi, self.ui_scale = configure_tk_dpi(self)
        set_scaled_window_geometry(self, 980, 740, 820, 620, self.ui_scale)
        self.configure(background=COLOR_BG)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._cancel_or_close)

        self.phase_var = tk.StringVar(value="Preparing")
        self.message_var = tk.StringVar(value="Starting transfer diagnostics…")
        self.percent_var = tk.StringVar(value="0.0%")
        self.transferred_var = tk.StringVar(value="0 B")
        self.rate_var = tk.StringVar(value="Waiting")
        self.eta_var = tk.StringVar(value="Unknown")
        self.elapsed_var = tk.StringVar(value="0s")

        self._build_ui(direction)
        self.set_details(
            {
                "Transfer ID": transfer_id,
                "Direction": direction,
                "State": "Preparing",
                "Phase": "Preparing",
                "Protocol": f"{MAGIC} / version {PROTOCOL_VERSION}",
                "App session ID": SESSION_ID,
                "Dialog opened": datetime.now().astimezone().isoformat(timespec="seconds"),
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
                "Peer IPv6": peer_ip,
                "Transport": "TCP over IPv6 link-local / direct physical Ethernet",
                "Adapter": adapter.name,
                "Interface index": str(adapter.if_index),
                "Local IPv6": f"{adapter.link_local}%{adapter.if_index}",
                "Adapter MAC": adapter.mac or "Unavailable",
                "Negotiated link speed": adapter.link_speed or "Unavailable",
                "Receive link capacity": f"{human_bytes(adapter.rx_bps / 8)}/s ({adapter.rx_bps} bit/s)",
                "Transmit link capacity": f"{human_bytes(adapter.tx_bps / 8)}/s ({adapter.tx_bps} bit/s)",
                "Default gateway": "Present" if adapter.has_gateway else "None (direct-link requirement met)",
                "Discovery endpoint": f"[{DISCOVERY_GROUP}%{adapter.if_index}]:{DISCOVERY_PORT}/UDP",
                "Transfer port": f"{TRANSFER_PORT}/TCP",
                "Application block size": f"{human_bytes(BLOCK_SIZE)} ({BLOCK_SIZE} bytes)",
                "Requested socket buffer": f"{human_bytes(SOCKET_BUFFER)} ({SOCKET_BUFFER} bytes)",
                "Integrity verification": "SHA-256 enabled" if verify else "Disabled",
                "Selected source paths": " | ".join(str(path) for path in (sources or [])) or "Supplied by sender",
                "Power behavior": "Automatic system sleep blocked; display sleep is allowed",
                "Minimized behavior": "Transfer threads continue while the window is minimized",
                "Actual sleep/hibernation": "Networking pauses; the transfer resumes only if Windows preserves the TCP connection",
                "Cancellation behavior": "Immediately closes the active transfer socket",
            }
        )
        self.add_log(f"Diagnostics opened for {direction.lower()} transfer {transfer_id}.")
        self.after(250, self._tick)
        self.after_idle(self._activate_modal)

    def _build_ui(self, direction: str) -> None:
        outer = ttk.Frame(self, style="App.TFrame", padding=22)
        outer.pack(fill="both", expand=True)

        heading = ttk.Frame(outer, style="App.TFrame")
        heading.pack(fill="x")
        mark_color = COLOR_ACCENT if direction == "Sending" else COLOR_CYAN
        mark = tk.Label(
            heading,
            text="↑" if direction == "Sending" else "↓",
            bg=mark_color,
            fg="#FFFFFF" if direction == "Sending" else COLOR_BG,
            font=("Segoe UI", 18, "bold"),
            width=2,
            height=1,
        )
        mark.pack(side="left", padx=(0, 12))
        title_stack = ttk.Frame(heading, style="App.TFrame")
        title_stack.pack(side="left")
        ttk.Label(title_stack, text=direction, style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_stack, text=f"Transfer {self.transfer_id[:8]}", style="Subtitle.TLabel").pack(anchor="w")
        self.phase_label = ttk.Label(heading, textvariable=self.phase_var, style="Phase.TLabel")
        self.phase_label.pack(side="right")
        ttk.Label(outer, textvariable=self.message_var, style="Subtitle.TLabel", wraplength=900).pack(
            anchor="w", pady=(12, 12)
        )

        self.progress = ttk.Progressbar(outer, maximum=100, style="Modern.Horizontal.TProgressbar")
        self.progress.pack(fill="x")
        ttk.Label(outer, textvariable=self.percent_var, style="AccentText.TLabel").pack(anchor="e", pady=(4, 10))

        metrics = ttk.Frame(outer, style="App.TFrame")
        metrics.pack(fill="x", pady=(0, 12))
        for column, (label, variable) in enumerate(
            (
                ("Transferred", self.transferred_var),
                ("Current speed", self.rate_var),
                ("ETA", self.eta_var),
                ("Elapsed", self.elapsed_var),
            )
        ):
            box = ttk.Frame(metrics, style="Card.TFrame", padding=(13, 9))
            box.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 5, 0))
            ttk.Label(box, text=label.upper(), style="MetricLabel.TLabel").pack(anchor="w")
            ttk.Label(box, textvariable=variable, style="MetricValue.TLabel").pack(anchor="w", pady=(3, 0))
            metrics.columnconfigure(column, weight=1)

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)

        details_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=7)
        log_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=7)
        notebook.add(details_tab, text="  All diagnostics  ")
        notebook.add(log_tab, text="  Activity log  ")

        self.detail_tree = ttk.Treeview(
            details_tab,
            columns=("value",),
            show="tree headings",
            selectmode="browse",
            height=8,
        )
        self.detail_tree.heading("#0", text="Field")
        self.detail_tree.heading("value", text="Value")
        self.detail_tree.column("#0", width=220, minwidth=150, stretch=False)
        self.detail_tree.column("value", width=620, minwidth=250, stretch=True)
        detail_scroll = ttk.Scrollbar(details_tab, orient="vertical", command=self.detail_tree.yview)
        self.detail_tree.configure(yscrollcommand=detail_scroll.set)
        self.detail_tree.pack(side="left", fill="both", expand=True)
        detail_scroll.pack(side="right", fill="y")

        self.log_text = tk.Text(
            log_tab,
            wrap="word",
            state="disabled",
            height=8,
            font=("Cascadia Mono", 9),
            bg=COLOR_PANEL,
            fg=COLOR_TEXT,
            insertbackground=COLOR_TEXT,
            selectbackground=COLOR_ACCENT,
            selectforeground="#FFFFFF",
            relief="flat",
            borderwidth=0,
            padx=10,
            pady=10,
        )
        log_scroll = ttk.Scrollbar(log_tab, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scroll.pack(side="right", fill="y")

        power_note = ttk.Frame(outer, style="Card.TFrame", padding=(12, 8))
        power_note.pack(fill="x", pady=(12, 8))
        ttk.Label(power_note, text="◐", style="CardTitle.TLabel").pack(side="left", padx=(0, 9))
        ttk.Label(
            power_note,
            text="Keep-awake is active. The screen may turn off; manually forcing sleep still pauses networking.",
            style="CardMuted.TLabel",
            wraplength=820,
        ).pack(side="left", fill="x", expand=True)

        self.actions = ttk.Frame(outer, style="App.TFrame")
        self.actions.pack(fill="x")
        ttk.Button(
            self.actions,
            text="Copy diagnostics",
            command=self.copy_diagnostics,
            style="Ghost.TButton",
        ).pack(side="left")
        ttk.Button(self.actions, text="Minimize", command=self._minimize, style="Ghost.TButton").pack(
            side="left", padx=(8, 0)
        )
        self.action_button = ttk.Button(
            self.actions,
            text="Cancel transfer",
            command=self._cancel_or_close,
            style="Danger.TButton",
        )
        self.action_button.pack(side="right")

    def offer_destination_choice(self, callback) -> None:
        if self.accept_button:
            return

        def choose() -> None:
            if self.finished or self.cancel_requested:
                return
            self.accept_button.config(state="disabled")
            callback()

        self.accept_button = ttk.Button(
            self.actions,
            text="Choose destination & accept",
            command=choose,
            style="Cyan.TButton",
        )
        self.accept_button.pack(side="right", padx=(0, 8))

    def _activate_modal(self) -> None:
        if not self.winfo_exists():
            return
        self.deiconify()
        self.lift()
        self.focus_force()
        self.grab_set()

    def set_detail(self, name: str, value) -> None:
        text_value = str(value)
        self.details[name] = text_value
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

        elif action == "prepared":
            self.set_details(
                {
                    "Peer computer": data.get("peer", "Unknown"),
                    "Peer IPv6": data.get("peer_ip", "Unknown"),
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
            self.transfer_started_monotonic = time.monotonic()
            self.last_progress_monotonic = None
            self.set_details(
                {
                    "State": "Transferring",
                    "Peer computer": data.get("peer", "Unknown"),
                    "Peer IPv6": data.get("peer_ip", "Unknown"),
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
            self.set_detail("Average speed", f"{human_bytes(data.get('average_bps', 0))}/s")
            if data.get("destination"):
                self.set_detail("Receiver destination", data["destination"])
            self._finish("Completed", "Transfer completed and was confirmed by both laptops.")

        elif action == "rejected":
            self._finish("Declined", str(data.get("message") or "Transfer declined."))

        elif action == "cancelled":
            if data.get("destination"):
                self.set_detail("Partial data location", data["destination"])
            self._finish("Cancelled", str(data.get("message") or "Transfer cancelled."))

        elif action == "failed":
            if data.get("error_type"):
                self.set_detail("Error type", data["error_type"])
            if data.get("destination"):
                self.set_detail("Partial data location", data["destination"])
            self._finish("Failed", str(data.get("message") or "Transfer failed."))

    def _apply_progress(self, data: dict) -> None:
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
        self.action_button.config(text="Close", state="normal", style="Accent.TButton")

    def _tick(self) -> None:
        if not self.winfo_exists():
            return
        start = self.transfer_started_monotonic or self.created_monotonic
        elapsed = time.monotonic() - start
        self.elapsed_var.set(human_duration(elapsed))
        self.set_detail("Elapsed time", human_duration(elapsed))
        self.set_detail("Seconds since last activity", f"{max(time.monotonic() - self.last_activity_monotonic, 0):.1f}")
        self.after(250, self._tick)

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

    def _minimize(self) -> None:
        if self.minimized:
            return
        self.minimized = True
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.withdraw()
        self.parent.iconify()
        self.after(250, self._watch_for_restore)

    def _watch_for_restore(self) -> None:
        if not self.winfo_exists() or not self.minimized:
            return
        if self.parent.state() != "iconic":
            self.minimized = False
            self._activate_modal()
            return
        self.after(250, self._watch_for_restore)

    def _close(self) -> None:
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.close_callback(self)
        self.destroy()


class EthernetSetupDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk):
        super().__init__(parent)
        self.parent = parent
        self.title(f"{APP_NAME} — Ethernet setup")
        self.monitor_dpi, self.ui_scale = configure_tk_dpi(self)
        set_scaled_window_geometry(self, 620, 350, 560, 320, self.ui_scale)
        self.configure(background=COLOR_BG)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", lambda: None)

        outer = ttk.Frame(self, style="App.TFrame", padding=24)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x")
        tk.Label(
            header,
            text="⚙",
            bg=COLOR_ACCENT,
            fg="#FFFFFF",
            font=("Segoe UI Symbol", 18),
            padx=10,
            pady=7,
        ).pack(side="left", padx=(0, 12))
        heading = ttk.Frame(header, style="App.TFrame")
        heading.pack(side="left")
        ttk.Label(heading, text="Configuring direct Ethernet", style="Title.TLabel").pack(anchor="w")
        ttk.Label(heading, text="A Windows administrator prompt may appear", style="Subtitle.TLabel").pack(anchor="w")

        self.progress = ttk.Progressbar(outer, mode="indeterminate", style="Modern.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(22, 16))
        self.progress.start(12)

        card = ttk.Frame(outer, style="Card.TFrame", padding=16)
        card.pack(fill="both", expand=True)
        ttk.Label(card, text="EtherDrop is checking and configuring:", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(
            card,
            text=(
                "✓ Physical wired adapter with no gateway\n"
                "✓ IPv6 link-local communication\n"
                "✓ Direct-link-only firewall rules\n"
                "✓ Supported Ethernet power settings"
            ),
            style="CardMuted.TLabel",
            justify="left",
        ).pack(anchor="w", pady=(9, 0))
        ttk.Label(
            outer,
            text="Wi-Fi, IPv4, DNS, DHCP, MTU, and router settings are never changed.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(12, 0))

        self.after_idle(self._activate)

    def _activate(self) -> None:
        self.lift()
        self.focus_force()
        self.grab_set()

    def close(self) -> None:
        self.progress.stop()
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()


class EtherDropApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.monitor_dpi, self.ui_scale = configure_tk_dpi(self)
        configure_modern_theme(self)
        self.title(APP_NAME)
        set_scaled_window_geometry(self, 840, 700, 760, 610, self.ui_scale)

        self.events: queue.Queue = queue.Queue()
        self.coordinator = threading.Lock()
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
        self.transfer_dialog: TransferDialog | None = None
        self.active_transfer_id: str | None = None
        self.keep_awake_active = False
        self.scan_token = 0
        self.listbox: tk.Listbox | None = None
        self.send_button: ttk.Button | None = None
        self.progress: ttk.Progressbar | None = None
        self.link_label: ttk.Label | None = None
        self.setup_button: ttk.Button | None = None
        self.setup_dialog: EthernetSetupDialog | None = None
        self.setup_in_progress = False
        self.update_busy = False
        self._closing = False
        self.update_installing = False
        self.update_button: ttk.Button | None = None
        self.update_dialog: tk.Toplevel | None = None
        self.release_notes_dialog: tk.Toplevel | None = None
        self.update_state = load_update_state()
        self.update_var = tk.StringVar(value="Check for updates")

        self.status_var = tk.StringVar(value="Connect the two laptops directly with Ethernet.")
        self.adapter_var = tk.StringVar(value="Ethernet: not detected")
        self.peer_var = tk.StringVar(value="Peer: searching…")
        self.link_var = tk.StringVar(value="○ NOT CONNECTED")
        self.sync_var = tk.StringVar(value="Waiting for a live heartbeat from the other laptop.")
        self.speed_var = tk.StringVar(value="")
        self.current_var = tk.StringVar(value="")
        self.verify_var = tk.BooleanVar(value=False)

        self._build_role_ui()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(100, self._drain_events)
        self.after(250, self._connection_tick)
        self.after(500, self.check_for_updates)
        self.after(300, self._show_startup_notes)

    def _clear_window(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self.link_label = None
        self.setup_button = None
        self.update_button = None

    def _build_update_button(self, parent: ttk.Frame) -> None:
        controls = ttk.Frame(parent, style="App.TFrame")
        controls.pack(side="right")
        self.update_button = ttk.Button(
            controls, textvariable=self.update_var, command=lambda: self.check_for_updates(manual=True),
        )
        self.update_button.pack(anchor="e")
        self.update_button.configure(state="disabled" if self.update_busy else "normal")
        ttk.Label(controls, text=f"v{APP_VERSION}", style="Subtitle.TLabel").pack(anchor="e", pady=(3, 0))

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
        if not getattr(sys, "frozen", False):
            messagebox.showinfo(
                APP_NAME, f"{release['version']} is available. Self-updating is available in the standalone EXE.\n"
                f"Download it from https://github.com/{GITHUB_REPOSITORY}/releases/latest", parent=self,
            )
            return
        if not messagebox.askyesno(
            APP_NAME, f"EtherDrop {release['version']} is available (current: v{APP_VERSION}).\n\n"
            "Download it now? EtherDrop will close briefly, update itself, and reopen.", parent=self,
        ):
            return
        self._set_update_busy(True, "Downloading…")
        self.update_installing = True
        dialog = tk.Toplevel(self)
        self.update_dialog = dialog
        dialog.title("Updating EtherDrop")
        configure_modern_theme(dialog)
        dialog.transient(self)
        dialog.protocol("WM_DELETE_WINDOW", lambda: None)
        content = ttk.Frame(dialog, style="App.TFrame", padding=24)
        content.pack(fill="both", expand=True)
        ttk.Label(content, text=f"Downloading {release['version']}", style="CardTitle.TLabel").pack(anchor="w")
        ttk.Label(content, textvariable=self.update_var, style="Subtitle.TLabel").pack(anchor="w", pady=(12, 0))
        ttk.Label(content, text="EtherDrop will restart when the download finishes.", style="Subtitle.TLabel").pack(pady=(12, 0))
        dialog.grab_set()

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

    def _show_release_notes(self, title: str, notes: str) -> None:
        dialog = tk.Toplevel(self)
        self.release_notes_dialog = dialog
        dialog.title(f"{APP_NAME} — What's new")
        configure_modern_theme(dialog)
        set_scaled_window_geometry(dialog, 620, 440, 440, 320, self.ui_scale)
        dialog.transient(self)
        outer = ttk.Frame(dialog, style="App.TFrame", padding=24)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=title, style="Title.TLabel").pack(anchor="w")
        ttk.Label(outer, text=f"EtherDrop v{APP_VERSION}", style="Subtitle.TLabel").pack(anchor="w", pady=(4, 16))
        body = ttk.Frame(outer, style="Panel.TFrame")
        body.pack(fill="both", expand=True)
        text = tk.Text(
            body, wrap="word", bg=COLOR_PANEL, fg=COLOR_TEXT, font=("Segoe UI", 10),
            relief="flat", padx=14, pady=12, borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=text.yview)
        scrollbar.pack(side="right", fill="y")
        text.pack(fill="both", expand=True)
        text.configure(yscrollcommand=scrollbar.set)
        text.insert("1.0", notes)
        text.configure(state="disabled")

        def close():
            self.update_state["seen_version"] = APP_VERSION
            try:
                save_update_state(self.update_state)
            except OSError:
                pass
            self.release_notes_dialog = None
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", close)
        ttk.Button(outer, text="Continue", command=close, style="Accent.TButton").pack(anchor="e", pady=(16, 0))
        dialog.grab_set()

    def _handle_update_error(self, message: str, manual: bool) -> None:
        if self.update_dialog:
            self.update_dialog.destroy()
            self.update_dialog = None
        self.update_installing = False
        self._set_update_busy(False)
        if manual:
            messagebox.showerror(APP_NAME, f"Could not update EtherDrop.\n\n{message}", parent=self)

    def _build_role_ui(self) -> None:
        self._clear_window()
        set_scaled_window_geometry(self, 820, 600, 720, 560, self.ui_scale)
        outer = ttk.Frame(self, style="App.TFrame", padding=34)
        outer.pack(fill="both", expand=True)

        update_header = ttk.Frame(outer, style="App.TFrame")
        update_header.pack(fill="x")
        self._build_update_button(update_header)

        brand = tk.Label(
            outer,
            text="ED",
            bg=COLOR_ACCENT,
            fg="#FFFFFF",
            font=("Segoe UI", 13, "bold"),
            width=3,
            height=1,
            padx=4,
            pady=7,
        )
        brand.pack(anchor="center", pady=(6, 14))
        ttk.Label(outer, text="EtherDrop", style="Hero.TLabel").pack(anchor="center")
        ttk.Label(
            outer,
            text="Direct cable. Full speed. Zero cloud.",
            style="Subtitle.TLabel",
        ).pack(anchor="center", pady=(4, 6))
        ttk.Label(outer, text="Choose this laptop’s role", style="Title.TLabel").pack(
            anchor="center", pady=(12, 22)
        )

        choices = ttk.Frame(outer, style="App.TFrame")
        choices.pack(fill="both", expand=True)
        choices.columnconfigure(0, weight=1)
        choices.columnconfigure(1, weight=1)
        choices.rowconfigure(0, weight=1)

        send_border = tk.Frame(choices, bg=COLOR_BORDER, padx=1, pady=1)
        send_border.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        send_box = tk.Frame(send_border, bg=COLOR_SURFACE, padx=22, pady=20)
        send_box.pack(fill="both", expand=True)
        tk.Label(send_box, text="↑", bg=COLOR_SURFACE, fg=COLOR_ACCENT, font=("Segoe UI", 25, "bold")).pack(
            anchor="w"
        )
        tk.Label(send_box, text="Send", bg=COLOR_SURFACE, fg=COLOR_TEXT, font=("Segoe UI", 16, "bold")).pack(
            anchor="w", pady=(7, 3)
        )
        tk.Label(
            send_box,
            text="Choose files and folders, then push them across the direct Ethernet link.",
            bg=COLOR_SURFACE,
            fg=COLOR_MUTED,
            font=("Segoe UI", 10),
            justify="left",
            wraplength=290,
        ).pack(anchor="w")
        tk.Label(
            send_box,
            text="SELECT  •  REVIEW  •  SEND",
            bg=COLOR_SURFACE,
            fg=COLOR_ACCENT,
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", pady=(15, 12))
        ttk.Button(
            send_box,
            text="Continue as sender  →",
            command=lambda: self.select_role("sender"),
            style="Accent.TButton",
        ).pack(fill="x", side="bottom")

        receive_border = tk.Frame(choices, bg=COLOR_BORDER, padx=1, pady=1)
        receive_border.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        receive_box = tk.Frame(receive_border, bg=COLOR_SURFACE, padx=22, pady=20)
        receive_box.pack(fill="both", expand=True)
        tk.Label(receive_box, text="↓", bg=COLOR_SURFACE, fg=COLOR_CYAN, font=("Segoe UI", 25, "bold")).pack(
            anchor="w"
        )
        tk.Label(
            receive_box,
            text="Receive",
            bg=COLOR_SURFACE,
            fg=COLOR_TEXT,
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", pady=(7, 3))
        tk.Label(
            receive_box,
            text="Review every offer and choose exactly where the incoming transfer is saved.",
            bg=COLOR_SURFACE,
            fg=COLOR_MUTED,
            font=("Segoe UI", 10),
            justify="left",
            wraplength=290,
        ).pack(anchor="w")
        tk.Label(
            receive_box,
            text="APPROVE  •  LOCATE  •  RECEIVE",
            bg=COLOR_SURFACE,
            fg=COLOR_CYAN,
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w", pady=(15, 12))
        ttk.Button(
            receive_box,
            text="Continue as receiver  →",
            command=lambda: self.select_role("receiver"),
            style="Cyan.TButton",
        ).pack(fill="x", side="bottom")

        ttk.Label(
            outer,
            text="Choose opposite roles on the two laptops — EtherDrop handles the pairing.",
            style="Subtitle.TLabel",
        ).pack(anchor="center", pady=(18, 0))

    def select_role(self, role: str) -> None:
        if role not in ("sender", "receiver"):
            return
        self.shutdown_services()
        self.role = role
        self._build_main_ui()
        self.after(100, self.rescan)

    def _build_main_ui(self) -> None:
        self._clear_window()
        set_scaled_window_geometry(self, 860, 730, 760, 610, self.ui_scale)
        outer = ttk.Frame(self, style="App.TFrame", padding=24)
        outer.pack(fill="both", expand=True)

        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x")
        brand = tk.Label(
            header,
            text="ED",
            bg=COLOR_ACCENT,
            fg="#FFFFFF",
            font=("Segoe UI", 10, "bold"),
            padx=9,
            pady=7,
        )
        brand.pack(side="left", padx=(0, 11))
        title_stack = ttk.Frame(header, style="App.TFrame")
        title_stack.pack(side="left")
        ttk.Label(title_stack, text="EtherDrop", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_stack, text="Direct Ethernet transfer", style="Subtitle.TLabel").pack(anchor="w")
        ttk.Label(
            header,
            text="SENDER" if self.role == "sender" else "RECEIVER",
            style="RoleBadge.TLabel" if self.role == "sender" else "ReceiverBadge.TLabel",
        ).pack(side="right")

        info = ttk.Frame(outer, style="Card.TFrame", padding=16)
        info.pack(fill="x", pady=(18, 0))
        info_top = ttk.Frame(info, style="Card.TFrame")
        info_top.pack(fill="x")
        self.link_label = ttk.Label(info_top, textvariable=self.link_var, style="Waiting.TLabel")
        self.link_label.pack(side="left")
        tk.Label(
            info_top,
            text="DIRECT ETHERNET",
            bg=COLOR_SURFACE_ALT,
            fg=COLOR_MUTED,
            font=("Segoe UI", 8, "bold"),
            padx=9,
            pady=4,
        ).pack(side="right")
        ttk.Label(info, textvariable=self.adapter_var, style="CardMuted.TLabel").pack(anchor="w", pady=(9, 0))
        ttk.Label(info, textvariable=self.peer_var, style="Card.TLabel").pack(anchor="w", pady=(5, 0))
        ttk.Label(info, textvariable=self.sync_var, style="CardMuted.TLabel").pack(anchor="w", pady=(3, 0))
        connection_buttons = ttk.Frame(info, style="Card.TFrame")
        connection_buttons.pack(fill="x", pady=(11, 0))
        ttk.Button(connection_buttons, text="←  Change role", command=self._change_role, style="Ghost.TButton").pack(
            side="left"
        )
        self.setup_button = ttk.Button(
            connection_buttons,
            text="Auto-configure Ethernet",
            command=self.auto_configure_ethernet,
            style="Cyan.TButton",
        )
        self.setup_button.pack(side="right")
        ttk.Button(connection_buttons, text="Rescan", command=self.rescan).pack(side="right", padx=(0, 8))

        if self.role == "sender":
            files = ttk.Frame(outer, style="Card.TFrame", padding=16)
            files.pack(fill="both", expand=True, pady=(14, 0))

            section_head = ttk.Frame(files, style="Card.TFrame")
            section_head.pack(fill="x", pady=(0, 10))
            section_title = ttk.Frame(section_head, style="Card.TFrame")
            section_title.pack(side="left")
            ttk.Label(section_title, text="Transfer contents", style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(section_title, text="Add any mix of files and folders", style="CardMuted.TLabel").pack(anchor="w")

            buttons = ttk.Frame(section_head, style="Card.TFrame")
            buttons.pack(side="right")
            ttk.Button(buttons, text="＋ Files", command=self.add_files, style="Accent.TButton").pack(side="left")
            ttk.Button(buttons, text="＋ Folder", command=self.add_folder).pack(side="left", padx=(7, 0))
            ttk.Button(buttons, text="Clear", command=self.clear_selection, style="Ghost.TButton").pack(
                side="left", padx=(7, 0)
            )

            self.listbox = tk.Listbox(
                files,
                height=6,
                activestyle="none",
                bg=COLOR_PANEL,
                fg=COLOR_TEXT,
                selectbackground=COLOR_ACCENT,
                selectforeground="#FFFFFF",
                highlightbackground=COLOR_BORDER,
                highlightcolor=COLOR_ACCENT,
                highlightthickness=1,
                relief="flat",
                borderwidth=0,
                font=("Segoe UI", 10),
            )
            self.listbox.pack(fill="both", expand=True, pady=(0, 10), ipady=5)

            opts = ttk.Frame(files, style="Card.TFrame")
            opts.pack(fill="x")
            ttk.Checkbutton(
                opts,
                text="Verify every file with SHA-256",
                variable=self.verify_var,
                style="Card.TCheckbutton",
            ).pack(side="left")

            self.send_button = ttk.Button(
                opts,
                text="Send now  →",
                command=self.send_selected,
                state="disabled",
                style="Accent.TButton",
            )
            self.send_button.pack(side="right")
            self.refresh_list()
        else:
            waiting = ttk.Frame(outer, style="Card.TFrame", padding=22)
            waiting.pack(fill="both", expand=True, pady=(14, 0))
            waiting_body = ttk.Frame(waiting, style="Card.TFrame")
            waiting_body.pack(fill="both", expand=True, pady=(12, 8))
            tk.Label(
                waiting_body,
                text="↓",
                bg=COLOR_SURFACE,
                fg=COLOR_CYAN,
                font=("Segoe UI", 34, "bold"),
            ).pack(side="left", padx=(18, 30))
            waiting_copy = ttk.Frame(waiting_body, style="Card.TFrame")
            waiting_copy.pack(side="left", fill="both", expand=True)
            ttk.Label(waiting_copy, text="Listening for the sender", style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(
                waiting_copy,
                text=(
                    "An approval dashboard appears when an offer arrives. You choose the destination before "
                    "EtherDrop accepts a single byte."
                ),
                style="CardMuted.TLabel",
                wraplength=540,
                justify="left",
            ).pack(anchor="w", pady=(6, 0))
            safety = ttk.Frame(waiting_copy, style="Panel.TFrame", padding=(14, 8))
            safety.pack(anchor="w", pady=(13, 0))
            ttk.Label(
                safety,
                text="✓  Every transfer requires your approval",
                background=COLOR_PANEL,
                foreground=COLOR_SUCCESS,
                font=("Segoe UI", 9, "bold"),
            ).pack()
            ttk.Label(
                waiting_copy,
                text="Cancel the folder picker to decline • Cancel during transfer to stop both laptops",
                style="CardMuted.TLabel",
                wraplength=540,
                justify="left",
            ).pack(anchor="w", pady=(11, 0))
            self.listbox = None
            self.send_button = None

        progress_box = ttk.Frame(outer, style="Card.TFrame", padding=(16, 12))
        progress_box.pack(fill="x", pady=(14, 0))
        progress_head = ttk.Frame(progress_box, style="Card.TFrame")
        progress_head.pack(fill="x")
        ttk.Label(progress_head, text="Transfer summary", style="CardTitle.TLabel").pack(side="left")
        ttk.Label(progress_head, textvariable=self.speed_var, style="MetricValue.TLabel").pack(side="right")
        self.progress = ttk.Progressbar(progress_box, maximum=100, style="Modern.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(9, 0))
        ttk.Label(progress_box, textvariable=self.status_var, style="Card.TLabel").pack(anchor="w", pady=(7, 0))
        ttk.Label(progress_box, textvariable=self.current_var, style="CardMuted.TLabel").pack(anchor="w", pady=(2, 0))

    def _change_role(self) -> None:
        self.shutdown_services()
        self.role = None
        self._build_role_ui()

    def _set_link_state(self, text: str, state: str) -> None:
        self.link_var.set(text)
        if self.link_label:
            style = {
                "synced": "Sync.TLabel",
                "lost": "Lost.TLabel",
                "waiting": "Waiting.TLabel",
            }.get(state, "Waiting.TLabel")
            self.link_label.config(style=style)

    def auto_configure_ethernet(self) -> None:
        if self.setup_in_progress:
            return
        if self.transfer_dialog and self.transfer_dialog.winfo_exists():
            messagebox.showerror(APP_NAME, "Finish or cancel the current transfer before configuring Ethernet.")
            return

        confirmed = messagebox.askyesno(
            f"{APP_NAME} — Auto-configure Ethernet",
            (
                "EtherDrop will request administrator permission and configure only an active physical Ethernet "
                "adapter with no default gateway.\n\n"
                "It will:\n"
                "• enable IPv6 link-local support if needed;\n"
                "• install firewall rules limited to EtherDrop, wired Ethernet, and link-local peers;\n"
                "• disable supported adapter selective-suspend settings;\n"
                "• restart Ethernet only if enabling IPv6 requires it.\n\n"
                "Wi-Fi, IPv4, DNS, DHCP, MTU, and router settings will not be changed.\n\n"
                "Make sure the cable goes directly to the other laptop. Continue?"
            ),
            icon="question",
        )
        if not confirmed:
            return

        self.setup_in_progress = True
        if self.setup_button:
            self.setup_button.config(state="disabled")
        self.shutdown_services()
        self._set_link_state("●  CONFIGURING", "waiting")
        self.status_var.set("Waiting for Ethernet configuration and administrator approval…")
        self.setup_dialog = EthernetSetupDialog(self)

        def worker() -> None:
            try:
                report = run_ethernet_autoconfigure(Path(sys.executable).resolve())
                self.events.put(("setup_done", report))
            except Exception as exc:
                self.events.put(("setup_error", str(exc)))

        threading.Thread(target=worker, daemon=True, name="ethernet-auto-setup").start()

    def _close_setup_dialog(self) -> None:
        if self.setup_dialog and self.setup_dialog.winfo_exists():
            self.setup_dialog.close()
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
        if self.setup_button:
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
        messagebox.showinfo(f"{APP_NAME} — Ethernet configured", "\n".join(lines), parent=self)
        self.status_var.set("Ethernet configuration completed. Rescanning the direct link…")
        self.after(200, self.rescan)

    def _handle_setup_error(self, message: str) -> None:
        self.setup_in_progress = False
        self._close_setup_dialog()
        if self.setup_button:
            self.setup_button.config(state="normal")
        self._set_link_state("●  SETUP NOT COMPLETED", "lost")
        self.status_var.set(message)
        messagebox.showerror(f"{APP_NAME} — Ethernet setup", message, parent=self)
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

    def rescan(self) -> None:
        if not self.role:
            return
        self.shutdown_services()
        self.scan_token += 1
        token = self.scan_token
        role = self.role
        self.adapter_var.set("Ethernet: scanning…")
        expected = "receiver" if role == "sender" else "sender"
        self.peer_var.set(f"Peer: searching for a {expected}…")
        self._set_link_state("●  SEARCHING", "waiting")
        self.sync_var.set("Waiting for a live heartbeat from the other laptop.")
        if self.send_button:
            self.send_button.config(state="disabled")
        self.update_idletasks()

        def worker():
            try:
                adapter = choose_direct_adapter()
                self.events.put(("adapter", token, role, adapter))
            except Exception as exc:
                self.events.put(("adapter_error", token, role, str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def _start_services(self, adapter: EthernetAdapter) -> None:
        if not self.role:
            return
        self.adapter = adapter
        self.discovery = DiscoveryService(adapter, self.events, self.role)
        if self.role == "receiver":
            self.receiver = ReceiverService(adapter, self.events, self.coordinator)
            self.receiver.start()
        else:
            self.sender = Sender(adapter, self.events, self.coordinator)
        self.discovery.start()

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(title="Choose files to send")
        for p in paths:
            path = Path(p)
            if path not in self.selected_paths:
                self.selected_paths.append(path)
        self.refresh_list()

    def add_folder(self) -> None:
        p = filedialog.askdirectory(title="Choose folder to send")
        if p:
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
        if not self.selected_paths:
            self.listbox.insert(tk.END, "  No files selected — add files or a folder to begin")
            self.listbox.itemconfig(0, foreground=COLOR_MUTED, selectbackground=COLOR_PANEL)
        else:
            for index, path in enumerate(self.selected_paths):
                item_type = "FOLDER" if path.is_dir() else "FILE"
                self.listbox.insert(tk.END, f"  {item_type:<6}  {path}")
                if path.is_dir():
                    self.listbox.itemconfig(index, foreground=COLOR_CYAN)
        self._refresh_send_state()

    def _refresh_send_state(self) -> None:
        if not self.send_button:
            return
        dialog_active = bool(self.transfer_dialog and self.transfer_dialog.winfo_exists())
        enabled = bool(self.peer_ip and self.selected_paths and self.sender and self.adapter and not dialog_active)
        self.send_button.config(state="normal" if enabled else "disabled")

    def send_selected(self) -> None:
        if not self.sender or not self.peer_ip or not self.peer_name:
            messagebox.showerror(APP_NAME, "No other EtherDrop laptop is connected.")
            return
        if not self.selected_paths:
            return

        self.send_button.config(state="disabled")
        self.progress["value"] = 0
        self.status_var.set("Preparing transfer…")
        self.speed_var.set("")
        transfer_id = self.sender.send(
            self.peer_ip,
            self.peer_name,
            list(self.selected_paths),
            bool(self.verify_var.get()),
        )
        if not transfer_id:
            messagebox.showerror(APP_NAME, "This laptop is already handling another transfer.")
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
    ) -> TransferDialog:
        if not self.adapter:
            raise RuntimeError("Ethernet adapter is unavailable.")
        self.active_transfer_id = transfer_id
        dialog = TransferDialog(
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
        self.transfer_dialog = dialog
        self.keep_awake_active, power_status = set_system_awake(True)
        dialog.set_detail("Windows keep-awake request", power_status)
        self._refresh_send_state()
        return dialog

    def _transfer_dialog_closed(self, dialog: TransferDialog) -> None:
        if self.transfer_dialog is dialog:
            self.transfer_dialog = None
            self.active_transfer_id = None
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
        dialog: TransferDialog,
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
            title="Choose the parent folder for this incoming transfer",
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
            decision.accept(Path(selected))
        else:
            dialog.set_phase("Declining", "No destination folder was selected; declining the transfer.")
            decision.reject("The receiver did not choose a destination folder.")

    def _handle_transfer_event(self, transfer_id: str, action: str, data: dict) -> None:
        if action == "incoming_offer":
            decision: IncomingTransferDecision = data["decision"]
            if self.update_installing:
                decision.reject("EtherDrop is installing an update. Please retry after it restarts.")
                return
            if self.role != "receiver" or not self.receiver:
                decision.reject("This laptop is not in receiver mode.")
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

                elif kind == "update_progress":
                    self.update_var.set(f"Downloading… {event[1] / event[2] * 100:.0f}%")

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

                elif kind == "adapter":
                    _, token, role, adapter = event
                    if token != self.scan_token or role != self.role:
                        continue
                    self._start_services(adapter)
                    speed = adapter.link_speed or human_bytes(min(adapter.rx_bps, adapter.tx_bps) / 8) + "/s"
                    self.adapter_var.set(f"Ethernet: {adapter.name} — {speed} — direct-link mode")
                    expected = "receiver" if self.role == "sender" else "sender"
                    self.status_var.set(f"Ethernet ready. Waiting for the {expected} laptop…")

                elif kind == "adapter_error":
                    _, token, role, message = event
                    if token != self.scan_token or role != self.role:
                        continue
                    self.adapter_var.set("Ethernet: unavailable")
                    self.status_var.set(message)
                    self.peer_var.set("Peer: not connected")
                    self._set_link_state("●  NOT CONNECTED", "lost")

                elif kind == "peer":
                    self.peer_name, self.peer_ip, self.peer_role = event[1], event[2], event[3]
                    self.peer_last_seen = time.monotonic()
                    label = self.peer_role.capitalize()
                    scope = self.adapter.if_index if self.adapter else 0
                    self.peer_var.set(f"{label}: {self.peer_name} — [{self.peer_ip}%{scope}]")
                    self._set_link_state("●  LINKED & SYNCED", "synced")
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
                    self.speed_var.set("")
                    self._refresh_send_state()

        except queue.Empty:
            pass
        finally:
            if not self._closing:
                self.after(100, self._drain_events)

    def _connection_tick(self) -> None:
        if self.peer_ip and self.peer_last_seen:
            age = max(time.monotonic() - self.peer_last_seen, 0.0)
            self.sync_var.set(f"Live peer heartbeat received {age:.1f}s ago — both clients are synchronized.")
            if self.transfer_dialog and self.transfer_dialog.winfo_exists():
                self.transfer_dialog.set_detail("Peer heartbeat age", f"{age:.1f}s")
        self.after(250, self._connection_tick)

    def _close(self) -> None:
        if self.update_installing:
            messagebox.showwarning(APP_NAME, "Please wait for the update download to finish.", parent=self.update_dialog or self)
            return
        if self.setup_in_progress:
            messagebox.showwarning(
                APP_NAME,
                "Ethernet configuration is still running. Complete or cancel the Windows administrator prompt first.",
                parent=self.setup_dialog or self,
            )
            return
        self.shutdown_services()
        self._release_keep_awake()
        self._closing = True
        self.destroy()


def main() -> None:
    if platform.system() != "Windows":
        print("EtherDrop is currently Windows-only.", file=sys.stderr)
        raise SystemExit(1)

    app = EtherDropApp()
    app.mainloop()


if __name__ == "__main__":
    main()
