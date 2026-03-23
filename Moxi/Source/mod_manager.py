import os
import re
import io
import json
import string
import zipfile
import requests


DATA_DIR      = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Moxi")
INSTALLED_DB  = os.path.join(DATA_DIR, "installed.json")
MOD_INDEX_URL  = "https://raw.githubusercontent.com/KerbalMissile/Moxi/main/Mods/ModIndex.json"
GAME_INDEX_URL = "https://raw.githubusercontent.com/KerbalMissile/Moxi/main/Games/GameIndex.json"
MOXI_REPO      = "KerbalMissile/Moxi"

GAME_ID_MAP = {
    "planet_crafter": "1284190",
}

MODLOADER_CONFIGS = {
    "planet_crafter": {
        "type":       "static",
        "url":        "https://github.com/BepInEx/BepInEx/releases/download/v5.4.23.2/BepInEx_win_x64_5.4.23.2.zip",
        "check_path": os.path.join("BepInEx", "core", "BepInEx.dll"),
        "mod_dest":   os.path.join("BepInEx", "plugins"),
    },
    "subnautica": {
        "type":       "github_latest",
        "repo":       "toebeann/BepInEx.Subnautica",
        "asset":      "Tobey.s.BepInEx.Pack.for.Subnautica.zip",
        "check_path": os.path.join("BepInEx", "core", "BepInEx.dll"),
        "mod_dest":   os.path.join("BepInEx", "plugins"),
    },
    "subnautica_bz": {
        "type":       "github_latest",
        "repo":       "toebeann/BepInEx.SubnauticaZero",
        "asset":      "Tobey.s.BepInEx.Pack.for.Subnautica.Below.Zero.zip",
        "check_path": os.path.join("BepInEx", "core", "BepInEx.dll"),
        "mod_dest":   os.path.join("BepInEx", "plugins"),
    },
    "slime_rancher": {
        "type":       "github_latest",
        "repo":       "SlimeRancherModding/SRML",
        "asset":      "SRMLInstaller",
        "check_path": os.path.join("SRML", "Mods"),
        "mod_dest":   os.path.join("SRML", "Mods"),
        "asset_match": "startswith",
    },
    "slime_rancher_2": {
        "type":       "github_latest",
        "repo":       "LavaGang/MelonLoader",
        "asset":      "MelonLoader.x64.zip",
        "asset_x86":  "MelonLoader.x86.zip",
        "check_path": "MelonLoader",
        "mod_dest":   "Mods",
        "arch_detect": True,
    },
    "dyson_sphere": {
        "type":       "static",
        "url":        "https://github.com/BepInEx/BepInEx/releases/download/v5.4.23.2/BepInEx_win_x64_5.4.23.2.zip",
        "check_path": os.path.join("BepInEx", "core", "BepInEx.dll"),
        "mod_dest":   os.path.join("BepInEx", "plugins"),
    },
    "schedule_i": {
        "type":       "github_latest",
        "repo":       "LavaGang/MelonLoader",
        "asset":      "MelonLoader.x64.zip",
        "asset_x86":  "MelonLoader.x86.zip",
        "check_path": "MelonLoader",
        "mod_dest":   "Mods",
        "arch_detect": True,
    },
}

THUNDERSTORE_CONFIGS = {
    "dyson_sphere": {
        "community": "dyson-sphere-program",
        "mod_dest":  os.path.join("BepInEx", "plugins"),
    },
    "schedule_i": {
        "community": "schedule-i",
        "mod_dest":  "Mods",
    },
}


