import os
import time
import json
import requests
import subprocess
import psutil
import threading
import sys
from datetime import datetime, timezone
from rich.table import Table
from rich.console import Console
from rich.live import Live
from rich.text import Text
import ctypes
from ctypes import wintypes
import re
import shutil
import filecmp

# BF JSON CACHE (agar ringan)
BF_CACHE = {}
BF_CACHE_TIME = {}
BF_CACHE_INTERVAL = 10  # detik

OVA_PROCESS = None

# Base dir: compat dengan exec() wrapper, PyInstaller EXE, dan script langsung
if getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
elif '__file__' in vars():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))

# ----------------------------
# Config / Files
# ----------------------------
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
COOKIE_FILE = os.path.join(BASE_DIR, "cookies.txt")
SERVER_FILE = os.path.join(BASE_DIR, "servers.txt")
SAVES_FOLDER = os.path.join(BASE_DIR, "saves")
SAVES_FILE = os.path.join(SAVES_FOLDER, "saves.json")
DEATH_FILE = os.path.join(SAVES_FOLDER, "death.json")
MAX_DEATH_LAUNCH_ATTEMPT = 3
DEATH_COOKIES_FILE = os.path.join(SAVES_FOLDER, "deathcookies.json")
GAMEID_LIST_FILE = os.path.join(BASE_DIR, "daftar gameid.json")
PLAY_GAME_FOLDER = os.path.join(BASE_DIR, "play game.id.json")

console = Console()

# Default config
DEFAULT_CONFIG = {
    "gameId": 2753915549,
    "private_link": "",
    "Executor": "RonixExploit",
    "_ExecutorOptions": ["Seliware", "Potassium", "RonixExploit", "Velocity"],
    "first_check": 3,
    "launchDelay": 15,
    "accountLaunchCooldown": 30,
    "TotalInstance": 10,
    "FixedSize": "530x400",
    "ArrangeWindows": True,
    "ArrangeWindowsInterval": 60,
    "SortAccounts": True,
    "Kill Process > Ram": True,
    "Ram Usage (Each Process)": 3,
    "EnableRestart": False,
    "Restart": 1,
    "EnableMultiInstance": True,
    "FollowPlayer": False,
    "FollowPlayerUsername": "",
    "FollowCheckInterval": 30,
    "Show BF Stats": False,
    "change_and_close_game": False,
    "change_and_close_game_interval": 120,
    "change_akun": False,
    "change_akun_interval": 120
}

# Tambahkan di variabel global
SCRIPT_START_TIME = time.time()

def get_script_start_time():
    """Mendapatkan waktu mulai script"""
    return SCRIPT_START_TIME

# Tambahkan di bagian variabel global
GAME_CHANGE_STATE = {
    "last_change_time": 0,
    "is_changing": False,
    "change_start_time": 0
}

ACCOUNT_CHANGE_STATE = {
    "last_change_time": 0, 
    "is_changing": False,
    "change_start_time": 0
}

# Variabel untuk rotasi
CURRENT_GAME_INDEX = {}
ACCOUNT_ROTATION_INDEX = 0
LAST_GAME_CHANGE_TIME = 0
LAST_ACCOUNT_CHANGE_TIME = 0

def ensure_game_folders():
    """Membuat folder dan file yang diperlukan saat pertama kali menjalankan script"""
    try:
        # Buat folder play game.id.json
        if not os.path.exists(PLAY_GAME_FOLDER):
            os.makedirs(PLAY_GAME_FOLDER, exist_ok=True)
        
        # Buat file daftar gameid.json jika belum ada
        if not os.path.exists(GAMEID_LIST_FILE):
            default_gameids = [
                740581508, 2753915549, 8737899170, 920587237, 735030788, 
                1962086868, 142823291, 606849621, 370710243, 189707, 
                6699864173, 187796081, 6516141723, 286090429, 3527629287, 
                6872265039, 914010731, 2970742921, 2653064683, 3112115001, 
                6447795994, 292439477, 2217468224, 7047607440, 8560631822, 
                537413528, 4490140733, 5663993410, 7532473490, 6284583030, 
                8939734408, 8540346418, 6677985873, 4738548959
            ]
            with open(GAMEID_LIST_FILE, "w", encoding="utf-8") as f:
                json.dump(default_gameids, f, indent=2)
        
        return True
    except Exception as e:
        print(f"Error creating game folders: {e}")
        return False

# ----------------------------
# Executor Resolver
# ----------------------------
EXECUTOR_MAP = {
    "seliware": {
        "workspace": "seliware-workspace",
        "autoexec": "seliware-autoexec"
    },
    "potassium": {
        "workspace": os.path.join("Potassium", "workspace"),
        "autoexec": os.path.join("Potassium", "autoexec")
    },
    "wave": {
        "workspace": os.path.join("Wave", "workspace"),
        "autoexec": os.path.join("Wave", "autoexec")
    },
    "ronixexploit": {
        "workspace": os.path.join("RonixExploit", "Workspace"),
        "autoexec": os.path.join("RonixExploit", "AutoExecute")
    },
    "velocity": {
        "workspace": os.path.join("Velocity", "Workspace"),
        "autoexec": os.path.join("Velocity", "AutoExec")
    }
    
}

def resolve_executor_paths(cfg):
    executor_name = cfg.get("Executor", "Seliware").lower()

    if executor_name not in EXECUTOR_MAP:
        raise ValueError(f"Executor tidak dikenal: {executor_name}")

    local_appdata = os.environ.get("LOCALAPPDATA")
    if not local_appdata:
        raise RuntimeError("LOCALAPPDATA tidak ditemukan")

    exe_cfg = EXECUTOR_MAP[executor_name]

    workspace = os.path.join(local_appdata, exe_cfg["workspace"])
    autoexec = os.path.join(local_appdata, exe_cfg["autoexec"])

    # Auto create folder (anti error)
    os.makedirs(workspace, exist_ok=True)
    os.makedirs(autoexec, exist_ok=True)

    return workspace, autoexec

def sync_script_folder_to_autoexec(autoexec_folder):
    # Compat: PyInstaller EXE vs script biasa
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    script_folder = os.path.join(base_dir, "autoexec")

    if not os.path.isdir(script_folder):
        return

    os.makedirs(autoexec_folder, exist_ok=True)

    # --- COPY & UPDATE ---
    for root, _, files in os.walk(script_folder):
        rel = os.path.relpath(root, script_folder)
        target_root = autoexec_folder if rel == "." else os.path.join(autoexec_folder, rel)

        os.makedirs(target_root, exist_ok=True)

        for file in files:
            src = os.path.join(root, file)
            dst = os.path.join(target_root, file)

            if not os.path.exists(dst) or not filecmp.cmp(src, dst, shallow=False):
                shutil.copy2(src, dst)

    # --- DELETE EXTRA FILES ---
    for root, _, files in os.walk(autoexec_folder):
        rel = os.path.relpath(root, autoexec_folder)
        source_root = script_folder if rel == "." else os.path.join(script_folder, rel)

        for file in files:
            dst_file = os.path.join(root, file)
            src_file = os.path.join(source_root, file)

            if not os.path.exists(src_file):
                try:
                    os.remove(dst_file)
                except:
                    pass

def record_current_game(username, game_id):
    """Mencatat game yang sedang dimainkan oleh username"""
    try:
        file_path = os.path.join(PLAY_GAME_FOLDER, f"game.{username}.json")
        
        # Load existing games atau buat baru
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                games_played = json.load(f)
        else:
            games_played = []
        
        # Tambahkan game_id jika belum ada
        if game_id not in games_played:
            games_played.append(game_id)
        
        # Simpan kembali
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(games_played, f, indent=2)
        
        return True
    except Exception as e:
        add_log(f"Error recording game for {username}: {e}")
        return False

def update_game_name_cache(game_id, game_name=None):
    """Update cache nama game, atau clear cache untuk game_id tertentu"""
    global GAME_NAME_CACHE
    
    if game_name:
        # Update dengan nama baru
        GAME_NAME_CACHE[game_id] = game_name
    else:
        # Clear cache untuk game_id ini, agar di-refresh
        if game_id in GAME_NAME_CACHE:
            del GAME_NAME_CACHE[game_id]

def clear_all_game_cache():
    """Clear semua cache nama game"""
    global GAME_NAME_CACHE
    GAME_NAME_CACHE = {}

def get_played_games(username):
    """Mendapatkan daftar game yang sudah dimainkan oleh username"""
    try:
        file_path = os.path.join(PLAY_GAME_FOLDER, f"game.{username}.json")
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    except:
        return []

def get_next_game_id(username, current_game_id):
    """Mendapatkan game ID berikutnya yang akan dimainkan dari daftar gameid.json"""
    try:
        # Load daftar gameid
        with open(GAMEID_LIST_FILE, "r", encoding="utf-8") as f:
            all_gameids = json.load(f)
        
        if not all_gameids:
            return current_game_id
            
        # Load game yang sudah dimainkan
        played_games = get_played_games(username)
        
        # Cari game yang belum dimainkan
        unplayed_games = [gid for gid in all_gameids if gid not in played_games]
        
        if unplayed_games:
            # Pilih game yang belum dimainkan
            return unplayed_games[0]
        else:
            # Jika semua sudah dimainkan, pilih secara random dari daftar
            import random
            available_games = [gid for gid in all_gameids if gid != current_game_id]
            if available_games:
                return random.choice(available_games)
            else:
                return all_gameids[0]  # Fallback ke game pertama
                
    except Exception as e:
        add_log(f"Error getting next game: {e}")
        # Fallback: return game pertama dari daftar atau current game
        try:
            with open(GAMEID_LIST_FILE, "r", encoding="utf-8") as f:
                all_gameids = json.load(f)
                return all_gameids[0] if all_gameids else current_game_id
        except:
            return current_game_id

