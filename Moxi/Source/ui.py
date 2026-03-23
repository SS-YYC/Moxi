import os
import sys
import json
import io
import tkinter as tk
import customtkinter as ctk
from PIL import Image, ImageTk
import threading
import requests

from mod_manager import ModManager, SteamScanner

SUPPORTED_GAMES = {
    "1284190": {"name": "Planet Crafter",        "supported": True, "game_key": "planet_crafter"},
    "264710":  {"name": "Subnautica",             "supported": True, "game_key": "subnautica"},
    "848450":  {"name": "Subnautica: Below Zero", "supported": True, "game_key": "subnautica_bz"},
    "433340":  {"name": "Slime Rancher",          "supported": True, "game_key": "slime_rancher"},
    "1657630": {"name": "Slime Rancher 2",        "supported": True, "game_key": "slime_rancher_2"},
    "1366540": {"name": "Dyson Sphere Program",   "supported": True, "game_key": "dyson_sphere"},
}

CUSTOM_ART_URLS = {
    "3527290": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/3527290/31bac6b2eccf09b368f5e95ce510bae2baf3cfcd/header.jpg?t=1773856924",
}

THUNDERSTORE_GAMES = {"dyson_sphere"}

GAME_KEY_TO_NAME    = {v["game_key"]: v["name"] for v in SUPPORTED_GAMES.values()}
GAME_NAMES          = [v["name"] for v in SUPPORTED_GAMES.values() if v["supported"]]
GAME_NAMES_ALL      = [v["name"] for v in SUPPORTED_GAMES.values()]

MOXI_VERSION = "1.1.2"
MOXI_REPO    = "KerbalMissile/Moxi"

BG       = "#111111"
ACCENT   = "#FF0051"
CARD_BG  = "#1a1a1a"
NAV_BG   = "#0d0d0d"
TEXT_DIM = "#888888"
TEXT_ON  = "#ffffff"
GLOW_CLR = "#FF0051"

CARD_W = 300
CARD_H = 210
ART_W  = 300
ART_H  = 140




def _assets_dir():
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "assets")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "assets")


def _glow_on_hover(widget, targets=None, bg_normal=None, bg_hover="#222222", is_btn=False):
    targets   = targets or [widget]
    bg_normal = bg_normal or widget.cget("fg_color")

    if is_btn:
        def enter(e):
            try:
                widget.configure(border_width=2, border_color=GLOW_CLR)
            except Exception:
                pass
        def leave(e):
            try:
                widget.configure(border_width=0)
            except Exception:
                pass
    else:
        def enter(e):
            try:
                widget.configure(fg_color=bg_hover, border_width=2, border_color=GLOW_CLR)
            except Exception:
                pass
        def leave(e):
            try:
                widget.configure(fg_color=bg_normal, border_width=0)
            except Exception:
                pass

    for t in targets:
        try:
            t.bind("<Enter>", enter)
            t.bind("<Leave>", leave)
        except Exception:
            pass


class MoxiApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("")
        self.geometry("1200x750")
        self.minsize(950, 620)
        self.configure(fg_color=BG)
        self.after(50, self._apply_titlebar_color)
        self._set_window_icon()

        self._logo_img       = None
        self._art_cache      = {}
        self._detected       = []
        self._detected_inner = None
        self._active_frame   = None

        self._mod_manager    = ModManager()
        self._mod_index      = {}
        self._detected_map   = {}
        self._index_loading  = False
        self._selected_game       = GAME_NAMES[0]
        self._recently_played     = self._load_recently_played()
        self._recently_played_row = None
        self._game_index          = {}
        self._coming_soon_row     = None
        self._pending_update      = None
        self._news_cache          = None
        self._thunderstore_cache  = {}
        self._ts_loading          = set()

        self._load_logo()
        self._build_topbar()
        self._build_content_area()
        self._show_page("dashboard")

        threading.Thread(target=self._scan_steam, daemon=True).start()
        threading.Thread(target=self._do_fetch_index, daemon=True).start()
        threading.Thread(target=self._do_fetch_game_index, daemon=True).start()
        threading.Thread(target=self._check_app_update_startup, daemon=True).start()
        self.after(200, self._check_post_update)

    def _load_recently_played(self):
        path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Moxi", "recently_played.json")
        try:
            if os.path.exists(path):
                with open(path, "r") as f:
                    return json.load(f)
        except Exception:
            pass
        return []

    def _save_recently_played(self):
        path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Moxi", "recently_played.json")
        try:
            with open(path, "w") as f:
                json.dump(self._recently_played, f, indent=2)
        except Exception:
            pass

    def _record_play(self, game):
        self._recently_played = [g for g in self._recently_played if g["appid"] != game["appid"]]
        self._recently_played.insert(0, game)
        self._recently_played = self._recently_played[:5]
        self._save_recently_played()
        self._refresh_recently_played_row()

    def _refresh_recently_played_row(self):
        row = self._recently_played_row
        if row is None:
            return
        try:
            for w in row.winfo_children():
                w.destroy()
            for game in self._recently_played:
                self._make_game_card(row, game)
        except Exception:
            pass

    def _load_logo(self):
        assets = _assets_dir()
        for name in ("MoxiLogo.png", "MoxiLogo.ico", "logo.png", "logo.ico"):
            path = os.path.join(assets, name)
            if os.path.exists(path):
                try:
                    img = Image.open(path).resize((30, 30), Image.LANCZOS)
                    self._logo_img = ImageTk.PhotoImage(img)
                except Exception:
                    pass
                break

    def _set_window_icon(self):
        assets = _assets_dir()
        for name in ("MoxiLogo.ico", "logo.ico", "blank.ico"):
            path = os.path.join(assets, name)
            if os.path.exists(path):
                try:
                    self.iconbitmap(path)
                except Exception:
                    pass
                return

    def _apply_titlebar_color(self):
        try:
            from ctypes import windll, byref, c_int, sizeof
            DWMWA_CAPTION_COLOR = 35
            hwnd  = windll.user32.GetParent(self.winfo_id())
            color = c_int(0x00111111)
            windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR, byref(color), sizeof(color))
        except Exception:
            pass

    def _check_app_update_startup(self):
        try:
            tag, changelog, dl_url = self._mod_manager.check_for_app_update()
            from packaging.version import Version
            if Version(tag) > Version(MOXI_VERSION):
                self._pending_update = {"version": tag, "changelog": changelog, "dl_url": dl_url}
                self.after(0, self._show_update_banner)
        except Exception:
            pass

    def _show_update_banner(self):
        if not hasattr(self, "_update_banner_shown"):
            self._update_banner_shown = False
        if self._update_banner_shown or not self._pending_update:
            return
        self._update_banner_shown = True
        u = self._pending_update

        banner = ctk.CTkFrame(self, fg_color="#0a1a0a", height=38, corner_radius=0)
        banner.pack(side="top", fill="x", before=self._content)
        banner.pack_propagate(False)

        ctk.CTkLabel(
            banner,
            text=f"Moxi v{u['version']} is available.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#44cc88", anchor="w"
        ).pack(side="left", padx=14)

        def start_update():
            banner.destroy()
            self._show_page("settings")
            self.after(100, self._trigger_settings_update)

        ctk.CTkButton(
            banner, text="Update Now",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color="#1a4a1a", hover_color="#226622",
            text_color="#44cc88", corner_radius=4,
            border_width=0, width=90, height=26,
            command=start_update
        ).pack(side="right", padx=(0, 10))

        def dismiss():
            banner.destroy()

        ctk.CTkButton(
            banner, text="Dismiss",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color="transparent", hover_color="#1a2a1a",
            text_color="#666666", corner_radius=4,
            border_width=0, width=70, height=26,
            command=dismiss
        ).pack(side="right", padx=(0, 4))

    def _trigger_settings_update(self):
        pass

    def _do_download_update(self, version, changelog, dl_url, progress_bar, btn, status):
        import webbrowser
        webbrowser.open(f"https://github.com/{MOXI_REPO}/releases/latest")

    def _check_post_update(self):
        data = self._mod_manager.read_and_clear_updated_flag()
        if data:
            self._show_changelog_overlay(data["version"], data["changelog"])

    def _show_changelog_overlay(self, version, changelog):
        overlay = ctk.CTkFrame(self, fg_color="#000000", corner_radius=0)
        overlay.place(x=0, y=0, relwidth=1, relheight=1)
        overlay.configure(fg_color="#000000")
        overlay.tkraise()

        try:
            overlay.configure(fg_color="#11111188")
        except Exception:
            pass

        card = ctk.CTkFrame(overlay, fg_color="#1a1a1a", corner_radius=12, width=540, height=420)
        card.place(relx=0.5, rely=0.5, anchor="center")
        card.pack_propagate(False)

        ctk.CTkLabel(
            card,
            text=f"Updated to v{version}",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=ACCENT
        ).pack(pady=(28, 4))

        ctk.CTkLabel(
            card,
            text="Here's what's new:",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_DIM
        ).pack(pady=(0, 10))

        log_box = ctk.CTkScrollableFrame(card, fg_color="#111111", corner_radius=8, height=240)
        log_box.pack(fill="x", padx=24)

        ctk.CTkLabel(
            log_box,
            text=changelog if changelog else "No changelog provided.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_ON,
            wraplength=460, justify="left", anchor="w"
        ).pack(anchor="w", padx=10, pady=10)

        ctk.CTkButton(
            card, text="Let's go",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            fg_color=ACCENT, hover_color="#cc0040",
            text_color="#ffffff", corner_radius=8,
            width=140, height=36,
            command=overlay.destroy
        ).pack(pady=(18, 0))

    def _build_topbar(self):
        bar = ctk.CTkFrame(self, fg_color=NAV_BG, height=52, corner_radius=0)
        bar.pack(side="top", fill="x")
        bar.pack_propagate(False)

        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.pack(side="left", padx=(16, 0))

        if self._logo_img:
            tk.Label(
                left, image=self._logo_img,
                bg=NAV_BG, bd=0, highlightthickness=0
            ).pack(side="left", pady=11)

        ctk.CTkLabel(
            left, text="Moxi",
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
            text_color=ACCENT
        ).pack(side="left", padx=(8, 0))

        nav_frame = ctk.CTkFrame(bar, fg_color="transparent")
        nav_frame.pack(side="right", padx=18)

        self._nav_buttons = {}
        for label, key in [("Dashboard", "dashboard"), ("Mod Database", "mod_database"), ("Settings", "settings")]:
            btn = ctk.CTkButton(
                nav_frame, text=label,
                font=ctk.CTkFont(family="Segoe UI", size=13),
                fg_color="transparent",
                text_color=TEXT_DIM,
                hover_color="#1a1a1a",
                corner_radius=6,
                border_width=0,
                width=115, height=34,
                command=lambda k=key: self._show_page(k)
            )
            btn.pack(side="left", padx=3)
            self._nav_buttons[key] = btn
            _glow_on_hover(btn, targets=[btn], is_btn=True)

    def _build_content_area(self):
        self._content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self._content.pack(fill="both", expand=True)
        self._build_footer()

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color=NAV_BG, height=36, corner_radius=0)
        footer.pack(side="bottom", fill="x")
        footer.pack_propagate(False)

        icon_frame = ctk.CTkFrame(footer, fg_color="transparent")
        icon_frame.pack(side="right", padx=14)

        links = [
            ("website",  "https://kerbalmissile.github.io/MoxiWebsite/"),
            ("github",   "https://github.com/KerbalMissile/Moxi"),
            ("discord",  "https://discord.com/invite/Y53vwvQRDc"),
        ]

        for kind, url in links:
            self._make_icon_btn(icon_frame, kind, url)

    def _make_icon_btn(self, parent, kind, url):
        import webbrowser

        labels = {"website": "Website", "github": "GitHub", "discord": "Discord"}

        lbl = tk.Label(
            parent,
            text=labels[kind],
            fg="#555555", bg=NAV_BG,
            font=("Segoe UI", 9),
            bd=0, highlightthickness=0,
            cursor="hand2"
        )
        lbl.pack(side="left", padx=8, pady=10)

        lbl.bind("<Enter>",    lambda e: lbl.configure(fg=ACCENT))
        lbl.bind("<Leave>",    lambda e: lbl.configure(fg="#555555"))
        lbl.bind("<Button-1>", lambda e: webbrowser.open(url))

    def _show_page(self, key):
        if self._active_frame:
            self._active_frame.destroy()
            self._active_frame   = None
            self._detected_inner = None

        for k, btn in self._nav_buttons.items():
            btn.configure(text_color=ACCENT if k == key else TEXT_DIM)

        frame = ctk.CTkFrame(self._content, fg_color=BG, corner_radius=0)
        frame.pack(fill="both", expand=True)
        self._active_frame = frame

        {
            "dashboard":    self._build_dashboard,
            "mod_database": self._build_mod_database,
            "settings":     self._build_settings,
        }[key](frame)

    def _do_fetch_index(self, on_done=None):
        if self._index_loading:
            return
        self._index_loading = True
        try:
            self._mod_index = self._mod_manager.fetch_mod_index()
        except Exception:
            self._mod_index = {}
        finally:
            self._index_loading = False
        if on_done:
            try:
                on_done()
            except Exception:
                pass

    def _do_fetch_game_index(self):
        try:
            self._game_index = self._mod_manager.fetch_game_index()
        except Exception:
            self._game_index = {}
        if self._active_frame:
            self._active_frame.after(0, self._refresh_coming_soon)

    def _refresh_coming_soon(self):
        if hasattr(self, "_coming_soon_row") and self._coming_soon_row is not None:
            try:
                for w in self._coming_soon_row.winfo_children():
                    w.destroy()
                coming = self._get_coming_soon_games()
                if coming:
                    for g in coming:
                        self._make_game_card(self._coming_soon_row, g)
                else:
                    import customtkinter as ctk
                    ctk.CTkLabel(
                        self._coming_soon_row, text="Nothing here yet.",
                        font=ctk.CTkFont(family="Segoe UI", size=12),
                        text_color=TEXT_DIM
                    ).pack(side="left", padx=16, pady=30)
            except Exception:
                pass

    def _get_coming_soon_games(self):
        coming = []
        for entry in self._game_index.get("coming_soon", []):
            coming.append({
                "appid":       entry.get("appid", "0"),
                "name":        entry.get("name", "Unknown"),
                "supported":   False,
                "game_key":    entry.get("game_key", ""),
                "coming_date": entry.get("coming_date", ""),
            })
        return coming

    def _build_dashboard(self, parent):
        body = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        body.pack(fill="both", expand=True)

        sidebar = ctk.CTkFrame(body, fg_color=NAV_BG, corner_radius=0, width=220)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        self._build_sidebar(sidebar)

        divider = ctk.CTkFrame(body, fg_color="#1e1e1e", corner_radius=0, width=1)
        divider.pack(side="left", fill="y")

        scroll = ctk.CTkScrollableFrame(body, fg_color=BG, corner_radius=0)
        scroll.pack(side="left", fill="both", expand=True)

        self._recently_played_row = self._build_section(scroll, "Recently Played", self._recently_played if self._recently_played else [])

        newly = [
            {"appid": appid, "name": v["name"], "supported": v["supported"], "game_key": v["game_key"]}
            for appid, v in SUPPORTED_GAMES.items()
        ]
        self._build_section(scroll, "Newly Added to Moxi", newly)

        coming = self._get_coming_soon_games()
        self._coming_soon_row = self._build_section(scroll, "Coming Soon", coming)

        self._detected_inner = self._build_section(scroll, "Detected Supported Games", None)
        self._populate_detected_cards()

    def _build_sidebar(self, parent):
        def section_label(text):
            ctk.CTkLabel(
                parent, text=text.upper(),
                font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                text_color="#444444", anchor="w"
            ).pack(anchor="w", padx=16, pady=(16, 4))

        def divider():
            ctk.CTkFrame(parent, fg_color="#1e1e1e", height=1, corner_radius=0).pack(fill="x", padx=12, pady=(0, 8))

        section_label("Stats")
        divider()

        total_installed = sum(
            len(v) for v in self._mod_manager.installed.values()
        )

        stat_rows = {}
        for label in ("Mods Installed", "Games Detected"):
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=2)
            ctk.CTkLabel(
                row, text=label,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=TEXT_DIM, anchor="w"
            ).pack(side="left")
            val_lbl = ctk.CTkLabel(
                row, text="...",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=TEXT_ON, anchor="e"
            )
            val_lbl.pack(side="right")
            stat_rows[label] = val_lbl

        def _update_stats():
            try:
                stat_rows["Mods Installed"].configure(
                    text=str(sum(len(v) for v in self._mod_manager.installed.values()))
                )
                stat_rows["Games Detected"].configure(
                    text=str(len(self._detected))
                )
            except Exception:
                pass

        _update_stats()
        self._sidebar_update_stats = _update_stats

        if self._mod_manager.installed:
            section_label("Mods Per Game")
            divider()
            for game_key, mods in self._mod_manager.installed.items():
                if not mods:
                    continue
                game_name = GAME_KEY_TO_NAME.get(game_key, game_key.replace("_", " ").title())
                row = ctk.CTkFrame(parent, fg_color="transparent")
                row.pack(fill="x", padx=16, pady=2)
                ctk.CTkLabel(
                    row, text=game_name,
                    font=ctk.CTkFont(family="Segoe UI", size=11),
                    text_color=TEXT_DIM, anchor="w",
                    wraplength=140
                ).pack(side="left")
                ctk.CTkLabel(
                    row, text=str(len(mods)),
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    text_color=ACCENT, anchor="e"
                ).pack(side="right")

        section_label("News")
        divider()

        news_frame = ctk.CTkScrollableFrame(parent, fg_color="transparent", corner_radius=0)
        news_frame.pack(fill="both", expand=True, padx=0)

        loading_lbl = ctk.CTkLabel(
            news_frame, text="Loading...",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#444444"
        )
        loading_lbl.pack(pady=12)

        def _load_news():
            if self._news_cache is not None:
                _render_news(self._news_cache)
                return
            try:
                r = requests.get(
                    f"https://api.github.com/repos/{MOXI_REPO}/releases",
                    timeout=8
                )
                r.raise_for_status()
                self._news_cache = r.json()
                news_frame.after(0, lambda: _render_news(self._news_cache))
            except Exception:
                news_frame.after(0, lambda: loading_lbl.configure(text="Failed to load news."))

        def _render_news(releases):
            try:
                loading_lbl.destroy()
            except Exception:
                pass
            for release in releases[:5]:
                tag  = release.get("tag_name", "")
                body = release.get("body", "No changelog provided.") or "No changelog provided."
                card = ctk.CTkFrame(news_frame, fg_color="#141414", corner_radius=6)
                card.pack(fill="x", padx=10, pady=(0, 8))
                ctk.CTkLabel(
                    card, text=f"Moxi {tag}",
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    text_color=ACCENT, anchor="w"
                ).pack(anchor="w", padx=10, pady=(8, 2))
                ctk.CTkLabel(
                    card, text=body,
                    font=ctk.CTkFont(family="Segoe UI", size=10),
                    text_color=TEXT_DIM, anchor="w",
                    wraplength=170, justify="left"
                ).pack(anchor="w", padx=10, pady=(0, 8))

        threading.Thread(target=_load_news, daemon=True).start()

    def _build_section(self, parent, title, games):
        wrapper = ctk.CTkFrame(parent, fg_color=BG, corner_radius=0)
        wrapper.pack(fill="x", pady=(28, 0), padx=28)

        ctk.CTkLabel(
            wrapper, text=title,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=TEXT_ON, anchor="w"
        ).pack(anchor="w", pady=(0, 8))

        ctk.CTkFrame(wrapper, fg_color="#252525", height=1, corner_radius=0).pack(fill="x", pady=(0, 14))

        row = ctk.CTkScrollableFrame(
            wrapper, fg_color=BG, corner_radius=0,
            orientation="horizontal", height=CARD_H + 16
        )
        row.pack(fill="x")

        if games is not None:
            if games:
                for g in games:
                    self._make_game_card(row, g)
            else:
                ctk.CTkLabel(
                    row, text="Nothing here yet.",
                    font=ctk.CTkFont(family="Segoe UI", size=12),
                    text_color=TEXT_DIM
                ).pack(side="left", padx=16, pady=30)

        return row

    def _populate_detected_cards(self):
        if self._detected_inner is None:
            return
        for w in self._detected_inner.winfo_children():
            w.destroy()
        if not self._detected:
            ctk.CTkLabel(
                self._detected_inner,
                text="Scanning for games...",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_DIM
            ).pack(side="left", padx=16, pady=30)
        else:
            self._render_detected_cards()

    def _render_detected_cards(self):
        if self._detected_inner is None:
            return
        for w in self._detected_inner.winfo_children():
            w.destroy()
        if not self._detected:
            ctk.CTkLabel(
                self._detected_inner,
                text="No supported games found on this machine.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_DIM
            ).pack(side="left", padx=16, pady=30)
            return
        for game in self._detected:
            self._make_game_card(self._detected_inner, game)

    def _make_game_card(self, parent, game):
        import webbrowser
        appid     = game["appid"]
        name      = game["name"]
        game_key  = game.get("game_key", "")
        live_info = SUPPORTED_GAMES.get(appid, {})
        supported = live_info.get("supported", game.get("supported", False))

        card = ctk.CTkFrame(
            parent, fg_color=CARD_BG, corner_radius=10,
            width=CARD_W, height=CARD_H, border_width=0
        )
        card.pack(side="left", padx=(0, 14), pady=4)
        card.pack_propagate(False)

        art_frame = ctk.CTkFrame(card, fg_color="#1e1e1e", corner_radius=8, width=ART_W, height=ART_H)
        art_frame.pack()
        art_frame.pack_propagate(False)

        art_label = ctk.CTkLabel(
            art_frame, text="Loading...",
            text_color=TEXT_DIM,
            font=ctk.CTkFont(family="Segoe UI", size=11)
        )
        art_label.place(relx=0.5, rely=0.5, anchor="center")

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(fill="x", padx=10, pady=(6, 6))

        name_row = ctk.CTkFrame(info, fg_color="transparent")
        name_row.pack(fill="x")

        ctk.CTkLabel(
            name_row, text=name,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=TEXT_ON, wraplength=260, anchor="w", justify="left"
        ).pack(side="left", anchor="w")

        bottom = ctk.CTkFrame(info, fg_color="transparent")
        bottom.pack(fill="x", pady=(4, 0))

        game_info   = SUPPORTED_GAMES.get(appid, {})
        coming_date = game.get("coming_date") or game_info.get("coming_date")

        if supported:
            badge_text  = "Supported"
            badge_color = ACCENT
        elif coming_date:
            badge_text  = f"Coming {coming_date}"
            badge_color = "#666666"
        else:
            badge_text  = "Coming Soon"
            badge_color = "#444444"

        ctk.CTkLabel(
            bottom,
            text=badge_text,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=badge_color, anchor="w"
        ).pack(side="left", anchor="center")

        play_btn = ctk.CTkButton(
            bottom, text="Play",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color="#2a2a2a",
            hover_color="#333333",
            text_color=TEXT_ON,
            corner_radius=4,
            border_width=0,
            width=48, height=24,
            command=lambda: self._launch_game(game)
        )
        play_btn.pack(side="right", anchor="center")
        _glow_on_hover(play_btn, targets=[play_btn], is_btn=True)

        def on_card_click(e):
            self._selected_game = name
            self._show_page("mod_database")

        art_frame.bind("<Button-1>", on_card_click)
        art_label.bind("<Button-1>", on_card_click)

        _glow_on_hover(card, targets=[card, art_frame, art_label, info, bottom], bg_normal=CARD_BG, bg_hover="#222222")
        threading.Thread(target=self._load_art, args=(appid, art_label), daemon=True).start()

    def _launch_game(self, game):
        import webbrowser
        game_key = game.get("game_key", "")
        if game_key not in self._detected_map:
            return
        webbrowser.open(f"steam://rungameid/{game['appid']}")
        self._record_play(game)

    def _all_descendants(self, widget):
        result = []
        try:
            for child in widget.winfo_children():
                result.append(child)
                result.extend(self._all_descendants(child))
        except Exception:
            pass
        return result

    def _load_art(self, appid, label):
        img = self._art_cache.get(appid)
        if img is None:
            img = self._fetch_cdn_art(appid)
        if img is None:
            def _set_no_icon(lbl=label):
                try:
                    lbl.configure(text="No Icon Found", text_color=TEXT_DIM)
                except Exception:
                    pass
            label.after(0, _set_no_icon)
            return
        self._art_cache[appid] = img
        photo = ImageTk.PhotoImage(img)
        def apply():
            try:
                label.configure(image=photo, text="")
                label.image = photo
            except Exception:
                pass
        try:
            label.after(0, apply)
        except Exception:
            pass

    def _fetch_cdn_art(self, appid):
        url = CUSTOM_ART_URLS.get(str(appid)) or f"https://steamcdn-a.akamaihd.net/steam/apps/{appid}/header.jpg"
        try:
            r = requests.get(url, timeout=6)
            if r.status_code == 200:
                img = Image.open(io.BytesIO(r.content))
                return img.resize((ART_W, ART_H), Image.LANCZOS)
        except Exception:
            pass
        return None

    def _scan_steam(self):
        scanner            = SteamScanner(SUPPORTED_GAMES)
        results            = scanner.scan()
        self._detected     = results
        self._detected_map = {g["game_key"]: g for g in results}
        if self._active_frame:
            self._active_frame.after(0, self._render_detected_cards)
            if hasattr(self, "_sidebar_update_stats"):
                self._active_frame.after(0, self._sidebar_update_stats)

    def _build_mod_database(self, parent):
        PAGE_SIZE = 20
        state     = {"page": 0, "all_mods": [], "game_key": "", "search_after": None, "suppress_search": False}

        toolbar = ctk.CTkFrame(parent, fg_color=NAV_BG, height=54, corner_radius=0)
        toolbar.pack(fill="x")
        toolbar.pack_propagate(False)

        ctk.CTkLabel(
            toolbar, text="Game:",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color=TEXT_DIM
        ).pack(side="left", padx=(20, 6), pady=14)

        game_var = ctk.StringVar(value=self._selected_game)

        ctk.CTkOptionMenu(
            toolbar,
            variable=game_var,
            values=GAME_NAMES,
            fg_color="#1e1e1e",
            button_color="#2a2a2a",
            button_hover_color="#333333",
            dropdown_fg_color="#1a1a1a",
            dropdown_hover_color="#252525",
            text_color=TEXT_ON,
            font=ctk.CTkFont(family="Segoe UI", size=13),
            width=220,
            command=lambda val: _reload(val)
        ).pack(side="left", pady=14)

        status_lbl = ctk.CTkLabel(
            toolbar, text="",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_DIM
        )
        status_lbl.pack(side="left", padx=16)

        refresh_btn = ctk.CTkButton(
            toolbar, text="Refresh",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#1e1e1e", hover_color="#2a2a2a",
            text_color=TEXT_DIM, corner_radius=6,
            border_width=0, width=80, height=30,
            command=lambda: _do_refresh()
        )
        refresh_btn.pack(side="right", padx=(0, 16), pady=12)
        _glow_on_hover(refresh_btn, targets=[refresh_btn], is_btn=True)

        search_var = ctk.StringVar()
        search_entry = ctk.CTkEntry(
            toolbar, textvariable=search_var,
            placeholder_text="Search mods...",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            fg_color="#1e1e1e", border_color="#2a2a2a",
            text_color=TEXT_ON, width=200, height=30
        )
        search_entry.pack(side="left", padx=(12, 0), pady=12)

        ctk.CTkFrame(parent, fg_color="#1e1e1e", height=1, corner_radius=0).pack(fill="x")

        notif_bar = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0, height=0)
        notif_bar.pack(fill="x")
        notif_bar.pack_propagate(False)

        list_container = ctk.CTkScrollableFrame(parent, fg_color=BG, corner_radius=0)
        list_container.pack(fill="both", expand=True)

        pager = ctk.CTkFrame(parent, fg_color=NAV_BG, height=40, corner_radius=0)
        pager.pack(fill="x", side="bottom")
        pager.pack_propagate(False)

        prev_btn = ctk.CTkButton(
            pager, text="< Prev",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="transparent", hover_color="#1e1e1e",
            text_color=TEXT_DIM, corner_radius=4,
            border_width=0, width=70, height=28,
            command=lambda: _go_page(state["page"] - 1)
        )
        prev_btn.pack(side="left", padx=12, pady=6)
        _glow_on_hover(prev_btn, targets=[prev_btn], is_btn=True)

        page_lbl = ctk.CTkLabel(
            pager, text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_DIM
        )
        page_lbl.pack(side="left", padx=8)

        next_btn = ctk.CTkButton(
            pager, text="Next >",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="transparent", hover_color="#1e1e1e",
            text_color=TEXT_DIM, corner_radius=4,
            border_width=0, width=70, height=28,
            command=lambda: _go_page(state["page"] + 1)
        )
        next_btn.pack(side="left", padx=0, pady=6)
        _glow_on_hover(next_btn, targets=[next_btn], is_btn=True)

        def _clear_list():
            for w in list_container.winfo_children():
                w.destroy()

        def _show_message(text):
            _clear_list()
            ctk.CTkLabel(
                list_container, text=text,
                font=ctk.CTkFont(family="Segoe UI", size=14),
                text_color=TEXT_DIM
            ).pack(pady=60)

        def _render_page(mods_slice, game_key):
            _clear_list()
            list_container.update_idletasks()

            def _batch(items, start=0):
                if not list_container.winfo_exists():
                    return
                for mod in items[start:start + 10]:
                    installed = self._mod_manager.is_installed(game_key, mod["id"])
                    self._make_mod_row(list_container, mod, game_key, installed, notif_bar,
                                       on_install_done=lambda gn=game_var.get(): _reload(gn))
                if start + 10 < len(items):
                    list_container.after(40, lambda s=start+10: _batch(items, s))

            list_container.after(80, lambda: _batch(mods_slice))

        def _go_page(page):
            all_mods  = state["all_mods"]
            game_key  = state["game_key"]
            total     = len(all_mods)
            max_page  = max(0, (total - 1) // PAGE_SIZE)
            page      = max(0, min(page, max_page))
            state["page"] = page

            start  = page * PAGE_SIZE
            end    = start + PAGE_SIZE
            sliced = all_mods[start:end]

            status_lbl.configure(text=f"{total} mod{'s' if total != 1 else ''}")
            page_lbl.configure(text=f"Page {page + 1} of {max_page + 1}")
            prev_btn.configure(state="normal" if page > 0 else "disabled",
                               text_color=TEXT_DIM if page > 0 else "#333333")
            next_btn.configure(state="normal" if page < max_page else "disabled",
                               text_color=TEXT_DIM if page < max_page else "#333333")

            _render_page(sliced, game_key)

        def _do_search(*_):
            if state["suppress_search"]:
                return
            if state["search_after"] is not None:
                try:
                    list_container.after_cancel(state["search_after"])
                except Exception:
                    pass
            state["search_after"] = list_container.after(300, _apply_search)

        def _mod_keywords(mod):
            words = set()
            name = mod.get("name", "")
            for w in name.lower().split():
                words.add(w.strip(".,!?-"))
            mod_id = mod.get("id", "")
            for part in mod_id.lower().replace("-", "_").split("_"):
                if part:
                    words.add(part)
            for tag in mod.get("tags", []):
                words.add(tag.lower())
            return words

        def _apply_search():
            state["search_after"] = None
            query    = search_var.get().strip().lower()
            game_key = state["game_key"]

            if not query:
                pager.pack(fill="x", side="bottom")
                _go_page(0)
                return

            terms    = query.split()
            all_mods = state["all_mods"]
            results  = []

            for m in all_mods:
                keywords = _mod_keywords(m)
                blob     = " ".join([
                    m.get("name", ""),
                    m.get("author", ""),
                    m.get("description", ""),
                    m.get("id", "").replace("_", " ").replace("-", " "),
                ]).lower()
                if all(
                    any(t in kw for kw in keywords) or t in blob
                    for t in terms
                ):
                    results.append(m)

            pager.pack_forget()
            status_lbl.configure(text=f"{len(results)} result{'s' if len(results) != 1 else ''}")
            page_lbl.configure(text="")

            if not results:
                _show_message("No mods found.")
                return

            _render_page(results, game_key)

        def _load_mods(game_name):
            game_info = next((v for v in SUPPORTED_GAMES.values() if v["name"] == game_name), {})
            game_key  = game_info.get("game_key", "")
            supported = game_info.get("supported", False)

            state["page"]     = 0
            state["game_key"] = game_key
            state["all_mods"] = []
            state["suppress_search"] = True
            search_var.set("")
            state["suppress_search"] = False
            pager.pack(fill="x", side="bottom")
            _clear_list()

            if not supported:
                status_lbl.configure(text="")
                _show_message(f"{game_name} is not yet supported.")
                return

            if not self._mod_index:
                status_lbl.configure(text="Failed to load index.")
                _show_message("Could not load mod index. Press Refresh to try again.")
                return

            curated_raw = self._mod_index.get("games", {}).get(game_key, {}).get("mods", [])
            curated     = [{**m, "source": "curated"} for m in curated_raw]
            curated_ids = {m["id"] for m in curated}

            if game_key in THUNDERSTORE_GAMES:
                ts_cached = self._thunderstore_cache.get(game_key)
                if ts_cached is None:
                    if game_key not in self._ts_loading:
                        self._ts_loading.add(game_key)
                        status_lbl.configure(text="Loading Thunderstore...")
                        _show_message("Fetching mods from Thunderstore...")
                        def _fetch(gk=game_key, gn=game_name):
                            try:
                                pkgs = self._mod_manager.fetch_thunderstore_packages(gk)
                                self._thunderstore_cache[gk] = pkgs
                            except Exception:
                                self._thunderstore_cache[gk] = []
                            self._ts_loading.discard(gk)
                            if self._active_frame and state["game_key"] == gk:
                                self._active_frame.after(0, lambda: _load_mods(gn))
                        threading.Thread(target=_fetch, daemon=True).start()
                    return
                ts_only = [m for m in ts_cached if m["id"] not in curated_ids]
                all_mods = curated + ts_only
            else:
                all_mods = curated

            state["all_mods"] = all_mods

            if not all_mods:
                status_lbl.configure(text="0 mods")
                _show_message("No mods available yet for this game.")
                return

            _go_page(0)

        def _reload(game_name, force=False):
            if self._index_loading:
                status_lbl.configure(text="Loading...")
                self.after(400, lambda: _reload(game_name))
                return
            if (not force
                    and state["game_key"] == next((v["game_key"] for v in SUPPORTED_GAMES.values() if v["name"] == game_name), "")
                    and state["all_mods"]):
                return
            _load_mods(game_name)

        def _do_refresh():
            if self._index_loading:
                return
            refresh_btn.configure(text="Refreshing...", state="disabled")
            status_lbl.configure(text="")
            game_key_now = next((v["game_key"] for v in SUPPORTED_GAMES.values()
                                 if v["name"] == game_var.get()), "")
            if game_key_now in self._thunderstore_cache:
                del self._thunderstore_cache[game_key_now]
            state["all_mods"] = []

            def on_done():
                current_game = game_var.get()
                refresh_btn.after(0, lambda: refresh_btn.configure(text="Refresh", state="normal"))
                refresh_btn.after(0, lambda: _load_mods(current_game))

            threading.Thread(target=self._do_fetch_index, args=(on_done,), daemon=True).start()

        search_var.trace_add("write", _do_search)
        _reload(self._selected_game)

    def _make_mod_row(self, parent, mod, game_key, installed, notif_bar=None, on_install_done=None):
        row = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=8, height=80, border_width=0)
        row.pack(fill="x", padx=20, pady=(0, 6))
        row.pack_propagate(False)

        left = ctk.CTkFrame(row, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(16, 8), pady=10)

        top_line = ctk.CTkFrame(left, fg_color="transparent")
        top_line.pack(fill="x")

        ctk.CTkLabel(
            top_line, text=mod["name"],
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=TEXT_ON, anchor="w"
        ).pack(side="left")

        ctk.CTkLabel(
            top_line, text=f"v{mod['version']}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_DIM, anchor="w"
        ).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(
            top_line, text=f"by {mod['author']}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#666666", anchor="w"
        ).pack(side="left", padx=(10, 0))

        source = mod.get("source", "curated")
        if source == "thunderstore":
            ctk.CTkLabel(
                top_line, text="Thunderstore",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color="#4a9eff", anchor="w"
            ).pack(side="left", padx=(10, 0))
        elif source == "curated":
            ctk.CTkLabel(
                top_line, text="Curated",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=ACCENT, anchor="w"
            ).pack(side="left", padx=(10, 0))

        ctk.CTkLabel(
            left, text=mod.get("description", ""),
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_DIM, anchor="w", wraplength=700, justify="left"
        ).pack(anchor="w", pady=(3, 0))

        right = ctk.CTkFrame(row, fg_color="transparent", width=140)
        right.pack(side="right", padx=16, pady=10)
        right.pack_propagate(False)

        status_lbl = ctk.CTkLabel(
            right,
            text="Installed" if installed else "Not Installed",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#44cc88" if installed else TEXT_DIM
        )
        status_lbl.pack(anchor="e", pady=(0, 4))

        progress_bar = ctk.CTkProgressBar(right, width=120, height=8, fg_color="#2a2a2a", progress_color=ACCENT)

        btn_row = ctk.CTkFrame(right, fg_color="transparent")
        btn_row.pack(anchor="e")

        mod_enabled = [self._mod_manager.installed.get(game_key, {}).get(mod["id"], {}).get("enabled", True)]

        toggle_canvas = tk.Canvas(btn_row, width=44, height=22, bg=CARD_BG, bd=0, highlightthickness=0)
        toggle_canvas.pack(side="left", padx=(0, 8))

        def _draw_toggle(enabled, animating=False):
            toggle_canvas.delete("all")
            bg_color = "#44cc88" if enabled else "#cc4444"
            toggle_canvas.create_rounded_rect = None
            x0, y0, x1, y1 = 0, 2, 44, 20
            r = 9
            toggle_canvas.create_arc(x0, y0, x0+r*2, y1, start=90,  extent=180, fill=bg_color, outline=bg_color)
            toggle_canvas.create_arc(x1-r*2, y0, x1, y1, start=270, extent=180, fill=bg_color, outline=bg_color)
            toggle_canvas.create_rectangle(x0+r, y0, x1-r, y1, fill=bg_color, outline=bg_color)
            cx = 32 if enabled else 12
            toggle_canvas.create_oval(cx-8, 3, cx+8, 19, fill="white", outline="white")

        _draw_toggle(mod_enabled[0])

        def _animate_toggle(enabled, step=0, steps=6):
            if step > steps:
                mod_enabled[0] = enabled
                _draw_toggle(enabled)
                return
            progress = step / steps
            cx = int(12 + (32 - 12) * progress) if enabled else int(32 - (32 - 12) * progress)
            toggle_canvas.delete("all")
            bg_color = "#44cc88" if enabled else "#cc4444"
            x0, y0, x1, y1 = 0, 2, 44, 20
            r = 9
            toggle_canvas.create_arc(x0, y0, x0+r*2, y1, start=90,  extent=180, fill=bg_color, outline=bg_color)
            toggle_canvas.create_arc(x1-r*2, y0, x1, y1, start=270, extent=180, fill=bg_color, outline=bg_color)
            toggle_canvas.create_rectangle(x0+r, y0, x1-r, y1, fill=bg_color, outline=bg_color)
            toggle_canvas.create_oval(cx-8, 3, cx+8, 19, fill="white", outline="white")
            toggle_canvas.after(16, lambda: _animate_toggle(enabled, step+1, steps))

        def _on_toggle(e=None):
            if not self._mod_manager.is_installed(game_key, mod["id"]):
                return
            new_state = not mod_enabled[0]
            _animate_toggle(new_state)
            if new_state:
                threading.Thread(target=lambda: self._mod_manager.enable_mod(game_key, mod["id"]), daemon=True).start()
            else:
                threading.Thread(target=lambda: self._mod_manager.disable_mod(game_key, mod["id"]), daemon=True).start()

        if installed:
            toggle_canvas.configure(cursor="hand2")
            toggle_canvas.bind("<Button-1>", _on_toggle)
        else:
            toggle_canvas.pack_forget()

        action_btn = ctk.CTkButton(
            btn_row,
            text="Remove" if installed else "Install",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color="#2a2a2a" if installed else ACCENT,
            hover_color="#3a1a1a" if installed else "#cc0040",
            text_color="#cc4444" if installed else "#ffffff",
            corner_radius=6,
            border_width=0,
            width=120, height=28
        )
        action_btn.pack(side="left")
        _glow_on_hover(action_btn, targets=[action_btn], is_btn=True)

        def do_install(bepinex_progress_offset=0.0):
            game_data   = self._detected_map.get(game_key)
            install_dir = game_data["install_dir"] if game_data else None

            if not install_dir or not os.path.isdir(install_dir):
                action_btn.after(0, lambda: status_lbl.configure(text="Game path not found", text_color="#cc4444"))
                action_btn.after(0, lambda: action_btn.configure(state="normal", text="Install"))
                return

            remaining = 1.0 - bepinex_progress_offset

            def progress_cb(val):
                try:
                    progress_bar.set(bepinex_progress_offset + val * remaining)
                except Exception:
                    pass

            try:
                self._mod_manager.install_mod(game_key, mod, install_dir, progress_cb)
                action_btn.after(0, action_btn.pack_forget)
                progress_bar.after(0, progress_bar.pack_forget)
                status_lbl.after(0, lambda: status_lbl.configure(text="Installed", text_color="#44cc88"))
                def set_remove():
                    if on_install_done:
                        on_install_done()
                    else:
                        action_btn.configure(
                            text="Remove", fg_color="#2a2a2a",
                            hover_color="#3a1a1a", text_color="#cc4444",
                            command=do_remove, state="normal"
                        )
                        action_btn.pack(side="left")
                        toggle_canvas.pack(side="left", padx=(0, 8))
                        toggle_canvas.configure(cursor="hand2")
                        toggle_canvas.bind("<Button-1>", _on_toggle)
                        _draw_toggle(True)
                action_btn.after(0, set_remove)
            except Exception:
                progress_bar.after(0, progress_bar.pack_forget)
                status_lbl.after(0, lambda: status_lbl.configure(text="Install failed", text_color="#cc4444"))
                def set_retry():
                    action_btn.configure(state="normal", text="Retry")
                    action_btn.pack(anchor="e")
                action_btn.after(0, set_retry)

        def do_remove():
            try:
                self._mod_manager.uninstall_mod(game_key, mod["id"])
                status_lbl.configure(text="Not Installed", text_color=TEXT_DIM)
                action_btn.configure(
                    text="Install", fg_color=ACCENT,
                    hover_color="#cc0040", text_color="#ffffff",
                    command=start_install, state="normal"
                )
                try:
                    toggle_canvas.pack_forget()
                except Exception:
                    pass
            except Exception:
                status_lbl.configure(text="Remove failed", text_color="#cc4444")

        def _dismiss_notif():
            if notif_bar is None:
                return
            for w in notif_bar.winfo_children():
                w.destroy()
            notif_bar.configure(height=0)
            notif_bar.pack_propagate(False)

        def _show_bepinex_notif():
            if notif_bar is None:
                return
            _dismiss_notif()
            notif_bar.configure(height=40)
            notif_bar.pack_propagate(False)
            bar = ctk.CTkFrame(notif_bar, fg_color="#1e0a0a", corner_radius=0)
            bar.pack(fill="both", expand=True)
            ctk.CTkLabel(
                bar,
                text="Mod loader not installed — required to run mods. Would you like Moxi to install it?",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#cc4444", anchor="w"
            ).pack(side="left", padx=14)
            ctk.CTkButton(
                bar, text="No thanks",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                fg_color="transparent", hover_color="#2a1010",
                text_color="#666666", corner_radius=4,
                border_width=0, width=80, height=26,
                command=_dismiss_notif
            ).pack(side="right", padx=(0, 6))
            ctk.CTkButton(
                bar, text="Install Mod Loader",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                fg_color=ACCENT, hover_color="#cc0040",
                text_color="#ffffff", corner_radius=4,
                border_width=0, width=110, height=26,
                command=lambda: [_dismiss_notif(), start_install(install_bepinex_first=True)]
            ).pack(side="right", padx=(0, 4))

        def _show_dep_notif(deps):
            _dismiss_notif()
            notif_bar.configure(height=40)
            notif_bar.pack_propagate(False)
            bar = ctk.CTkFrame(notif_bar, fg_color="#0a1a0a", corner_radius=0)
            bar.pack(fill="both", expand=True)
            names = ", ".join(d["name"] for d in deps)
            ctk.CTkLabel(
                bar,
                text=f"Requires: {names}. Install all?",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color="#44cc88", anchor="w"
            ).pack(side="left", padx=14)
            ctk.CTkButton(
                bar, text="Cancel",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                fg_color="transparent", hover_color="#1a2a1a",
                text_color="#666666", corner_radius=4,
                border_width=0, width=70, height=26,
                command=_dismiss_notif
            ).pack(side="right", padx=(0, 6))
            ctk.CTkButton(
                bar, text="Install All",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                fg_color="#1a4a1a", hover_color="#226622",
                text_color="#44cc88", corner_radius=4,
                border_width=0, width=90, height=26,
                command=lambda: [_dismiss_notif(), start_install(confirmed_deps=deps)]
            ).pack(side="right", padx=(0, 4))

        def start_install(install_bepinex_first=False, confirmed_deps=None):
            game_data   = self._detected_map.get(game_key)
            install_dir = game_data["install_dir"] if game_data else None

            if not install_dir:
                status_lbl.configure(text="Game not detected", text_color="#cc4444")
                return

            if not os.path.isdir(install_dir):
                status_lbl.configure(text="Install path missing", text_color="#cc4444")
                return

            if not install_bepinex_first and not self._mod_manager.check_modloader(game_key, install_dir):
                _show_bepinex_notif()
                return

            if confirmed_deps is None:
                all_mods = self._mod_index.get("games", {}).get(game_key, {}).get("mods", [])
                deps = self._mod_manager.resolve_dependencies(game_key, mod, all_mods)
                if deps:
                    _show_dep_notif(deps)
                    return

            _dismiss_notif()
            action_btn.configure(state="disabled", text="Downloading...")
            progress_bar.set(0)
            progress_bar.pack(anchor="e", pady=(0, 4))
            action_btn.pack(anchor="e")

            deps_to_install = confirmed_deps or []
            all_installs    = deps_to_install + [mod]
            total_steps     = len(all_installs)

            def install_all():
                game_data2   = self._detected_map.get(game_key)
                install_dir2 = game_data2["install_dir"] if game_data2 else None

                if install_bepinex_first:
                    try:
                        def bep_progress(val):
                            try:
                                progress_bar.set(val * 0.3)
                            except Exception:
                                pass
                        action_btn.after(0, lambda: action_btn.configure(text="Installing mod loader..."))
                        self._mod_manager.install_modloader(game_key, install_dir2, bep_progress)
                    except Exception:
                        progress_bar.after(0, progress_bar.pack_forget)
                        status_lbl.after(0, lambda: status_lbl.configure(text="Mod loader install failed", text_color="#cc4444"))
                        action_btn.after(0, lambda: action_btn.configure(state="normal", text="Retry"))
                        action_btn.after(0, lambda: action_btn.pack(anchor="e"))
                        return

                bep_offset = 0.3 if install_bepinex_first else 0.0
                remaining  = 1.0 - bep_offset

                for i, current_mod in enumerate(all_installs):
                    step_start = bep_offset + (i / total_steps) * remaining
                    step_end   = bep_offset + ((i + 1) / total_steps) * remaining
                    name       = current_mod["name"]

                    action_btn.after(0, lambda n=name: action_btn.configure(text=f"Installing {n}..."))

                    def progress_cb(val, s=step_start, e=step_end):
                        try:
                            progress_bar.set(s + val * (e - s))
                        except Exception:
                            pass

                    try:
                        if current_mod.get("source") == "thunderstore":
                            self._mod_manager.install_mod_thunderstore(game_key, current_mod, install_dir2, progress_cb)
                        else:
                            self._mod_manager.install_mod(game_key, current_mod, install_dir2, progress_cb)
                    except Exception:
                        progress_bar.after(0, progress_bar.pack_forget)
                        status_lbl.after(0, lambda n=name: status_lbl.configure(
                            text=f"Failed: {n}", text_color="#cc4444"))
                        action_btn.after(0, lambda: action_btn.configure(state="normal", text="Retry"))
                        action_btn.after(0, lambda: action_btn.pack(anchor="e"))
                        return

                if on_install_done:
                    progress_bar.after(0, on_install_done)
                else:
                    progress_bar.after(0, progress_bar.pack_forget)
                    status_lbl.after(0, lambda: status_lbl.configure(text="Installed", text_color="#44cc88"))
                    def set_remove():
                        action_btn.configure(
                            text="Remove", fg_color="#2a2a2a",
                            hover_color="#3a1a1a", text_color="#cc4444",
                            command=do_remove, state="normal"
                        )
                        action_btn.pack(anchor="e")
                    action_btn.after(0, set_remove)

            threading.Thread(target=install_all, daemon=True).start()

        action_btn.configure(command=do_remove if installed else start_install)

        all_row_widgets = [row, left, right, top_line]
        all_row_widgets += self._all_descendants(left)
        all_row_widgets += self._all_descendants(top_line)
        _glow_on_hover(row, targets=all_row_widgets, bg_normal=CARD_BG, bg_hover="#222222")

    def _all_descendants(self, widget):
        result = []
        try:
            for child in widget.winfo_children():
                result.append(child)
                result.extend(self._all_descendants(child))
        except Exception:
            pass
        return result

    def _build_settings(self, parent):
        import subprocess, webbrowser

        scroll = ctk.CTkScrollableFrame(parent, fg_color=BG, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        def section(title):
            wrap = ctk.CTkFrame(scroll, fg_color=BG, corner_radius=0)
            wrap.pack(fill="x", padx=32, pady=(28, 0))
            ctk.CTkLabel(
                wrap, text=title,
                font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                text_color=TEXT_ON, anchor="w"
            ).pack(anchor="w", pady=(0, 8))
            ctk.CTkFrame(wrap, fg_color="#252525", height=1, corner_radius=0).pack(fill="x", pady=(0, 14))
            return wrap

        def row(parent, label, widget_fn):
            r = ctk.CTkFrame(parent, fg_color=CARD_BG, corner_radius=8, height=54)
            r.pack(fill="x", pady=(0, 6))
            r.pack_propagate(False)
            ctk.CTkLabel(
                r, text=label,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_ON, anchor="w"
            ).pack(side="left", padx=16)
            widget_fn(r)
            return r

        def action_btn(parent, text, command, danger=False):
            btn = ctk.CTkButton(
                parent, text=text,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                fg_color="#2a2a2a" if not danger else "#3a1010",
                hover_color="#333333" if not danger else "#5a1a1a",
                text_color=TEXT_DIM if not danger else "#cc4444",
                corner_radius=6, border_width=0,
                width=140, height=30,
                command=command
            )
            btn.pack(side="right", padx=16)
            _glow_on_hover(btn, targets=[btn], is_btn=True)
            return btn

        # --- About ---
        about = section("About")

        version_row = ctk.CTkFrame(about, fg_color=CARD_BG, corner_radius=8, height=54)
        version_row.pack(fill="x", pady=(0, 6))
        version_row.pack_propagate(False)

        ctk.CTkLabel(
            version_row, text=f"Moxi  v{MOXI_VERSION}",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=TEXT_ON, anchor="w"
        ).pack(side="left", padx=16)

        update_lbl = ctk.CTkLabel(
            version_row, text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_DIM
        )
        update_lbl.pack(side="right", padx=(0, 8))

        def check_updates():
            check_btn.configure(state="disabled", text="Checking...")
            update_lbl.configure(text="")
            def _check():
                try:
                    tag, changelog, dl_url = self._mod_manager.check_for_app_update()
                    if tag and tag != MOXI_VERSION:
                        self._pending_update = {"version": tag, "changelog": changelog, "dl_url": dl_url}
                        def _show():
                            update_lbl.configure(text=f"v{tag} available", text_color=ACCENT)
                            check_btn.configure(state="normal", text="Download Update",
                                command=lambda: do_download(tag, changelog, dl_url))
                        check_btn.after(0, _show)
                    else:
                        check_btn.after(0, lambda: update_lbl.configure(text="Up to date", text_color="#44cc88"))
                        check_btn.after(0, lambda: check_btn.configure(state="normal", text="Check for Updates"))
                except Exception:
                    check_btn.after(0, lambda: update_lbl.configure(text="Check failed", text_color="#cc4444"))
                    check_btn.after(0, lambda: check_btn.configure(state="normal", text="Check for Updates"))
            threading.Thread(target=_check, daemon=True).start()

        def do_download(tag, changelog, dl_url):
            if not dl_url:
                update_lbl.configure(text="No installer found in release", text_color="#cc4444")
                return
            check_btn.configure(state="disabled", text="Downloading...")
            threading.Thread(
                target=self._do_download_update,
                args=(tag, changelog, dl_url, None, check_btn, update_lbl),
                daemon=True
            ).start()

        check_btn = action_btn(version_row, "Check for Updates", check_updates)

        # --- Game Paths ---
        paths_sec = section("Game Install Paths")

        for appid, info in SUPPORTED_GAMES.items():
            game_name = info["name"]
            game_key  = info["game_key"]
            detected  = self._detected_map.get(game_key)
            current   = detected["install_dir"] if detected else None

            path_row = ctk.CTkFrame(paths_sec, fg_color=CARD_BG, corner_radius=8, height=54)
            path_row.pack(fill="x", pady=(0, 6))
            path_row.pack_propagate(False)

            ctk.CTkLabel(
                path_row, text=game_name,
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_ON, anchor="w", width=160
            ).pack(side="left", padx=16)

            path_lbl = ctk.CTkLabel(
                path_row,
                text=current if current else "Not detected",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=TEXT_DIM if current else "#555555",
                anchor="w"
            )
            path_lbl.pack(side="left", padx=(0, 8), fill="x", expand=True)

            def browse(gkey=game_key, lbl=path_lbl):
                from tkinter import filedialog
                path = filedialog.askdirectory(title=f"Select install folder")
                if path:
                    if gkey not in self._detected_map:
                        self._detected_map[gkey] = {}
                    self._detected_map[gkey]["install_dir"] = path
                    lbl.configure(text=path, text_color=TEXT_DIM)

            browse_btn = ctk.CTkButton(
                path_row, text="Browse",
                font=ctk.CTkFont(family="Segoe UI", size=11),
                fg_color="#2a2a2a", hover_color="#333333",
                text_color=TEXT_DIM,
                corner_radius=6, border_width=0,
                width=80, height=30,
                command=browse
            )
            browse_btn.pack(side="right", padx=16)
            _glow_on_hover(browse_btn, targets=[browse_btn], is_btn=True)

        # --- Data ---
        data_sec = section("Data")

        def open_data_folder():
            path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Moxi")
            os.makedirs(path, exist_ok=True)
            os.startfile(path)

        row(data_sec, "Open Moxi data folder", lambda p: action_btn(p, "Open Folder", open_data_folder))

        def clear_cache():
            import json
            dialog = ctk.CTkToplevel(self)
            dialog.title("Confirm")
            dialog.geometry("360x150")
            dialog.resizable(False, False)
            dialog.configure(fg_color="#1a1a1a")
            dialog.grab_set()
            dialog.lift()
            dialog.focus_force()

            ctk.CTkLabel(
                dialog,
                text="This will remove all installed mod records.\nActual mod files will NOT be deleted.",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                text_color=TEXT_DIM, justify="center"
            ).pack(pady=(24, 16))

            btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
            btn_row.pack()

            def confirm():
                try:
                    db = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Moxi", "installed.json")
                    if os.path.exists(db):
                        os.remove(db)
                    self._mod_manager._load_installed()
                except Exception:
                    pass
                dialog.destroy()

            no_btn = ctk.CTkButton(
                btn_row, text="Cancel",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                fg_color="#2a2a2a", hover_color="#333333",
                text_color=TEXT_DIM, corner_radius=6, width=90, height=32,
                command=dialog.destroy
            )
            no_btn.pack(side="left", padx=(0, 10))
            _glow_on_hover(no_btn, targets=[no_btn], is_btn=True)

            yes_btn = ctk.CTkButton(
                btn_row, text="Clear Cache",
                font=ctk.CTkFont(family="Segoe UI", size=12),
                fg_color="#3a1010", hover_color="#5a1a1a",
                text_color="#cc4444", corner_radius=6, width=110, height=32,
                command=confirm
            )
            yes_btn.pack(side="left")
            _glow_on_hover(yes_btn, targets=[yes_btn], is_btn=True)

        row(data_sec, "Clear installed mods cache", lambda p: action_btn(p, "Clear Cache", clear_cache, danger=True))

        def reset_recently_played():
            self._recently_played = []
            self._save_recently_played()
            if self._recently_played_row is not None:
                try:
                    for w in self._recently_played_row.winfo_children():
                        w.destroy()
                    ctk.CTkLabel(
                        self._recently_played_row,
                        text="Nothing here yet.",
                        font=ctk.CTkFont(family="Segoe UI", size=12),
                        text_color=TEXT_DIM
                    ).pack(side="left", padx=16, pady=30)
                except Exception:
                    pass

        row(data_sec, "Clear recently played history", lambda p: action_btn(p, "Clear History", reset_recently_played, danger=True))