class ModManager:
    def __init__(self):
        self.installed = {}
        os.makedirs(DATA_DIR, exist_ok=True)
        self._load_installed()

    def _load_installed(self):
        if os.path.exists(INSTALLED_DB):
            try:
                with open(INSTALLED_DB, "r") as f:
                    self.installed = json.load(f)
            except Exception:
                self.installed = {}
        else:
            self.installed = {}

    def _save_installed(self):
        with open(INSTALLED_DB, "w") as f:
            json.dump(self.installed, f, indent=2)

    def check_modloader(self, game_key, install_dir):
        cfg = MODLOADER_CONFIGS.get(game_key)
        if not cfg:
            return True
        return os.path.exists(os.path.join(install_dir, cfg["check_path"]))

    def get_mod_dest(self, game_key):
        cfg = MODLOADER_CONFIGS.get(game_key)
        return cfg["mod_dest"] if cfg else os.path.join("BepInEx", "plugins")

    def _resolve_modloader_url(self, game_key):
        import platform
        cfg = MODLOADER_CONFIGS.get(game_key)
        if not cfg:
            raise ValueError(f"No modloader config for: {game_key}")

        if cfg["type"] == "static":
            return cfg["url"]

        if cfg["type"] == "github_latest":
            api_url = f"https://api.github.com/repos/{cfg['repo']}/releases/latest"
            r = requests.get(api_url, timeout=10)
            r.raise_for_status()
            assets = r.json().get("assets", [])

            if cfg.get("arch_detect"):
                bits = platform.architecture()[0]
                asset_name = cfg["asset"] if bits == "64bit" else cfg.get("asset_x86", cfg["asset"])
            else:
                asset_name = cfg["asset"]

            match_mode = cfg.get("asset_match", "exact")
            for asset in assets:
                name = asset["name"]
                if match_mode == "startswith" and name.startswith(asset_name) and name.endswith(".zip"):
                    return asset["browser_download_url"]
                elif match_mode == "exact" and name == asset_name:
                    return asset["browser_download_url"]

            raise ValueError(f"No matching asset for {cfg['repo']}: '{asset_name}'")

        raise ValueError(f"Unknown modloader type: {cfg['type']}")

    def install_modloader(self, game_key, install_dir, progress_cb=None):
        url = self._resolve_modloader_url(game_key)
        r   = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()

        total      = int(r.headers.get("content-length", 0))
        downloaded = 0
        buf        = io.BytesIO()

        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                buf.write(chunk)
                downloaded += len(chunk)
                if progress_cb and total > 0:
                    progress_cb(downloaded / total)

        buf.seek(0)
        with zipfile.ZipFile(buf) as zf:
            zf.extractall(install_dir)

    def check_bepinex(self, install_dir):
        dll = os.path.join(install_dir, "BepInEx", "core", "BepInEx.dll")
        return os.path.exists(dll)

    def install_bepinex(self, install_dir, game_key, progress_cb=None):
        return self.install_modloader(game_key, install_dir, progress_cb)

    def fetch_mod_index(self):
        r = requests.get(MOD_INDEX_URL, timeout=10)
        r.raise_for_status()
        return r.json()

    def fetch_game_index(self):
        r = requests.get(GAME_INDEX_URL, timeout=10)
        r.raise_for_status()
        return r.json()

    def fetch_thunderstore_packages(self, game_key):
        cfg = THUNDERSTORE_CONFIGS.get(game_key)
        if not cfg:
            return []
        community = cfg["community"]
        mods      = []
        page      = 1

        while True:
            url = f"https://thunderstore.io/c/{community}/api/v1/package/?page={page}"
            r   = requests.get(url, timeout=15)
            if r.status_code == 404:
                break
            r.raise_for_status()
            data     = r.json()
            packages = data if isinstance(data, list) else data.get("results", [])

            for pkg in packages:
                if pkg.get("is_deprecated"):
                    continue
                versions = pkg.get("versions", [])
                if not versions:
                    continue
                latest = versions[0]
                deps   = []
                for dep in latest.get("dependencies", []):
                    parts = dep.split("-")
                    if len(parts) >= 2:
                        deps.append(f"{parts[0]}-{parts[1]}")
                mods.append({
                    "id":          f"{pkg['owner']}-{pkg['name']}",
                    "name":        pkg["name"],
                    "author":      pkg["owner"],
                    "version":     latest["version_number"],
                    "description": latest.get("description", ""),
                    "download_url": latest["download_url"],
                    "dependencies": deps,
                    "source":      "thunderstore",
                    "files": [
                        {
                            "url":         latest["download_url"],
                            "filename":    f"{pkg['name']}.zip",
                            "destination": cfg["mod_dest"],
                            "extract":     True,
                        }
                    ],
                })

            if isinstance(data, list) or not data.get("next"):
                break
            page += 1

        return mods

    def install_mod_thunderstore(self, game_key, mod, game_install_dir, progress_cb=None):
        file_entry   = mod["files"][0]
        url          = file_entry["url"]
        dest_dir     = os.path.join(game_install_dir, file_entry["destination"])
        os.makedirs(dest_dir, exist_ok=True)

        r     = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done  = 0
        buf   = io.BytesIO()

        for chunk in r.iter_content(chunk_size=8192):
            if chunk:
                buf.write(chunk)
                done += len(chunk)
                if progress_cb and total > 0:
                    progress_cb(done / total)

        buf.seek(0)
        installed_files = []

        with zipfile.ZipFile(buf) as zf:
            for member in zf.namelist():
                if member.endswith("/"):
                    continue
                basename = os.path.basename(member)
                if not basename:
                    continue
                dest_path = os.path.join(dest_dir, basename)
                with zf.open(member) as src, open(dest_path, "wb") as dst:
                    dst.write(src.read())
                installed_files.append(dest_path)

        if game_key not in self.installed:
            self.installed[game_key] = {}

        self.installed[game_key][mod["id"]] = {
            "name":    mod["name"],
            "version": mod["version"],
            "files":   installed_files,
            "enabled": True,
        }
        self._save_installed()

    def check_for_app_update(self):
        url = f"https://api.github.com/repos/{MOXI_REPO}/releases/latest"
        r   = requests.get(url, timeout=8)
        r.raise_for_status()
        data      = r.json()
        tag       = data.get("tag_name", "").lstrip("v")
        changelog = data.get("body", "")
        assets    = data.get("assets", [])
        dl_url    = None
        for asset in assets:
            if asset["name"].startswith("Moxi-v") and asset["name"].endswith("-Installer.exe"):
                dl_url = asset["browser_download_url"]
                break
        return tag, changelog, dl_url

    def download_installer(self, dl_url, version, progress_cb=None):
        updates_dir = os.path.join(DATA_DIR, "updates")
        os.makedirs(updates_dir, exist_ok=True)
        dest = os.path.join(updates_dir, f"Moxi-v{version}-Installer.exe")

        r     = requests.get(dl_url, stream=True, timeout=120)
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done  = 0

        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    done += len(chunk)
                    if progress_cb and total > 0:
                        progress_cb(done / total)
        return dest

    def write_updated_flag(self, version, changelog):
        path = os.path.join(DATA_DIR, "updated.json")
        with open(path, "w") as f:
            json.dump({"version": version, "changelog": changelog}, f, indent=2)

    def read_and_clear_updated_flag(self):
        path = os.path.join(DATA_DIR, "updated.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r") as f:
                data = json.load(f)
            os.remove(path)
            return data
        except Exception:
            return None

    def resolve_dependencies(self, game_key, mod, all_mods):
        mod_by_id = {m["id"]: m for m in all_mods}
        resolved  = []
        visited   = set()

        def walk(m):
            mid = m["id"]
            if mid in visited:
                return
            visited.add(mid)
            for dep_id in m.get("dependencies", []):
                if dep_id in mod_by_id:
                    walk(mod_by_id[dep_id])
            if not self.is_installed(game_key, mid) and mid != mod["id"]:
                resolved.append(m)

        walk(mod)
        return resolved

    def is_installed(self, game_key, mod_id):
        return self.installed.get(game_key, {}).get(mod_id) is not None

    def install_mod(self, game_key, mod, game_install_dir, progress_cb=None):
        files = mod.get("files", [])
        installed_files = []

        for i, file_entry in enumerate(files):
            url      = file_entry["url"]
            filename = file_entry["filename"]
            dest_rel = file_entry["destination"]
            dest_dir = os.path.join(game_install_dir, dest_rel)
            os.makedirs(dest_dir, exist_ok=True)
            dest_path = os.path.join(dest_dir, filename)

            r = requests.get(url, stream=True, timeout=30)
            r.raise_for_status()

            total = int(r.headers.get("content-length", 0))
            downloaded = 0

            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_cb and total > 0:
                            progress_cb((i + downloaded / total) / len(files))

            installed_files.append(dest_path)

        if game_key not in self.installed:
            self.installed[game_key] = {}

        self.installed[game_key][mod["id"]] = {
            "name":    mod["name"],
            "version": mod["version"],
            "files":   installed_files,
            "enabled": True,
        }
        self._save_installed()

    def uninstall_mod(self, game_key, mod_id):
        entry = self.installed.get(game_key, {}).get(mod_id)
        if not entry:
            return

        for path in entry.get("files", []):
            for candidate in [path, path + ".disabled"]:
                if os.path.exists(candidate):
                    try:
                        os.remove(candidate)
                    except Exception:
                        pass

        del self.installed[game_key][mod_id]
        self._save_installed()

    def enable_mod(self, game_key, mod_id):
        entry = self.installed.get(game_key, {}).get(mod_id)
        if not entry:
            return
        updated = []
        for path in entry.get("files", []):
            if path.endswith(".disabled"):
                enabled_path = path[:-len(".disabled")]
                if os.path.exists(path):
                    os.rename(path, enabled_path)
                updated.append(enabled_path)
            else:
                updated.append(path)
        entry["files"]   = updated
        entry["enabled"] = True
        self._save_installed()

    def disable_mod(self, game_key, mod_id):
        entry = self.installed.get(game_key, {}).get(mod_id)
        if not entry:
            return
        updated = []
        for path in entry.get("files", []):
            if path.endswith(".dll") and os.path.exists(path):
                disabled = path + ".disabled"
                os.rename(path, disabled)
                updated.append(disabled)
            else:
                updated.append(path)
        entry["files"]   = updated
        entry["enabled"] = False
        self._save_installed()