def change_game_for_all_accounts(accounts, cfg):
    """Ganti game untuk semua akun yang sedang berjalan"""
    global GAME_CHANGE_STATE
    
    if GAME_CHANGE_STATE["is_changing"]:
        return False
        
    add_log("🔄 Changing games for all accounts", important=True)
    GAME_CHANGE_STATE["is_changing"] = True
    GAME_CHANGE_STATE["change_start_time"] = time.time()

    clear_all_game_cache()

    # Load daftar gameid
    try:
        with open(GAMEID_LIST_FILE, "r", encoding="utf-8") as f:
            all_gameids = json.load(f)
    except:
        add_log("Error loading game list", important=True)
        GAME_CHANGE_STATE["is_changing"] = False
        return False
    
    killed_count = 0
    game_changes = 0
    
    # Pre-fetch nama game untuk cache
    add_log("📥 Pre-loading game names...", important=True)
    for game_id in all_gameids[:10]:  # Pre-load max 10 game pertama
        get_game_name(game_id, force_refresh=True)
        time.sleep(0.5)  # Delay agar tidak spam request
    
    for acc in accounts:
        pid = acc.get("pid")
        
        # Kill process yang sedang berjalan (jika ada)
        if pid and is_roblox_process_running(pid):
            if aggressive_kill_process(pid, acc):
                killed_count += 1
        
        # Dapatkan game berikutnya dari daftar gameid.json
        current_game = acc.get("game_id") or cfg.get("gameId")
        next_game = get_next_game_id(acc["username"], current_game)
        
        # Update game_id untuk akun ini (PASTI dari daftar gameid.json)
        acc["game_id"] = next_game
        acc["private_link"] = ""  # Reset private link
        acc["pid"] = None  # Reset PID
        acc["launch_time"] = None  # Reset launch time
        acc["last_launch"] = 0  # Reset cooldown
        acc["json_start_time"] = None  # Reset JSON start time
        acc["json_active"] = False  # Reset JSON active state
        
        # Dapatkan nama game untuk cache
        game_name = get_game_name(next_game, force_refresh=True)
        
        # Catat game yang akan dimainkan
        record_current_game(acc["username"], next_game)
        
        game_changes += 1
        add_log(f"🎮 {acc['username']} will play {game_name} ({next_game})", important=True)
    
    GAME_CHANGE_STATE["last_change_time"] = time.time()
    add_log(f"✅ Changed games for {game_changes} accounts. Killed {killed_count} processes. Will play for 10 minutes then stop script.", important=True)
    return True

def rotate_accounts(accounts, cfg):
    """Rotasi akun yang aktif"""
    global ACCOUNT_ROTATION_INDEX, LAST_ACCOUNT_CHANGE_TIME
    
    add_log("🔄 Rotating accounts", important=True)
    
    total_instances = int(cfg.get("TotalInstance", 10))
    total_accounts = len(accounts)
    
    if total_accounts <= total_instances:
        add_log("No rotation needed - all accounts are active", important=True)
        return True
    
    # Kill semua proses yang sedang berjalan
    killed_count = 0
    for acc in accounts:
        pid = acc.get("pid")
        if pid and is_roblox_process_running(pid):
            if aggressive_kill_process(pid, acc):
                killed_count += 1
    
    # Update rotation index
    ACCOUNT_ROTATION_INDEX = (ACCOUNT_ROTATION_INDEX + total_instances) % total_accounts
    
    add_log(f"✅ Rotated accounts. Next batch starts from index {ACCOUNT_ROTATION_INDEX}", important=True)
    LAST_ACCOUNT_CHANGE_TIME = time.time()
    return True

def get_active_accounts(accounts, cfg):
    """Mendapatkan akun aktif berdasarkan rotasi"""
    global ACCOUNT_ROTATION_INDEX
    
    total_instances = int(cfg.get("TotalInstance", 10))
    total_accounts = len(accounts)
    
    if total_accounts <= total_instances:
        return accounts
    
    start_index = ACCOUNT_ROTATION_INDEX
    end_index = start_index + total_instances
    
    if end_index <= total_accounts:
        return accounts[start_index:end_index]
    else:
        # Handle wrap-around
        first_part = accounts[start_index:]
        remaining = total_instances - len(first_part)
        return first_part + accounts[:remaining]

ROBLOX_EXE_NAMES = {"robloxplayerbeta.exe", "robloxplayer.exe", "robloxplayerlauncher.exe"}

def start_arrage_exe():
    if is_process_running_by_name("arrage.exe"):
        print("arrage.exe sudah berjalan – tidak dijalankan ulang.")
        return True

    exe_path = os.path.join(os.getcwd(), "arrage.exe")
    if not os.path.exists(exe_path):
        print("arrage.exe tidak ditemukan!")
        return False

    try:
        subprocess.Popen([exe_path], creationflags=subprocess.CREATE_NO_WINDOW)
        print("arrage.exe started.")
        return True
    except Exception as e:
        print(f"Gagal start arrage.exe: {e}")
        return False

def kill_arrage_exe():
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] and proc.info['name'].lower() == "arrage.exe":
                try:
                    proc.kill()
                except:
                    pass
        print("arrage.exe closed.")
    except:
        pass

def kill_ova_exe():
    """Kill semua proses ova.exe"""
    try:
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] and proc.info['name'].lower() == "ova.exe":
                try:
                    proc.kill()
                except:
                    pass
        print("ova.exe closed.")
    except:
        pass

def start_ova_exe():
    """Start ova.exe jika belum berjalan"""
    global OVA_PROCESS

    if is_process_running_by_name("ova.exe"):
        print("ova.exe sudah berjalan – tidak dijalankan ulang.")
        return True

    ova_path = os.path.join(os.getcwd(), "ova.exe")

    if not os.path.exists(ova_path):
        print("WARNING: ova.exe tidak ditemukan!")
        return False

    try:
        OVA_PROCESS = subprocess.Popen(
            [ova_path],
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        print("ova.exe started.")
        return True
    except Exception as e:
        print(f"Gagal start ova.exe: {e}")
        return False

def is_process_running_by_name(name):
    """Cek apakah process dengan nama tertentu sedang berjalan"""
    name = name.lower()
    for proc in psutil.process_iter(['name']):
        try:
            if proc.info['name'] and proc.info['name'].lower() == name:
                return True
        except:
            pass
    return False

# ----------------------------
# Logging (Minimal)
# ----------------------------
LOG_MESSAGES = []
MAX_LOG_LINES = 3

def nowstr():
    return datetime.now().strftime("%H:%M:%S")

def add_log(msg, important=False):
    """Add log - hanya important logs yang ditampilkan"""
    global LOG_MESSAGES
    
    # Filter out verbose logs
    skip_keywords = ["rename", "pid", "attempt", "quick", "background", "recovery"]
    
    if not important:
        # Check if message contains skip keywords
        msg_lower = msg.lower()
        if any(keyword in msg_lower for keyword in skip_keywords):
            return
    
    timestamp = nowstr()
    LOG_MESSAGES.append(f"[{timestamp}] {msg}")
    if len(LOG_MESSAGES) > MAX_LOG_LINES:
        LOG_MESSAGES.pop(0)

# ----------------------------
# Config Management
# ----------------------------
def load_or_create_config():
    cfg = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except:
            cfg = {}
    
    updated = False
    for k, v in DEFAULT_CONFIG.items():
        if k not in cfg:
            cfg[k] = v
            updated = True
    
    if updated:
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2)
        except:
            pass
    return cfg

def ensure_cookie_file():
    if not os.path.exists(COOKIE_FILE):
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            f.write("")
        return False
    return True

def load_cookies():
    if not os.path.exists(COOKIE_FILE):
        return []
    with open(COOKIE_FILE, "r", encoding="utf-8") as f:
        lines = [l.strip() for l in f if l.strip()]
    return lines

def ensure_server_file():
    if not os.path.exists(SERVER_FILE):
        with open(SERVER_FILE, "w", encoding="utf-8") as f:
            f.write("# Format: 1 link per line (Line 1 = Account 1)\n")
            f.write("# Use 'default' or leave empty for config.json settings\n")
    return True

def load_servers():
    if not os.path.exists(SERVER_FILE):
        return []
    with open(SERVER_FILE, "r", encoding="utf-8") as f:
        lines = []
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                lines.append(None)
            elif line.lower() == "default":
                lines.append(None)
            else:
                lines.append(line)
        return lines

def parse_game_link(link):
    if not link:
        return None, None
    
    try:
        game_id_match = re.search(r'/games/(\d+)', link)
        game_id = int(game_id_match.group(1)) if game_id_match else None
        
        private_code = None
        if "privateServerLinkCode=" in link:
            match = re.search(r'privateServerLinkCode=([^&]+)', link)
            if match:
                private_code = match.group(1)
        elif "share?code=" in link:
            match = re.search(r'code=([^&]+)', link)
            if match:
                private_code = match.group(1)
        
        return game_id, private_code
    except:
        return None, None

# ----------------------------
# Save/Load System (Simplified)
# ----------------------------
def ensure_saves_folder():
    try:
        if not os.path.exists(SAVES_FOLDER):
            os.makedirs(SAVES_FOLDER, exist_ok=True)
        return True
    except:
        return False

def load_death_cookies():
    if not os.path.exists(DEATH_FILE):
        return set()
    try:
        with open(DEATH_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return set(data) if isinstance(data, list) else set()
    except:
        return set()

def save_death_cookie(username):
    os.makedirs(SAVES_FOLDER, exist_ok=True)
    death = load_death_cookies()
    if username not in death:
        death.add(username)
        with open(DEATH_FILE, "w", encoding="utf-8") as f:
            json.dump(sorted(death), f, indent=2)

def is_cookie_death(username):
    return username in load_death_cookies()

def save_death_cookies(entries):
    os.makedirs(SAVES_FOLDER, exist_ok=True)
    with open(DEATH_COOKIES_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)

def save_accounts_data(accounts):
    """Save accounts data - Silent version"""
    try:
        os.makedirs(SAVES_FOLDER, exist_ok=True)
        
        existing_data = load_accounts_data()
        pid_to_username = existing_data.get("pid_to_username", {})
        username_to_pid = existing_data.get("username_to_pid", {})
        
        if not isinstance(accounts, list):
            accounts = [accounts]
        
        for acc in accounts:
            pid = acc.get("pid")
            username = acc.get("username")
            
            if pid and username and is_process_really_running(pid):
                try:
                    process = psutil.Process(pid)
                    if process.name().lower() in ROBLOX_EXE_NAMES:
                        pid_to_username[str(pid)] = username
                        username_to_pid[username] = pid
                except:
                    continue
        
        saves_data = {
            "pid_to_username": pid_to_username,
            "username_to_pid": username_to_pid,
            "timestamp": time.time()
        }
        
        with open(SAVES_FILE, "w", encoding="utf-8") as f:
            json.dump(saves_data, f, indent=2)
        
        return True
        
    except:
        return False

def periodic_rename_check():
    """Check unrenamed windows every X minutes"""
    def _check_worker():
        while True:
            try:
                time.sleep(60)  # menit
                
                # Cari unrenamed windows
                unrenamed = get_unrenamed_roblox_windows()
                
                if unrenamed:
                    add_log(f"🔍 Found {len(unrenamed)} unrenamed Roblox windows")
                    
                    for window in unrenamed:
                        pid = window['pid']
                        
                        # Cari username yang cocok dengan PID ini
                        for acc in accounts:
                            if acc.get("pid") == pid:
                                username = acc["username"]
                                add_log(f"🔄 Attempting rename for {username} (PID: {pid})")
                                quick_rename_async(pid, username)
                                break
                        else:
                            # PID tidak ada di accounts, coba recovery
                            add_log(f"⚠️ Unknown PID {pid}, attempting recovery...")
                
            except Exception as e:
                add_log(f"Error in periodic rename check: {str(e)[:50]}")
                time.sleep(60)
    
    thread = threading.Thread(target=_check_worker, daemon=True)
    thread.start()
    return thread

def load_accounts_data():
    """Load accounts data - Silent version"""
    try:
        if not os.path.exists(SAVES_FILE) or os.path.getsize(SAVES_FILE) == 0:
            return {"pid_to_username": {}, "username_to_pid": {}}
        
        with open(SAVES_FILE, "r", encoding="utf-8") as f:
            saves_data = json.load(f)
        
        if not isinstance(saves_data, dict):
            return {"pid_to_username": {}, "username_to_pid": {}}
        
        valid_pid_to_username = {}
        valid_username_to_pid = {}
        
        pid_to_username = saves_data.get("pid_to_username", {})
        if not isinstance(pid_to_username, dict):
            pid_to_username = {}
        
        for pid_str, username in pid_to_username.items():
            try:
                pid = int(pid_str)
                if psutil.pid_exists(pid):
                    process = psutil.Process(pid)
                    if process.name().lower() in ROBLOX_EXE_NAMES:
                        valid_pid_to_username[pid_str] = username
                        valid_username_to_pid[username] = pid
            except:
                continue
        
        return {
            "pid_to_username": valid_pid_to_username,
            "username_to_pid": valid_username_to_pid
        }
        
    except:
        return {"pid_to_username": {}, "username_to_pid": {}}

def load_bf_stats(workspace_folder, username):
    now = time.time()

    # Cache check
    if username in BF_CACHE and (now - BF_CACHE_TIME.get(username, 0)) < BF_CACHE_INTERVAL:
        return BF_CACHE[username]

    filepath = os.path.join(workspace_folder, f"bf.{username}.json")
    if not os.path.exists(filepath):
        BF_CACHE[username] = None
        BF_CACHE_TIME[username] = now
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        stats = data.get("Stats", {})
        equip = data.get("Equipment", {})
        inv = data.get("Inventory", {})

        level = stats.get("Level")
        beli = stats.get("Beli")
        frags = stats.get("Fragments")
        race = stats.get("Race", "-")
        meele = equip.get("EquippedMelee", "-")
        fruit_equipped = equip.get("EquippedFruit", "-")

        # RARITY FILTER
        def rarity_filter(item):
            tier = item.get("Tier")
            name = item.get("Name")
            if tier == "Mythical":
                return ("Mythical", name)
            elif tier == "Legendary":
                return ("Legendary", name)
            return None

        swords = [rarity_filter(s) for s in inv.get("Swords", []) if rarity_filter(s)]
        guns = [rarity_filter(g) for g in inv.get("Guns", []) if rarity_filter(g)]
        fruits = [rarity_filter(f) for f in inv.get("Fruits", []) if rarity_filter(f)]

        result = {
            "level": level,
            "beli": beli,
            "frags": frags,
            "race": race,
            "meele": meele,
            "fruit_equipped": fruit_equipped,
            "swords": swords,
            "guns": guns,
            "fruits": fruits,
        }

        # update cache
        BF_CACHE[username] = result
        BF_CACHE_TIME[username] = now
        return result

    except:
        BF_CACHE[username] = None
        BF_CACHE_TIME[username] = now
        return None

# ----------------------------
# Global Rename Tracking
# ----------------------------
RENAME_TASKS = {}
RENAME_LOCK = threading.Lock()

# ----------------------------
# Save Batching - Reduce save frequency
# ----------------------------
SAVE_BATCH = {"pending": False, "last_save": 0}
SAVE_BATCH_LOCK = threading.Lock()
SAVE_BATCH_INTERVAL = 5  # Save max once every 5 seconds

def schedule_save(accounts):
    """Schedule a save (batched to reduce frequency)"""
    with SAVE_BATCH_LOCK:
        SAVE_BATCH["pending"] = True
        SAVE_BATCH["accounts"] = accounts

def process_pending_saves():
    """Process pending saves in background"""
    with SAVE_BATCH_LOCK:
        if not SAVE_BATCH.get("pending", False):
            return
        
        current_time = time.time()
        last_save = SAVE_BATCH.get("last_save", 0)
        
        # Only save if enough time has passed
        if current_time - last_save < SAVE_BATCH_INTERVAL:
            return
        
        # Get accounts and reset pending
        accounts_to_save = SAVE_BATCH.get("accounts", [])
        SAVE_BATCH["pending"] = False
        SAVE_BATCH["last_save"] = current_time
    
    # Save outside lock
    if accounts_to_save:
        save_accounts_data(accounts_to_save)

# ----------------------------
# Launch Queue System - PREVENT WINDOW SWAP
# ----------------------------
LAUNCH_QUEUE = {}  # Format: {username: {"launch_time": time, "expected_pid": None}}
LAUNCH_LOCK = threading.Lock()

def register_launch(username):
    """Register bahwa username ini sedang launching"""
    with LAUNCH_LOCK:
        LAUNCH_QUEUE[username] = {
            "launch_time": time.time(),
            "expected_pid": None,
            "status": "launching"
        }
        add_log(f"🔵 Registered launch for {username}")

def assign_pid_to_launch(username, pid):
    """Assign PID ke username yang baru launch"""
    with LAUNCH_LOCK:
        if username in LAUNCH_QUEUE:
            LAUNCH_QUEUE[username]["expected_pid"] = pid
            LAUNCH_QUEUE[username]["status"] = "pid_assigned"
            add_log(f"🎯 Assigned PID {pid} to {username}")
            return True
        return False

def complete_launch(username):
    """Mark launch as complete"""
    with LAUNCH_LOCK:
        if username in LAUNCH_QUEUE:
            del LAUNCH_QUEUE[username]
            add_log(f"✅ Completed launch for {username}")

def is_username_launching(username):
    """Check if username sedang launching"""
    with LAUNCH_LOCK:
        return username in LAUNCH_QUEUE

def get_launching_usernames():
    """Get semua usernames yang sedang launching"""
    with LAUNCH_LOCK:
        return list(LAUNCH_QUEUE.keys())

def find_newest_unassigned_roblox_pid(exclude_pids=None):
    """Find newest Roblox PID yang belum di-assign ke account manapun"""
    if exclude_pids is None:
        exclude_pids = set()
    
    try:
        # Get all assigned PIDs
        with LAUNCH_LOCK:
            assigned_in_queue = set(
                q["expected_pid"] for q in LAUNCH_QUEUE.values() 
                if q.get("expected_pid")
            )
        
        # Get PIDs from accounts
        assigned_in_accounts = set(acc.get("pid") for acc in accounts if acc.get("pid"))
        
        all_assigned = assigned_in_queue | assigned_in_accounts | exclude_pids
        
        # Find unassigned Roblox processes
        unassigned = []
        for proc in psutil.process_iter(['pid', 'name', 'create_time']):
            try:
                if (proc.info['name'] and 
                    proc.info['name'].lower() in ROBLOX_EXE_NAMES and
                    proc.info['pid'] not in all_assigned):
                    unassigned.append({
                        'pid': proc.info['pid'],
                        'create_time': proc.info.get('create_time', 0)
                    })
            except:
                continue
        
        if unassigned:
            # Return newest (highest create_time)
            newest = max(unassigned, key=lambda x: x['create_time'])
            add_log(f"🔍 Found newest unassigned PID: {newest['pid']}")
            return newest['pid']
        
        return None
        
    except Exception as e:
        add_log(f"Error finding unassigned PID: {str(e)[:50]}")
        return None

RENAME_LOCK = threading.Lock()  # Thread safety for RENAME_TASKS

# ----------------------------
# JSON Checker Functions - UPDATED LOGIC
# ----------------------------
def get_json_file_path(workspace_folder, username):
    return os.path.join(workspace_folder, f"{username}_checkyum.json")

def read_json_file(filepath):
    try:
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
    except:
        pass
    return None

def parse_time_from_json(time_str):
    try:
        return datetime.fromisoformat(time_str.replace('Z', '+00:00'))
    except:
        return None

def get_json_time_diff(workspace_folder, username):
    filepath = get_json_file_path(workspace_folder, username)
    data = read_json_file(filepath)
    
    if data is None:
        return None
    
    json_time = parse_time_from_json(data.get("time", ""))
    if json_time is None:
        return None
    
    now = datetime.now(timezone.utc)
    time_diff = (now - json_time).total_seconds()
    
    return time_diff

def check_json_running(workspace_folder, username):
    """Check apakah JSON sedang berjalan (< 60 detik)"""
    time_diff = get_json_time_diff(workspace_folder, username)
    
    if time_diff is None:
        return False
    
    return time_diff <= 60

def determine_account_status(acc, workspace_folder, first_check_minutes):
    """
    Menentukan status akun berdasarkan logika baru:
    - offline: Client tidak berjalan
    - waiting: Launch baru, menunggu first check
    - in_game: JSON aktif
    - needs_kill: JSON tidak aktif setelah melewati first check / grace period
    """
    pid = acc.get("pid")
    username = acc["username"]
    launch_time = acc.get("launch_time")
    json_start_time = acc.get("json_start_time")
    json_active = acc.get("json_active", False)
    
    # 1. Jika client tidak berjalan → OFFLINE
    if pid is None or not is_roblox_process_running(pid):
        # PENTING: Reset semua timer saat offline
        acc["json_active"] = False
        acc["json_start_time"] = None
        return "offline"
    
    # 2. Client berjalan, cek JSON
    json_running = check_json_running(workspace_folder, username)
    current_time = time.time()
    first_check_seconds = first_check_minutes * 60
    
    # 3. Jika JSON berjalan
    if json_running:
        # Mark JSON as active - UPDATE timer setiap kali JSON aktif
        acc["json_active"] = True
        acc["json_start_time"] = current_time
        
        return "in_game"
    
    # 4. JSON tidak berjalan - cek kondisi
    # 4a. Jika baru launch, masih dalam grace period → WAITING
    if launch_time is not None:
        time_since_launch = current_time - launch_time
        if time_since_launch < first_check_seconds:
            return "waiting"
    
    # 4b. Jika JSON pernah aktif tapi sekarang mati
    if json_active and json_start_time is not None:
        time_since_json_stop = current_time - json_start_time
        # Jika JSON mati lebih dari first_check → NEEDS KILL
        if time_since_json_stop >= first_check_seconds:
            return "needs_kill"
        else:
            # Masih dalam grace period setelah JSON mati
            return "in_game"
    
    # 4c. Launch sudah lama, JSON belum pernah aktif → NEEDS KILL
    if launch_time is not None:
        time_since_launch = current_time - launch_time
        if time_since_launch >= first_check_seconds:
            return "needs_kill"
    
    # 4d. Kondisi tidak jelas → WAITING
    return "waiting"

# ----------------------------
# Game Name Cache
# ----------------------------
GAME_NAME_CACHE = {}

def get_game_name(place_id, force_refresh=False):
    global GAME_NAME_CACHE
    
    if not force_refresh and place_id in GAME_NAME_CACHE:
        return GAME_NAME_CACHE[place_id]
    
    COMMON_GAMES = {
        2753915549: "Blox Fruits",
        606849621: "Jailbreak",
        537413528: "Build A Boat",
        920587237: "Adopt Me!",
        189707: "Natural Disaster",
        292439477: "Phantom Forces",
        286090429: "Arsenal",
        8737899170: "Adopt Me!",  
        740581508: "Brookhaven RP",  
        735030788: "Blade Ball",
        1962086868: "Pet Simulator 99",
        142823291: "Mad City",
        370710243: "Vehicle Legends",
        6699864173: "Doors",
        187796081: "MeepCity",
        6516141723: "Rainbow Friends",
        3527629287: "Tower of Hell",
        6872265039: "Muscle Legends",
        914010731: "RoGhoul",
        2970742921: "Anime Adventures",
        2653064683: "All Star Tower Defense",
        3112115001: "King Legacy",
        6447795994: "Heroes Online",
        2217468224: "World Zero",
        7047607440: "Build A Boat For Treasure",
        8560631822: "Horrific Housing",
        4490140733: "BedWars",
        5663993410: "Sonic Speed Simulator",
        7532473490: "Ragdoll Universe",
        6284583030: "Ninja Legends",
        8939734408: "Mining Simulator 2",
        8540346418: "Zombie Attack",
        6677985873: "Super Golf",
        4738548959: "Bubble Gum Simulator"
    }
    
    if place_id in COMMON_GAMES:
        GAME_NAME_CACHE[place_id] = COMMON_GAMES[place_id]
        return COMMON_GAMES[place_id]
    
    # Jika tidak ada di common games, fetch dari API
    try:
        url = f"https://games.roblox.com/v1/games/multiget-place-details?placeIds={place_id}"
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if len(data) > 0:
                name = data[0].get("name", "")
                if name and "'s Place" not in name.lower():
                    GAME_NAME_CACHE[place_id] = name
                    return name
    except:
        pass
    
    fallback_name = f"Game {place_id}"
    GAME_NAME_CACHE[place_id] = fallback_name
    return fallback_name

# ----------------------------
# Windows API Setup
# ----------------------------
user32 = ctypes.WinDLL('user32', use_last_error=True)

EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
IsWindowVisible = user32.IsWindowVisible
GetWindowTextLengthW = user32.GetWindowTextLengthW
GetWindowTextW = user32.GetWindowTextW
SetWindowTextW = user32.SetWindowTextW

def enum_windows():
    results = []
    @EnumWindowsProc
    def _proc(hwnd, lParam):
        if IsWindowVisible(hwnd):
            length = GetWindowTextLengthW(hwnd)
            buffer = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buffer, length + 1)
            text = buffer.value
            results.append((hwnd, text))
        return True
    EnumWindows(_proc, 0)
    return results