class SteamScanner:
    def __init__(self, supported_games: dict):
        self.supported = supported_games

    def scan(self):
        steamapps_paths = self._find_steamapps_dirs()
        found = []

        for sa_path in steamapps_paths:
            for appid, entry in self.supported.items():
                acf_path = os.path.join(sa_path, f"appmanifest_{appid}.acf")
                if os.path.exists(acf_path):
                    install_name = self._parse_install_dir(acf_path)
                    install_dir  = os.path.join(sa_path, "common", install_name) if install_name else None
                    found.append({
                        "appid":       appid,
                        "name":        entry["name"],
                        "supported":   entry["supported"],
                        "game_key":    entry.get("game_key", ""),
                        "acf_path":    acf_path,
                        "install_dir": install_dir,
                    })

        seen   = set()
        unique = []
        for item in found:
            if item["appid"] not in seen:
                seen.add(item["appid"])
                unique.append(item)

        return unique

    def _parse_install_dir(self, acf_path):
        try:
            with open(acf_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            m = re.search(r'"installdir"\s+"([^"]+)"', content)
            return m.group(1) if m else None
        except Exception:
            return None

    def _find_steamapps_dirs(self):
        candidates = []
        steam_root  = self._steam_root_from_registry() or self._steam_root_fallback()

        if steam_root:
            default_sa = os.path.join(steam_root, "steamapps")
            if os.path.isdir(default_sa):
                candidates.append(default_sa)
            vdf_path = os.path.join(default_sa, "libraryfolders.vdf")
            if os.path.exists(vdf_path):
                for p in self._parse_libraryfolders(vdf_path):
                    sa = os.path.join(p, "steamapps")
                    if os.path.isdir(sa) and sa not in candidates:
                        candidates.append(sa)

        if not candidates:
            candidates = self._brute_force_scan()

        return candidates

    def _steam_root_from_registry(self):
        try:
            import winreg
            key  = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam")
            path, _ = winreg.QueryValueEx(key, "InstallPath")
            winreg.CloseKey(key)
            if os.path.isdir(path):
                return path
        except Exception:
            pass
        try:
            import winreg
            key  = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam")
            path, _ = winreg.QueryValueEx(key, "SteamPath")
            winreg.CloseKey(key)
            path = path.replace("/", "\\")
            if os.path.isdir(path):
                return path
        except Exception:
            pass
        return None

    def _steam_root_fallback(self):
        for p in [
            os.path.join(os.environ.get("PROGRAMFILES(X86)", ""), "Steam"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Steam"),
        ]:
            if os.path.isdir(p):
                return p
        return None

    def _brute_force_scan(self):
        candidates = []
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if not os.path.exists(drive):
                continue
            for fragment in [
                os.path.join(drive, "Program Files (x86)", "Steam", "steamapps"),
                os.path.join(drive, "Program Files", "Steam", "steamapps"),
                os.path.join(drive, "Steam", "steamapps"),
                os.path.join(drive, "SteamLibrary", "steamapps"),
            ]:
                if os.path.isdir(fragment) and fragment not in candidates:
                    candidates.append(fragment)
        return candidates

    def _parse_libraryfolders(self, vdf_path):
        paths = []
        try:
            with open(vdf_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            for m in re.findall(r'"path"\s+"([^"]+)"', content):
                p = m.replace("\\\\", "\\")
                if os.path.isdir(p):
                    paths.append(p)
        except Exception:
            pass
        return paths


class GameAdapter:
    def get_install_path(self):
        raise NotImplementedError

    def get_plugins_path(self):
        raise NotImplementedError


class PlanetCrafterAdapter(GameAdapter):
    def __init__(self, install_dir):
        self.install_dir = install_dir

    def get_install_path(self):
        return self.install_dir

    def get_plugins_path(self):
        return os.path.join(self.install_dir, "BepInEx", "plugins")