def hwnd_to_pid(hwnd):
    pid = wintypes.DWORD()
    GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value

def get_process_name_from_hwnd(hwnd):
    try:
        pid = hwnd_to_pid(hwnd)
        if pid and psutil.pid_exists(pid):
            process = psutil.Process(pid)
            return process.name()
    except:
        pass
    return None

def set_window_title(hwnd, new_title):
    try:
        user32.SetWindowTextW(hwnd, new_title)
        return True
    except:
        return False

# ----------------------------
# Rename Functions (Silent)
# ----------------------------
def rename_window_async(pid, username, max_attempts=999, delay=5):
    """Rename window in background - Silent"""
    def _rename_worker():
        current_pid = pid
        
        try:
            with RENAME_LOCK:
                if username not in RENAME_TASKS:
                    RENAME_TASKS[username] = {}
                
                RENAME_TASKS[username]["pid"] = current_pid
                RENAME_TASKS[username]["last_attempt"] = time.time()
                RENAME_TASKS[username]["attempts"] = 0
            
            attempt = 0
            while attempt < max_attempts:
                try:
                    with RENAME_LOCK:
                        if username in RENAME_TASKS:
                            RENAME_TASKS[username]["attempts"] = attempt + 1
                            RENAME_TASKS[username]["last_attempt"] = time.time()
                    
                    if not is_process_really_running(current_pid):
                        recovered_pid = recover_process_for_username(username)
                        if recovered_pid:
                            current_pid = recovered_pid
                            update_account_pid(username, current_pid)
                            continue
                        else:
                            break
                    
                    success = rename_roblox_window_by_pid(current_pid, username, max_attempts=3, delay=1)
                    
                    if success:
                        save_accounts_data([{"username": username, "pid": current_pid}])
                        with RENAME_LOCK:
                            if username in RENAME_TASKS:
                                del RENAME_TASKS[username]
                        return
                
                except:
                    pass
                
                attempt += 1
                time.sleep(delay)
            
            with RENAME_LOCK:
                if username in RENAME_TASKS:
                    del RENAME_TASKS[username]
                
        except:
            with RENAME_LOCK:
                if username in RENAME_TASKS:
                    del RENAME_TASKS[username]
    
    thread = threading.Thread(target=_rename_worker, daemon=True)
    thread.start()
    return thread

def update_account_pid(username, new_pid):
    """Update PID - Silent"""
    global accounts
    for acc in accounts:
        if acc["username"] == username:
            acc["pid"] = new_pid
            acc["launch_time"] = time.time()
            break

def quick_rename_async(pid, username):
    """Quick rename - Silent"""
    def _quick_rename():
        try:
            current_pid = pid
            
            if not is_process_really_running(current_pid):
                recovered_pid = recover_process_for_username(username)
                if recovered_pid:
                    current_pid = recovered_pid
                    update_account_pid(username, current_pid)
                else:
                    return
            
            for _ in range(3):
                success = rename_roblox_window_by_pid(current_pid, username, max_attempts=2, delay=0.5)
                if success:
                    save_accounts_data([{"username": username, "pid": current_pid}])
                    return
                time.sleep(2)
        except:
            pass
    
    threading.Thread(target=_quick_rename, daemon=True).start()

def rename_roblox_window_by_pid(pid, username, max_attempts=15, delay=1):
    """Rename window - Silent"""
    for attempt in range(max_attempts):
        try:
            hwnds = enum_windows()
            
            for hwnd, title in hwnds:
                window_pid = hwnd_to_pid(hwnd)
                if window_pid == pid:
                    process_name = get_process_name_from_hwnd(hwnd)
                    
                    if process_name and process_name.lower() in ROBLOX_EXE_NAMES:
                        if title.strip() == username:
                            return True
                            
                        if set_window_title(hwnd, username):
                            time.sleep(0.2)
                            return True
                
        except:
            pass
        
        if attempt < max_attempts - 1:
            time.sleep(delay)
    
    return False

def is_process_really_running(pid):
    """Enhanced process checking"""
    if pid is None:
        return False
    
    try:
        if psutil.pid_exists(pid):
            process = psutil.Process(pid)
            if (process.name().lower() in ROBLOX_EXE_NAMES and 
                process.status() != psutil.STATUS_ZOMBIE):
                return True
        return False
        
    except:
        return False

def find_roblox_process_by_username(username):
    """Cari Roblox process - Silent"""
    try:
        hwnds = enum_windows()
        candidate_processes = []
        
        for hwnd, title in hwnds:
            try:
                pid = hwnd_to_pid(hwnd)
                if pid and psutil.pid_exists(pid):
                    process = psutil.Process(pid)
                    if process.name().lower() in ROBLOX_EXE_NAMES:
                        title_lower = title.lower()
                        
                        if title.strip() == username:
                            return pid
                            
                        elif (title.strip() == "" or 
                              "roblox" in title_lower or 
                              len(title.strip()) < 3):
                            candidate_processes.append((pid, title, 1))
                            
            except:
                continue
        
        if candidate_processes:
            candidate_processes.sort(key=lambda x: x[2])
            return candidate_processes[0][0]
            
        return None
        
    except:
        return None

def get_unrenamed_roblox_windows():
    """Get unrenamed windows - Silent"""
    unrenamed_windows = []
    try:
        hwnds = enum_windows()
        
        for hwnd, title in hwnds:
            try:
                pid = hwnd_to_pid(hwnd)
                if pid and psutil.pid_exists(pid):
                    process = psutil.Process(pid)
                    if process.name().lower() in ROBLOX_EXE_NAMES:
                        title_lower = title.lower()
                        is_default_title = (
                            title.strip() == "" or
                            "roblox" in title_lower or 
                            len(title.strip()) < 3 or
                            not any(acc["username"].lower() in title_lower for acc in accounts)
                        )
                        
                        if is_default_title:
                            unrenamed_windows.append({
                                'pid': pid,
                                'title': title,
                                'hwnd': hwnd
                            })
            except:
                continue
                
        unrenamed_windows.sort(key=lambda x: psutil.Process(x['pid']).create_time(), reverse=True)
        
    except:
        pass
    
    return unrenamed_windows

def get_all_roblox_processes():
    """Get all Roblox processes - Silent"""
    roblox_processes = []
    try:
        for proc in psutil.process_iter(['pid', 'name', 'create_time']):
            try:
                if proc.info['name'] and proc.info['name'].lower() in ROBLOX_EXE_NAMES:
                    roblox_processes.append({
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'create_time': proc.info.get('create_time', 0)
                    })
            except:
                continue
        roblox_processes.sort(key=lambda x: x['create_time'], reverse=True)
    except:
        pass
    
    return roblox_processes
    
def recover_process_for_username(username):
    """Process recovery - Silent"""
    try:
        recovered_pid = find_roblox_process_by_username(username)
        if recovered_pid:
            return recovered_pid
        
        unrenamed_windows = get_unrenamed_roblox_windows()
        if unrenamed_windows:
            return unrenamed_windows[0]['pid']
        
        all_roblox = get_all_roblox_processes()
        assigned_pids = set(acc.get("pid") for acc in accounts if acc.get("pid"))
        unassigned_processes = [p for p in all_roblox if p['pid'] not in assigned_pids]
        
        if unassigned_processes:
            return unassigned_processes[0]['pid']
        
        if all_roblox:
            return all_roblox[0]['pid']
        
        return None
        
    except:
        return None

def start_rename_monitor():
    """Monitor rename tasks - Silent"""
    def _monitor_worker():
        while True:
            try:
                current_time = time.time()
                
                with RENAME_LOCK:
                    tasks_snapshot = dict(RENAME_TASKS)
                
                for username, task_info in tasks_snapshot.items():
                    if username not in RENAME_TASKS:
                        continue
                        
                    pid = task_info.get("pid")
                    last_attempt = task_info.get("last_attempt", 0)
                    
                    if current_time - last_attempt > 30:
                        with RENAME_LOCK:
                            if username in RENAME_TASKS:
                                del RENAME_TASKS[username]
                        
                        recovered_pid = recover_process_for_username(username)
                        if recovered_pid:
                            rename_window_async(recovered_pid, username)
                        elif pid:
                            rename_window_async(pid, username)
                
                time.sleep(10)
                
            except:
                time.sleep(30)
    
    thread = threading.Thread(target=_monitor_worker, daemon=True)
    thread.start()
    return thread

# ----------------------------
# Process Management
# ----------------------------
def get_process_ram_usage(pid):
    try:
        if pid and psutil.pid_exists(pid):
            process = psutil.Process(pid)
            memory_info = process.memory_info()
            ram_usage_gb = memory_info.rss / (1024 ** 3)
            return round(ram_usage_gb, 2)
    except:
        pass
    return 0

def is_process_running(pid):
    if pid is None:
        return False
    try:
        return psutil.pid_exists(pid)
    except:
        return False

def is_roblox_process_running(pid):
    if not is_process_running(pid):
        return False
    try:
        p = psutil.Process(pid)
        return p.name().lower() in ROBLOX_EXE_NAMES
    except:
        return False

def aggressive_kill_process(pid, acc=None):
    """Force kill process"""
    try:
        if pid and psutil.pid_exists(pid):
            proc = psutil.Process(pid)
            
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except psutil.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            
            if not psutil.pid_exists(pid):
                if acc:
                    acc["pid"] = None
                    acc["launch_time"] = None
                    acc["json_start_time"] = None
                    acc["json_active"] = False
                return True
            else:
                return False
                
    except psutil.NoSuchProcess:
        if acc:
            acc["pid"] = None
            acc["launch_time"] = None
            acc["json_start_time"] = None
            acc["json_active"] = False
        return True
    except:
        pass
    return False

def check_and_kill_high_ram_processes(accounts, ram_threshold_gb):
    """Kill high RAM processes"""
    killed_count = 0
    
    for acc in accounts:
        pid = acc.get("pid")
        if pid and is_roblox_process_running(pid):
            ram_usage = get_process_ram_usage(pid)
            if ram_usage > ram_threshold_gb:
                add_log(f"Kill {acc['username']} - High RAM: {ram_usage}GB", important=True)
                if aggressive_kill_process(pid, acc):
                    killed_count += 1
    
    return killed_count

def kill_duplicate_running_accounts(accounts, target_username):
    """Kill any running instance of target username before launching"""
    killed = False
    for acc in accounts:
        if acc["username"] == target_username:
            pid = acc.get("pid")
            if pid and is_roblox_process_running(pid):
                add_log(f"Kill existing {target_username} before relaunch")
                if aggressive_kill_process(pid, acc):
                    killed = True
    return killed

# ----------------------------
# Roblox API Functions
# ----------------------------
def get_user_from_cookie(cookie, max_retries=3):
    """Get user info from cookie"""
    for attempt in range(max_retries):
        try:
            r = requests.get("https://users.roblox.com/v1/users/authenticated",
                             headers={"Cookie": f".ROBLOSECURITY={cookie}"},
                             timeout=10)
            if r.status_code == 200:
                d = r.json()
                user_id = str(d["id"])
                username = d.get("name") or d.get("displayName") or d["id"]
                return user_id, username
                    
        except:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
    
    return None, None

def get_auth_ticket(cookie):
    try:
        r1 = requests.post("https://auth.roblox.com/v1/authentication-ticket",
                           headers={"Cookie": f".ROBLOSECURITY={cookie}", "Content-Type": "application/json"},
                           timeout=10)
        csrf = r1.headers.get("x-csrf-token")
        if not csrf:
            return None
        
        r2 = requests.post("https://auth.roblox.com/v1/authentication-ticket",
                           headers={
                               "Cookie": f".ROBLOSECURITY={cookie}",
                               "X-CSRF-TOKEN": csrf,
                               "Referer": "https://www.roblox.com/",
                               "Origin": "https://www.roblox.com",
                               "User-Agent": "Mozilla/5.0",
                               "Content-Type": "application/json"
                           },
                           data="{}",
                           timeout=10)
        if r2.status_code == 200:
            return r2.headers.get("rbx-authentication-ticket")
    except:
        pass
    return None

def extract_private_server_code(private_link):
    if not private_link:
        return None
    try:
        if "privateServerLinkCode=" in private_link:
            match = re.search(r'privateServerLinkCode=([^&]+)', private_link)
            if match:
                return match.group(1)
        elif "share?code=" in private_link:
            match = re.search(r'code=([^&]+)', private_link)
            if match:
                return match.group(1)
    except:
        pass
    return None

def list_current_roblox_pids():
    res = []
    for p in psutil.process_iter(['pid', 'name', 'create_time']):
        try:
            if p.info['name'] and p.info['name'].lower() in ROBLOX_EXE_NAMES:
                res.append((p.info['pid'], p.info.get('create_time', 0)))
        except:
            pass
    return dict(res)

def find_new_roblox_pid(before_pids, timeout=20):
    start = time.time()
    while time.time() - start < timeout:
        cur = list_current_roblox_pids()
        new = [pid for pid in cur.keys() if pid not in before_pids]
        if new:
            new.sort(key=lambda p: cur[p], reverse=True)
            return new[0]
        time.sleep(0.5)
    return None

def launch_via_protocol(cookie, cfg_game_id, private_link="", username=None):
    """Launch Roblox via protocol dengan singleton handle removal"""
    ticket = get_auth_ticket(cookie)
    if not ticket:
        return None, "no-ticket"
    
    private_code = extract_private_server_code(private_link)
    
    if private_code:
        protocol = (
            f"roblox-player:1+launchmode:play+gameinfo:{ticket}"
            f"+launchtime:{int(time.time()*1000)}"
            f"+placelauncherurl:https%3A%2F%2Fwww.roblox.com%2FGame%2FPlaceLauncher.ashx%3Frequest%3DRequestPrivateGame%26placeId%3D{cfg_game_id}%26linkCode%3D{private_code}"
        )
    else:
        protocol = (
            f"roblox-player:1+launchmode:play+gameinfo:{ticket}"
            f"+launchtime:{int(time.time()*1000)}"
            f"+placelauncherurl:https%3A%2F%2Fwww.roblox.com%2FGame%2FPlaceLauncher.ashx%3Frequest%3DRequestGame%26placeId%3D{cfg_game_id}"
        )
    
    before = list_current_roblox_pids()
    
    try:
        subprocess.Popen(["cmd", "/c", "start", "", protocol], shell=True)
    except:
        return None, "start-failed"
    
    # Wait untuk process muncul
    new_pid = find_new_roblox_pid(before, timeout=25)
    
    if new_pid:
        return new_pid, "ok"
    
    return None, "no-new-pid"

# ----------------------------
# Follow Player Functions
# ----------------------------
def get_user_id_by_username(username, cookie):
    try:
        url = f"https://users.roblox.com/v1/users/search?keyword={username}&limit=10"
        r = requests.get(url, headers={"Cookie": f".ROBLOSECURITY={cookie}"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if data.get("data") and len(data["data"]) > 0:
                for user in data["data"]:
                    if user.get("name", "").lower() == username.lower():
                        return user.get("id")
        return None
    except:
        return None

def find_player_server(place_id, target_user_id, cookie, max_pages=10):
    try:
        cursor = ""
        page_count = 0
        
        while page_count < max_pages:
            url = f"https://games.roblox.com/v1/games/{place_id}/servers/Public?sortOrder=Desc&limit=100"
            if cursor:
                url += f"&cursor={cursor}"
            
            r = requests.get(url, headers={"Cookie": f".ROBLOSECURITY={cookie}"}, timeout=10)
            
            if r.status_code != 200:
                break
            
            data = r.json()
            servers = data.get("data", [])
            
            for server in servers:
                player_ids = server.get("playerIds", [])
                if target_user_id in player_ids:
                    job_id = server.get("id")
                    return job_id, server
            
            cursor = data.get("nextPageCursor")
            if not cursor:
                break
            
            page_count += 1
        
        return None, None
    except:
        return None, None

def launch_to_specific_server(cookie, place_id, job_id, username=None):
    """Launch to specific server"""
    ticket = get_auth_ticket(cookie)
    if not ticket:
        return None, "no-ticket"
    
    protocol = (
        f"roblox-player:1+launchmode:play+gameinfo:{ticket}"
        f"+launchtime:{int(time.time()*1000)}"
        f"+placelauncherurl:https%3A%2F%2Fassetgame.roblox.com%2Fgame%2FPlaceLauncher.ashx%3Frequest%3DRequestGameJob%26browserTrackerId%3D0%26placeId%3D{place_id}%26gameId%3D{job_id}%26isPlayTogetherGame%3Dfalse"
    )
    
    before = list_current_roblox_pids()
    
    try:
        subprocess.Popen(["cmd", "/c", "start", "", protocol], shell=True)
    except:
        return None, "start-failed"
    
    new_pid = find_new_roblox_pid(before, timeout=25)
    
    if new_pid:
        return new_pid, "ok"
    
    return None, "no-new-pid"

# ----------------------------
# Match Existing Processes
# ----------------------------
def match_existing_processes_to_accounts(accounts, workspace_folder, first_check_minutes):
    """Match processes - Silent version"""
    
    saved_data = load_accounts_data()
    pid_to_username = saved_data["pid_to_username"]
    username_to_pid = saved_data["username_to_pid"]
    
    running_roblox_pids = {}
    for proc in psutil.process_iter(['pid', 'name', 'create_time']):
        try:
            if proc.info['name'] and proc.info['name'].lower() in ROBLOX_EXE_NAMES:
                pid = proc.info['pid']
                running_roblox_pids[pid] = proc
        except:
            continue
    
    matched_count = 0
    
    # METHOD 1: Match via saved mapping
    for acc in accounts:
        if acc.get("pid") is not None:
            continue
            
        username = acc["username"]
        
        if username in username_to_pid:
            saved_pid = username_to_pid[username]
            
            if saved_pid in running_roblox_pids:
                acc["pid"] = saved_pid
                acc["launch_time"] = time.time() - 300
                acc["json_start_time"] = None
                acc["json_active"] = False
                matched_count += 1
                quick_rename_async(saved_pid, username)
                continue
    
    # METHOD 2: Match via window titles
    current_windows = enum_windows()
    window_pid_to_title = {}
    
    for hwnd, title in current_windows:
        try:
            pid = hwnd_to_pid(hwnd)
            if pid in running_roblox_pids:
                process_name = get_process_name_from_hwnd(hwnd)
                if process_name and process_name.lower() in ROBLOX_EXE_NAMES:
                    window_pid_to_title[pid] = title.strip()
        except:
            continue
    
    for acc in accounts:
        if acc.get("pid") is not None:
            continue
            
        username = acc["username"]
        
        for pid, window_title in window_pid_to_title.items():
            if (window_title.lower() == username.lower() or 
                username.lower() in window_title.lower()):
                
                pid_already_used = any(
                    other_acc.get("pid") == pid 
                    for other_acc in accounts 
                    if other_acc.get("pid") is not None
                )
                
                if not pid_already_used:
                    acc["pid"] = pid
                    acc["launch_time"] = time.time() - 300
                    acc["json_start_time"] = None
                    acc["json_active"] = False
                    matched_count += 1
                    break
    
    # METHOD 3: Assign remaining
    remaining_accounts = [acc for acc in accounts if acc.get("pid") is None]
    remaining_processes = [
        pid for pid in running_roblox_pids.keys() 
        if not any(acc.get("pid") == pid for acc in accounts)
    ]
    
    if remaining_accounts and remaining_processes:
        for acc, pid in zip(remaining_accounts, remaining_processes):
            acc["pid"] = pid
            acc["launch_time"] = time.time() - 300
            acc["json_start_time"] = None
            acc["json_active"] = False
            matched_count += 1
            quick_rename_async(pid, acc["username"])
    
    for acc in accounts:
        if acc.get("pid") is not None:
            quick_rename_async(acc["pid"], acc["username"])
    
    return matched_count

# ----------------------------
# Main Process Cycle - UPDATED LOGIC
# ----------------------------
def proc_cycle(accounts, cfg, follow_state, workspace_folder):
    """Main processing cycle dengan logika baru"""
    global GAME_CHANGE_STATE, ACCOUNT_CHANGE_STATE
    
    # Check untuk stop script setelah 10 menit main game baru
    if GAME_CHANGE_STATE["is_changing"]:
        time_since_change = time.time() - GAME_CHANGE_STATE["change_start_time"]
        if time_since_change >= 600:  # 10 menit
            add_log("🕒 10 minutes gameplay completed after game change. Stopping script.", important=True)
            # Kill semua proses sebelum exit
            for acc in accounts:
                pid = acc.get("pid")
                if pid and is_roblox_process_running(pid):
                    aggressive_kill_process(pid, acc)
            os._exit(0)  # Stop script
    
    # Check untuk ganti akun setelah 10 menit main game baru  
    if ACCOUNT_CHANGE_STATE["is_changing"]:
        time_since_change = time.time() - ACCOUNT_CHANGE_STATE["change_start_time"]
        if time_since_change >= 600:  # 10 menit
            add_log("🕒 10 minutes gameplay completed after account change. Switching accounts.", important=True)
            # Kill semua proses
            for acc in accounts:
                pid = acc.get("pid")
                if pid and is_roblox_process_running(pid):
                    aggressive_kill_process(pid, acc)
            # Reset state untuk ganti akun berikutnya
            ACCOUNT_CHANGE_STATE["is_changing"] = False
            return  # Skip proses berikutnya karena akan ganti akun
    
    # FORCE LAUNCH jika sedang dalam mode ganti game (bypass semua status check)
    if GAME_CHANGE_STATE["is_changing"]:
        add_log("🚀 FORCE LAUNCH: Launching new games after game change", important=True)
        for acc in accounts:
            if acc.get("pid") is None:  # Hanya launch yang belum ada PID
                cookie = acc["cookie"]
                name = acc["username"]
                game_id = acc["game_id"]  # PASTI dari daftar gameid.json
                
                add_log(f"🚀 Force Launch: {name} -> {get_game_name(game_id)}", important=True)
                
                new_pid, reason = launch_via_protocol(cookie, game_id, "")
                
                if new_pid:
                    acc["last_launch"] = time.time()
                    acc["pid"] = new_pid
                    acc["launch_time"] = time.time()
                    acc["json_start_time"] = None
                    acc["json_active"] = False
                    acc["follow_relaunch"] = False
                    
                    # Catat game yang dimainkan
                    record_current_game(name, game_id)
                    
                    rename_window_async(new_pid, name, max_attempts=999, delay=5)
                    quick_rename_async(new_pid, name)
                    
                    add_log(f"✅ {name} successfully launched new game", important=True)
                    
                    # Delay antara launch
                    launch_delay = float(cfg.get("launchDelay", 15))
                    if launch_delay > 0:
                        time.sleep(launch_delay)
                else:
                    add_log(f"❌ {name} failed to launch: {reason}", important=True)
                    # Tetap lanjut ke akun berikutnya meskipun gagal
        
        # Setelah semua dillaunch, return untuk skip proses normal
        return
    
    # Check interval utama untuk ganti game (120 menit sejak script start)
    change_game_enabled = cfg.get("change_and_close_game", False)
    change_game_interval = float(cfg.get("change_and_close_game_interval", 120)) * 60
    
    if (change_game_enabled and change_game_interval > 0 and 
        not GAME_CHANGE_STATE["is_changing"] and
        GAME_CHANGE_STATE["last_change_time"] == 0):
        
        current_time = time.time()
        
        if current_time - SCRIPT_START_TIME >= change_game_interval:
            add_log(f"🕒 Game change interval reached ({change_game_interval/60} minutes)", important=True)
            change_game_for_all_accounts(accounts, cfg)
            return  # Skip proses normal setelah initiate game change
    
    # Check interval utama untuk ganti akun (120 menit sejak script start)  
    change_akun_enabled = cfg.get("change_akun", False)
    change_akun_interval = float(cfg.get("change_akun_interval", 120)) * 60
    
    if (change_akun_enabled and change_akun_interval > 0 and 
        not ACCOUNT_CHANGE_STATE["is_changing"] and
        ACCOUNT_CHANGE_STATE["last_change_time"] == 0):
        
        current_time = time.time()
        
        if current_time - SCRIPT_START_TIME >= change_akun_interval:
            add_log(f"🕒 Account change interval reached ({change_akun_interval/60} minutes)", important=True)
            rotate_accounts(accounts, cfg)
            return  # Skip proses normal setelah initiate account change

    launch_delay = float(cfg.get("launchDelay", 15))
    first_check_minutes = int(cfg.get("first_check", 3))
    
    # Restart check
    if cfg.get("EnableRestart", True):
        current_time = time.time()
        kill_interval_hours = float(cfg.get("Restart", 1))
        kill_interval_seconds = kill_interval_hours * 3600
        
        if not hasattr(proc_cycle, "last_kill_time"):
            proc_cycle.last_kill_time = current_time
        
        if current_time - proc_cycle.last_kill_time >= kill_interval_seconds:
            add_log(f"Restart all - {kill_interval_hours}h interval", important=True)
            
            killed_count = 0
            for acc in accounts:
                pid = acc.get("pid")
                if pid and is_roblox_process_running(pid):
                    if aggressive_kill_process(pid, acc):
                        killed_count += 1
            
            proc_cycle.last_kill_time = current_time

    # Follow player
    follow_enabled = cfg.get("FollowPlayer", False)
    follow_username = cfg.get("FollowPlayerUsername", "")
    follow_check_interval = int(cfg.get("FollowCheckInterval", 30))
    
    if follow_enabled and follow_username and len(accounts) > 0:
        now = time.time()
        if now - follow_state.get("last_check", 0) >= follow_check_interval:
            follow_state["last_check"] = now
            
            if not follow_state.get("target_user_id"):
                first_cookie = accounts[0]["cookie"]
                target_id = get_user_id_by_username(follow_username, first_cookie)
                if target_id:
                    follow_state["target_user_id"] = target_id
                    add_log(f"Follow: Found {follow_username}", important=True)
            
            if follow_state.get("target_user_id"):
                target_id = follow_state["target_user_id"]
                first_cookie = accounts[0]["cookie"]
                search_game_id = accounts[0].get("game_id") or cfg.get("gameId")
                
                job_id, server_info = find_player_server(search_game_id, target_id, first_cookie)
                
                if job_id:
                    current_job = follow_state.get("current_job_id")
                    if job_id != current_job:
                        add_log(f"Follow: Switching server", important=True)
                        follow_state["current_job_id"] = job_id
                        
                        for acc in accounts:
                            pid = acc.get("pid")
                            if pid and is_roblox_process_running(pid):
                                aggressive_kill_process(pid, acc)
                                acc["follow_relaunch"] = True

    # RAM check
    if cfg.get("Kill Process > Ram", False):
        ram_threshold = float(cfg.get("Ram Usage (Each Process)", 3))
        check_and_kill_high_ram_processes(accounts, ram_threshold)

    # Process each account dengan LOGIKA BARU
    for acc in accounts:
        cookie = acc["cookie"]
        name = acc["username"]
        game_id = acc.get("game_id") or cfg.get("gameId")
        private_link = acc.get("private_link") or cfg.get("private_link", "")

        # Determine status menggunakan fungsi baru
        status = determine_account_status(acc, workspace_folder, first_check_minutes)
        
        # ACTION berdasarkan status:
        
        # 1. Status NEEDS_KILL → Kill roblox
        if status == "needs_kill":
            pid = acc.get("pid")
            if pid and is_roblox_process_running(pid):
                add_log(f"🔴 {name}: JSON inactive too long - Killing", important=True)
                aggressive_kill_process(pid, acc)
            continue
        
        # 2. Status OFFLINE + tidak ada client → Launch roblox
        if status == "offline":
            if is_cookie_death(name):
                continue
                
            now = time.time()
            cooldown = float(cfg.get("accountLaunchCooldown", 30))
            
            # Check cooldown
            if now - acc.get("last_launch", 0) >= cooldown:
                kill_duplicate_running_accounts(accounts, name)
                add_log(f"🚀 Launch: {name}", important=True)
                
                if follow_enabled and follow_state.get("current_job_id"):
                    new_pid, reason = launch_to_specific_server(
                        cookie, game_id, follow_state["current_job_id"]
                    )
                else:
                    new_pid, reason = launch_via_protocol(cookie, game_id, private_link)
                
                if new_pid:
                    # RESET SEMUA TIMER saat launch baru
                    acc["last_launch"] = time.time()
                    acc["pid"] = new_pid
                    acc["launch_time"] = time.time()
                    acc["json_start_time"] = None  # RESET - Mulai dari 0
                    acc["json_active"] = False      # RESET - Belum ada JSON
                    acc["follow_relaunch"] = False

                    current_game_id = acc.get("game_id") or cfg.get("gameId")
                    record_current_game(name, current_game_id)                   
                    rename_window_async(new_pid, name, max_attempts=999, delay=5)
                    quick_rename_async(new_pid, name)
                    
                    def _delayed_save():
                        time.sleep(3)
                        save_accounts_data(accounts)
                    threading.Thread(target=_delayed_save, daemon=True).start()

                    if launch_delay > 0:
                        time.sleep(launch_delay)
                else:
                    acc["death_attempt"] += 1
                    add_log(f"❌ Launch failed ({acc['death_attempt']}/{MAX_DEATH_LAUNCH_ATTEMPT}): {name}", important=True)

                    if acc["death_attempt"] >= MAX_DEATH_LAUNCH_ATTEMPT:
                        add_log(f"☠️ Cookie DEAD detected: {name}", important=True)
                        save_death_cookie(name)
        
        # 3. Status WAITING atau IN_GAME → Tidak ada action (biarkan berjalan)
        elif status in ["waiting", "in_game"]:
            # Tidak perlu update manual, sudah dihandle di determine_account_status()
            pass

# ----------------------------
# Main Logic
# ----------------------------
def main():
    global SCRIPT_START_TIME, GAME_CHANGE_STATE, ACCOUNT_CHANGE_STATE, ACCOUNT_ROTATION_INDEX, accounts
    
    # Reset state
    SCRIPT_START_TIME = time.time()
    GAME_CHANGE_STATE = {"last_change_time": 0, "is_changing": False, "change_start_time": 0}
    ACCOUNT_CHANGE_STATE = {"last_change_time": 0, "is_changing": False, "change_start_time": 0}
    ACCOUNT_ROTATION_INDEX = 0

    cfg = load_or_create_config()
    try:
        workspace_folder, autoexec_folder = resolve_executor_paths(cfg)
    except Exception as e:
        console.print(f"[red]Executor setup error:[/red] {e}")
        return

    sync_script_folder_to_autoexec(autoexec_folder)
    show_bf_stats = cfg.get("Show BF Stats", True)
    ensure_game_folders()

    if not ensure_cookie_file():
        return

    # Load & validate cookies (3x retry)
    # ---------------------------------
    cookies = load_cookies()
    if not cookies:
        console.print("cookies.txt is empty. Add 1 cookie per line.")
        return

    accounts = []
    death_entries = []

    for line_no, cookie in enumerate(cookies, start=1):
        cookie = cookie.strip()
        if not cookie:
            continue

        username = None

        for attempt in range(3):
            try:
                _, username = get_user_from_cookie(cookie, max_retries=1)
                if username:
                    break
            except Exception:
                pass
            time.sleep(1)

        if username:
            accounts.append({
                "cookie": cookie,
                "username": username,
                "pid": None,
                "death_attempt": 0
            })
        else:
            death_entries.append({
                "line": line_no,
                "cookie": cookie[:60] + "...",
                "reason": "failed_get_username_3x"
            })

    # Save & log invalid cookies found during load
    if death_entries:
        save_death_cookies(death_entries)
        add_log(
            f"☠️ {len(death_entries)} cookies INVALID during load (saved to deathcookies.json)",
            important=True
        )

    # Stop script if no valid cookies
    if not accounts:
        add_log("❌ All cookies are INVALID. Script stopped.", important=True)
        return

    ensure_server_file()
    server_links = load_servers()

    try:
        os.makedirs(SAVES_FOLDER, exist_ok=True)
    except:
        pass

    all_accounts = []
    for idx, ck in enumerate(cookies):
        uid, uname = get_user_from_cookie(ck, max_retries=3)
        if uid:
            acc_data = {
                "cookie": ck,
                "user_id": uid,
                "username": uname,
                "pid": None,
                "launch_time": None,
                "json_start_time": None,
                "json_active": False,
                "death_attempt": 0,
            }
            
            if idx < len(server_links) and server_links[idx]:
                link = server_links[idx]
                game_id, private_code = parse_game_link(link)
                
                if game_id:
                    acc_data["game_id"] = game_id
                    acc_data["private_link"] = link if private_code else ""
                    console.print(f"Loaded {uname} - Game: {game_id}" + 
                                (" [Private]" if private_code else ""))
            else:
                console.print(f"Loaded {uname}")
            
            all_accounts.append(acc_data)

    if not all_accounts:
        console.print("No valid accounts.")
        return

    if cfg.get("SortAccounts", True):
        all_accounts.sort(key=lambda a: a["username"].lower())

    start_rename_monitor()
    periodic_rename_check()

    follow_enabled = cfg.get("FollowPlayer", False)
    follow_username = cfg.get("FollowPlayerUsername", "")
    if follow_enabled and follow_username:
        console.print(f"Follow Player Mode: ENABLED - Target: {follow_username}")
    else:
        console.print(f"Follow Player Mode: DISABLED")

    # Gunakan fungsi get_active_accounts untuk mendapatkan accounts aktif
    accounts = get_active_accounts(all_accounts, cfg)

    total_instances = int(cfg.get("TotalInstance", 10))
    if total_instances < len(accounts):
        accounts = accounts[:total_instances]

    follow_state = {
        "last_check": 0,
        "target_user_id": None,
        "current_job_id": None
    }

    console.print("Searching for running Roblox processes...")
    matched = match_existing_processes_to_accounts(
        accounts, 
        workspace_folder, 
        int(cfg.get("first_check", 3))
    )
    if matched > 0:
        console.print(f"Matched {matched} running processes")
    else:
        add_log("No running processes, launching...", important=True)
        proc_cycle(accounts, cfg, follow_state, workspace_folder)        

    time.sleep(1)
    console.clear()

    # Main loop - check setiap detik
    with Live(console=console, screen=True, refresh_per_second=1) as live:
        last_proc_cycle = time.time()
        proc_cycle_interval = 5  # Check every 5 seconds
        
        while True:
            now = time.time()

            # Run proc_cycle setiap interval
            if now >= last_proc_cycle + proc_cycle_interval:
                proc_cycle(accounts, cfg, follow_state, workspace_folder)
                last_proc_cycle = now

            follow_mode = "ENABLED" if cfg.get("FollowPlayer", False) else "DISABLED"
            follow_target = cfg.get("FollowPlayerUsername", "N/A")
            first_check_min = cfg.get("first_check", 3)
            death = load_death_cookies()
            total_cookies = len(accounts)
            total_instance = sum(
                1 for acc in accounts
                if acc.get("pid") and is_roblox_process_running(acc.get("pid"))
            )           
            title_parts = [f"Roblox Multi-Instance v3"]
            title_parts.append(f"First Check: {first_check_min}min | "f"Instance: {total_instance} | "f"Cookies: {total_cookies} | "f"Cookies Dead: {len(death)}")
            if cfg.get("FollowPlayer", False):
                title_parts.append(f"Following: {follow_target}")
            
            table = Table(
                title="\n".join(title_parts),
                show_header=True, 
                header_style="bold magenta",
                box=None
            )
            
            if show_bf_stats:
                table.add_column("No.", justify="right", width=3)
                table.add_column("Username", min_width=8)
                table.add_column("Level", width=5)
                table.add_column("Game", min_width=12)
                table.add_column("Server", width=8)
                table.add_column("Beli", width=10)
                table.add_column("Frag", width=6)
                table.add_column("Status", min_width=20)
                table.add_column("Race", width=8)
                table.add_column("Meele", min_width=10)                
                table.add_column("DF", min_width=10)
                table.add_column("Sword", min_width=10)
                table.add_column("Gun", min_width=10)
                table.add_column("Fruits", min_width=10)
            else:
                table.add_column("No.", justify="right", width=3)
                table.add_column("Username", min_width=8)
                table.add_column("Game", min_width=15)
                table.add_column("Server", width=10)
                table.add_column("Status", min_width=20)

            for i, acc in enumerate(accounts, start=1):
                name = acc["username"]
                
                game_id = acc.get("game_id") or cfg.get("gameId")
                game_name = get_game_name(game_id)
                
                has_private = bool(acc.get("private_link") or cfg.get("private_link"))
                server_info = "[Pvt]" if has_private else "[Pub]"

                # Get status dengan fungsi baru
                status = determine_account_status(acc, workspace_folder, int(cfg.get("first_check", 3)))
                
                # Format status display
                time_diff = get_json_time_diff(workspace_folder, name)
                launch_time = acc.get("launch_time")
                
                if status == "in_game":
                    if time_diff is not None:
                        status_msg = f"In Game | JSON: {int(time_diff)}s"
                    else:
                        status_msg = "In Game "
                    status_style = "bold green"
                    
                elif status == "offline":
                    status_msg = "Offline "
                    status_style = "bold red"
                    
                elif status == "waiting":
                    if launch_time is not None:
                        first_check_seconds = int(cfg.get("first_check", 3)) * 60
                        remaining = max(0, first_check_seconds - int(time.time() - launch_time))
                        status_msg = f" Waiting ({remaining}s)"
                    else:
                        status_msg = " Waiting"
                    status_style = "bold yellow"
                    
                elif status == "needs_kill":
                    status_msg = " JSON Dead - Killing"
                    status_style = "bold red"
                
                # BF Stats Safe Loader
                bf = load_bf_stats(workspace_folder, acc["username"])

                lvl = "-"
                beli = "-"
                frags = "-"
                race = "-"
                meele = "-"
                sword = "-"
                gun = "-"
                fruit_list = "-"
                df = "-"

                if bf:
                    # Level
                    lvl = f"[bold green]{bf.get('level','-')}[/]"

                    # Beli
                    beli_raw = bf.get("beli")
                    if isinstance(beli_raw, int):
                        beli = f"[cyan]{beli_raw:,}[/]"
                    else:
                        beli = "-"

                    # Fragments
                    fr_raw = bf.get("frags")
                    if isinstance(fr_raw, int):
                        frags = f"[bright_blue]{fr_raw}[/]"
                    else:
                        frags = "-"

                    # Race + Melee
                    race = f"[magenta]{bf.get('race','-')}[/]"
                    meele_raw = bf.get("meele", "-")
                    meele = f"[cyan]{meele_raw}[/]" if meele_raw not in ("", "-") else "-"

                    # DF (EquippedFruit)
                    df_raw = bf.get("fruit_equipped", "")
                    df = f"[bold yellow]{df_raw}[/]" if df_raw not in ("", "-") else "-"

                    # Sword / Gun / Fruits (rarity color)
                    def color_rarity(items):
                        colored = []
                        for (tier, name) in items:
                            if tier == "Mythical":
                                colored.append(f"[bold red]{name}[/]")
                            elif tier == "Legendary":
                                colored.append(f"[bold yellow]{name}[/]")
                        return ", ".join(colored) if colored else "-"

                    sword = color_rarity(bf.get("swords", []))
                    gun = color_rarity(bf.get("guns", []))
                    fruit_list = color_rarity(bf.get("fruits", []))

                username_text = Text(name, style=status_style)
                game_text = Text(game_name, style="bold cyan")
                server_text = Text(server_info, style="magenta")
                status_text = Text(status_msg, style=status_style)

                if show_bf_stats:
                    table.add_row(
                        str(i),
                        username_text,
                        lvl,
                        game_text,
                        server_text,
                        beli,
                        frags,
                        status_text,
                        race,
                        meele,
                        df,
                        sword,
                        gun,
                        fruit_list
                    )
                else:
                    table.add_row(
                        str(i),
                        username_text,
                        game_text,
                        server_text,
                        status_text
                    )

            if LOG_MESSAGES:
                if show_bf_stats:
                    empty_row = ("", "", "", "", "", "", "", "", "", "", "", "", "", "")
                    log_header = ("", Text("=== Logs ===", style="bold cyan"), "", "", "", "", "", "", "", "", "", "", "", "")
                    def make_log_row(msg):
                        return ("", Text(msg, style="dim"), "", "", "", "", "", "", "", "", "", "", "", "")
                else:
                    empty_row = ("", "", "", "", "")
                    log_header = ("", Text("=== Logs ===", style="bold cyan"), "", "", "")
                    def make_log_row(msg):
                        return ("", Text(msg, style="dim"), "", "", "")
                
                table.add_row(*empty_row)
                table.add_row(*log_header)
                for log_msg in LOG_MESSAGES:
                    table.add_row(*make_log_row(log_msg))

            live.update(table)
            time.sleep(1)


if __name__ == "__main__":
        console.print("=" * 60)
        console.print("Roblox Multi-Instance v3")
        console.print("Features:")
        console.print("  - JSON Status Checker")
        console.print("  - Follow Player Mode")
        console.print("  - Per-Account Server Config")
        start_arrage_exe()
        start_ova_exe()
        try:
            main()
        finally:
            kill_ova_exe()
            kill_arrage_exe()
