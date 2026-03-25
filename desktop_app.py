"""
Owlet Dream Logger - Desktop Application

A standalone desktop GUI for monitoring Owlet Smart Sock 3 vitals in real-time.
No web server needed — runs as a native window using CustomTkinter.

Usage:
    python desktop_app.py
"""

import asyncio
import json
import logging
import threading
from datetime import datetime
import customtkinter as ctk

from pyowletapi.api import OwletAPI
from pyowletapi.sock import Sock

from config import UPDATE_INTERVAL, LOG_FILE
from owlet_service import discover_socks
from data_processing import process_properties
from csv_logger import init_csv_logging, log_data_to_csv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("owlet_desktop")

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

# Color palette
COLORS = {
    "bg": "#f0f2f5",
    "card": "#ffffff",
    "text": "#1f2937",
    "text_sub": "#6b7280",
    "green": "#10b981",
    "yellow": "#f59e0b",
    "red": "#ef4444",
    "blue": "#3b82f6",
    "purple": "#7c3aed",
    "border": "#e5e7eb",
    "table_header": "#f9fafb",
}


class VitalCard(ctk.CTkFrame):
    """A card widget displaying a single vital sign."""

    def __init__(self, master, label, unit="", show_badge=False, show_progress=False, **kwargs):
        super().__init__(master, fg_color=COLORS["card"], corner_radius=16,
                         border_width=1, border_color=COLORS["border"], **kwargs)

        self.label = ctk.CTkLabel(self, text=label.upper(), font=("Inter", 11, "bold"),
                                  text_color=COLORS["text_sub"])
        self.label.pack(anchor="w", padx=15, pady=(12, 0))

        self.value_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.value_frame.pack(anchor="w", padx=15, pady=(2, 0))

        self.value_label = ctk.CTkLabel(self.value_frame, text="--",
                                        font=("Inter", 36, "bold"),
                                        text_color=COLORS["text"])
        self.value_label.pack(side="left")

        if unit:
            self.unit_label = ctk.CTkLabel(self.value_frame, text=unit,
                                           font=("Inter", 14, "bold"),
                                           text_color=COLORS["text_sub"])
            self.unit_label.pack(side="left", padx=(4, 0), pady=(10, 0))

        # Quality badge (shown next to HR)
        self.badge_label = None
        if show_badge:
            self.badge_label = ctk.CTkLabel(self.value_frame, text="",
                                            font=("Inter", 10, "bold"),
                                            fg_color=COLORS["border"],
                                            corner_radius=6, padx=8, pady=2)
            self.badge_label.pack(side="left", padx=(8, 0), pady=(10, 0))

        # Progress bar for movement
        self.progress_bar = None
        if show_progress:
            self.progress_bar = ctk.CTkProgressBar(self, width=200, height=12,
                                                    corner_radius=6,
                                                    fg_color=COLORS["border"],
                                                    progress_color="#374151")
            self.progress_bar.pack(anchor="w", padx=15, pady=(6, 0))
            self.progress_bar.set(0)

            self.progress_labels = ctk.CTkFrame(self, fg_color="transparent")
            self.progress_labels.pack(fill="x", padx=15, pady=(2, 0))
            ctk.CTkLabel(self.progress_labels, text="Peaceful",
                         font=("Inter", 9), text_color=COLORS["text_sub"]).pack(side="left")
            ctk.CTkLabel(self.progress_labels, text="Wiggling",
                         font=("Inter", 9), text_color=COLORS["text_sub"]).pack(side="right")

        self.sub_label = ctk.CTkLabel(self, text="", font=("Inter", 11),
                                      text_color=COLORS["text_sub"])
        self.sub_label.pack(anchor="w", padx=15, pady=(4, 12))

    def set_value(self, val, color=None):
        self.value_label.configure(text=str(val) if val is not None else "--")
        if color:
            self.value_label.configure(text_color=color)

    def set_sub(self, text):
        self.sub_label.configure(text=text)

    def set_badge(self, text, fg_color, text_color):
        if self.badge_label:
            if text:
                self.badge_label.configure(text=f" {text} ", fg_color=fg_color,
                                           text_color=text_color)
                self.badge_label.pack(side="left", padx=(8, 0), pady=(10, 0))
            else:
                self.badge_label.pack_forget()

    def set_progress(self, value):
        if self.progress_bar:
            self.progress_bar.set(max(0.0, min(1.0, value / 100.0)))


class TechCard(ctk.CTkFrame):
    """A small diagnostic card for technical info."""

    def __init__(self, master, label, **kwargs):
        super().__init__(master, fg_color=COLORS["card"], corner_radius=12,
                         border_width=1, border_color=COLORS["border"], **kwargs)

        self.label = ctk.CTkLabel(self, text=label.upper(), font=("Inter", 10, "bold"),
                                  text_color=COLORS["text_sub"])
        self.label.pack(anchor="w", padx=10, pady=(8, 0))

        self.value_label = ctk.CTkLabel(self, text="--",
                                        font=("JetBrains Mono", 14, "bold"),
                                        text_color=COLORS["text"])
        self.value_label.pack(anchor="w", padx=10, pady=(2, 8))

    def set_value(self, val, color=None):
        self.value_label.configure(text=str(val) if val is not None else "--")
        if color:
            self.value_label.configure(text_color=color)


class LoginFrame(ctk.CTkFrame):
    """Login screen for entering Owlet credentials."""

    def __init__(self, master, on_login):
        super().__init__(master, fg_color=COLORS["bg"])
        self.on_login = on_login

        # Center container
        container = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=20,
                                 border_width=1, border_color=COLORS["border"])
        container.place(relx=0.5, rely=0.45, anchor="center")

        ctk.CTkLabel(container, text="Owlet Dream Logger",
                     font=("Inter", 24, "bold"),
                     text_color=COLORS["text"]).pack(padx=40, pady=(30, 5))

        ctk.CTkLabel(container, text="Sign in to your Owlet account",
                     font=("Inter", 13),
                     text_color=COLORS["text_sub"]).pack(pady=(0, 20))

        self.email_entry = ctk.CTkEntry(container, placeholder_text="Email",
                                        width=300, height=40, font=("Inter", 13))
        self.email_entry.pack(pady=(0, 10), padx=40)

        self.password_entry = ctk.CTkEntry(container, placeholder_text="Password",
                                           show="•", width=300, height=40,
                                           font=("Inter", 13))
        self.password_entry.pack(pady=(0, 10), padx=40)

        self.region_var = ctk.StringVar(value="europe")
        self.region_menu = ctk.CTkOptionMenu(container, values=["europe", "world"],
                                             variable=self.region_var, width=300,
                                             height=40, font=("Inter", 13))
        self.region_menu.pack(pady=(0, 20), padx=40)

        self.login_btn = ctk.CTkButton(container, text="Connect", width=300, height=42,
                                       font=("Inter", 14, "bold"), corner_radius=10,
                                       command=self._handle_login)
        self.login_btn.pack(pady=(0, 10), padx=40)

        self.status_label = ctk.CTkLabel(container, text="", font=("Inter", 12),
                                         text_color=COLORS["red"])
        self.status_label.pack(pady=(0, 25), padx=40)

        # Bind Enter key
        self.password_entry.bind("<Return>", lambda e: self._handle_login())

    def _handle_login(self):
        email = self.email_entry.get().strip()
        password = self.password_entry.get().strip()
        region = self.region_var.get()

        if not email or not password:
            self.status_label.configure(text="Please enter email and password.")
            return

        self.login_btn.configure(state="disabled", text="Connecting...")
        self.status_label.configure(text="", text_color=COLORS["text_sub"])
        self.on_login(email, password, region)

    def show_error(self, msg):
        self.status_label.configure(text=msg, text_color=COLORS["red"])
        self.login_btn.configure(state="normal", text="Connect")


class DashboardFrame(ctk.CTkFrame):
    """Main dashboard showing live vitals with tabbed layout."""

    def __init__(self, master, on_disconnect):
        super().__init__(master, fg_color=COLORS["bg"])
        self.on_disconnect = on_disconnect

        # Stale HR tracking
        self._last_hr = -1
        self._hr_stale_count = 0

        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(15, 5))

        header_left = ctk.CTkFrame(header, fg_color="transparent")
        header_left.pack(side="left")

        ctk.CTkLabel(header_left, text="Owlet Dream Logger",
                     font=("Inter", 22, "bold"),
                     text_color=COLORS["text"]).pack(anchor="w")

        btn_frame = ctk.CTkFrame(header, fg_color="transparent")
        btn_frame.pack(side="right")

        self.device_state_badge = ctk.CTkLabel(btn_frame, text="",
                                                  font=("Inter", 11, "bold"),
                                                  fg_color=COLORS["border"],
                                                  corner_radius=12, padx=10, pady=4)
        self.device_state_badge.pack(side="left", padx=(0, 6))

        self.alarm_badge = ctk.CTkLabel(btn_frame, text="",
                                        font=("Inter", 11, "bold"),
                                        fg_color=COLORS["border"],
                                        corner_radius=12, padx=10, pady=4)
        self.alarm_badge.pack(side="left", padx=(0, 6))
        self.alarm_badge.pack_forget()
        self._alarm_visible = False

        self.status_badge = ctk.CTkLabel(btn_frame, text="Connecting...",
                                         font=("Inter", 12, "bold"),
                                         fg_color=COLORS["border"],
                                         corner_radius=12, padx=12, pady=4)
        self.status_badge.pack(side="left", padx=(0, 10))

        ctk.CTkButton(btn_frame, text="Disconnect", width=100, height=32,
                      fg_color=COLORS["red"], hover_color="#dc2626",
                      font=("Inter", 12, "bold"), corner_radius=8,
                      command=on_disconnect).pack(side="left")

        # Warning banner
        self.warning_frame = ctk.CTkFrame(self, fg_color="#fef3c7", corner_radius=12,
                                          border_width=2, border_color=COLORS["yellow"])
        self.warning_label = ctk.CTkLabel(self.warning_frame, text="",
                                          font=("Inter", 12), text_color="#78350f")
        self.warning_label.pack(padx=15, pady=10)
        self._warning_visible = False

        # Alert banner (device alerts like low oxygen, sock off, etc.)
        self.alert_frame = ctk.CTkFrame(self, fg_color="#fee2e2", corner_radius=12,
                                        border_width=2, border_color=COLORS["red"])
        self.alert_label = ctk.CTkLabel(self.alert_frame, text="",
                                        font=("Inter", 12, "bold"), text_color="#991b1b")
        self.alert_label.pack(padx=15, pady=10)
        self._alert_visible = False

        # Tabview
        self.tabview = ctk.CTkTabview(self, fg_color=COLORS["bg"],
                                       segmented_button_fg_color=COLORS["border"],
                                       segmented_button_selected_color=COLORS["blue"],
                                       segmented_button_unselected_color=COLORS["card"])
        self.tabview.pack(fill="both", expand=True, padx=15, pady=(5, 15))

        # === TAB 1: LIVE VITALS ===
        tab_vitals = self.tabview.add("Live Vitals")

        vitals_scroll = ctk.CTkScrollableFrame(tab_vitals, fg_color=COLORS["bg"])
        vitals_scroll.pack(fill="both", expand=True)

        # Vital cards row
        vitals_grid = ctk.CTkFrame(vitals_scroll, fg_color="transparent")
        vitals_grid.pack(fill="x", pady=(5, 10))
        vitals_grid.columnconfigure((0, 1, 2, 3), weight=1, uniform="vital")

        self.hr_card = VitalCard(vitals_grid, "Heart Rate", "BPM", show_badge=True)
        self.hr_card.grid(row=0, column=0, padx=5, pady=5, sticky="nsew")

        self.ox_card = VitalCard(vitals_grid, "Oxygen (SpO2)", "%")
        self.ox_card.grid(row=0, column=1, padx=5, pady=5, sticky="nsew")

        self.mv_card = VitalCard(vitals_grid, "Baby Status", "", show_progress=True)
        self.mv_card.grid(row=0, column=2, padx=5, pady=5, sticky="nsew")

        self.lag_card = VitalCard(vitals_grid, "Data Freshness", "sec")
        self.lag_card.grid(row=0, column=3, padx=5, pady=5, sticky="nsew")

        # Technical Diagnostics section
        ctk.CTkLabel(vitals_scroll, text="TECHNICAL DIAGNOSTICS",
                     font=("Inter", 12, "bold"),
                     text_color=COLORS["text_sub"]).pack(anchor="w", pady=(15, 8))

        tech_grid = ctk.CTkFrame(vitals_scroll, fg_color="transparent")
        tech_grid.pack(fill="x", pady=(0, 10))
        tech_grid.columnconfigure((0, 1, 2, 3, 4, 5), weight=1, uniform="tech")

        self.tech_cards = {}
        tech_items = [
            ("onm", "Monitoring"), ("bp", "Band Placement"), ("mrs", "Monitor Ready"),
            ("bso", "Base Station"), ("mvb", "Movement %"), ("ss", "Sleep State"),
            ("rsi", "WiFi Signal"), ("sc", "Sock Conn"), ("chg", "Charging"),
            ("bat", "Battery"), ("st", "Skin Temp"), ("sock_off", "Sock Off"),
        ]
        for i, (key, label) in enumerate(tech_items):
            card = TechCard(tech_grid, label)
            card.grid(row=i // 6, column=i % 6, padx=4, pady=4, sticky="nsew")
            self.tech_cards[key] = card

        # Alert history summary on live vitals tab
        ctk.CTkLabel(vitals_scroll, text="ALERT HISTORY SUMMARY",
                     font=("Inter", 12, "bold"),
                     text_color=COLORS["text_sub"]).pack(anchor="w", pady=(15, 8))

        summary_grid = ctk.CTkFrame(vitals_scroll, fg_color="transparent")
        summary_grid.pack(fill="x", pady=(0, 10))
        summary_grid.columnconfigure((0, 1, 2, 3), weight=1, uniform="summary")

        self.summary_cards = {}
        summary_items = [
            ("total_alerts", "Total Alerts"),
            ("alert_types", "Alert Types"),
            ("hr_range", "HR During Alerts"),
            ("ox_range", "SpO2 During Alerts"),
        ]
        for i, (key, label) in enumerate(summary_items):
            card = TechCard(summary_grid, label)
            card.grid(row=0, column=i, padx=4, pady=4, sticky="nsew")
            self.summary_cards[key] = card

        # === TAB 2: DEVICE INSIGHTS ===
        tab_raw = self.tabview.add("Device Insights")

        insights_scroll = ctk.CTkScrollableFrame(tab_raw, fg_color=COLORS["bg"])
        insights_scroll.pack(fill="both", expand=True)

        # --- Section 1: Device & Firmware Info ---
        ctk.CTkLabel(insights_scroll, text="DEVICE & FIRMWARE",
                     font=("Inter", 12, "bold"),
                     text_color=COLORS["text_sub"]).pack(anchor="w", pady=(5, 8))

        info_grid = ctk.CTkFrame(insights_scroll, fg_color="transparent")
        info_grid.pack(fill="x", pady=(0, 10))
        info_grid.columnconfigure((0, 1, 2, 3), weight=1, uniform="info")

        self.info_cards = {}
        info_items = [
            ("base_fw", "Base Firmware"), ("sock_fw", "Sock Firmware"),
            ("base_hw", "Base Hardware"), ("flash_version", "Flash Version"),
            ("sock_mac", "Sock MAC"), ("base_mac", "Base MAC"),
            ("fw_update", "FW Update"), ("battery_raw", "Battery Raw"),
        ]
        for i, (key, label) in enumerate(info_items):
            card = TechCard(info_grid, label)
            card.grid(row=i // 4, column=i % 4, padx=4, pady=4, sticky="nsew")
            self.info_cards[key] = card

        # --- Section 2: Monitoring Settings ---
        ctk.CTkLabel(insights_scroll, text="MONITORING SETTINGS",
                     font=("Inter", 12, "bold"),
                     text_color=COLORS["text_sub"]).pack(anchor="w", pady=(15, 8))

        settings_grid = ctk.CTkFrame(insights_scroll, fg_color="transparent")
        settings_grid.pack(fill="x", pady=(0, 10))
        settings_grid.columnconfigure((0, 1, 2, 3), weight=1, uniform="settings")

        self.settings_cards = {}
        settings_items = [
            ("onm_setting", "Monitor Mode"), ("ox_baseline", "SpO2 Baseline"),
            ("hr_baseline", "HR Baseline"), ("sleep_state", "Sleep State"),
        ]
        for i, (key, label) in enumerate(settings_items):
            card = TechCard(settings_grid, label)
            card.grid(row=0, column=i, padx=4, pady=4, sticky="nsew")
            self.settings_cards[key] = card

        # --- Section 3: Alert History ---
        alert_header = ctk.CTkFrame(insights_scroll, fg_color="transparent")
        alert_header.pack(fill="x", pady=(15, 8))
        ctk.CTkLabel(alert_header, text="ALERT HISTORY",
                     font=("Inter", 12, "bold"),
                     text_color=COLORS["text_sub"]).pack(side="left")
        self.alert_count_label = ctk.CTkLabel(alert_header, text="",
                                               font=("Inter", 11),
                                               text_color=COLORS["text_sub"])
        self.alert_count_label.pack(side="right")

        # Alert history table header
        alert_table_header = ctk.CTkFrame(insights_scroll, fg_color=COLORS["table_header"],
                                           corner_radius=8)
        alert_table_header.pack(fill="x")
        alert_table_header.columnconfigure(0, weight=1)
        alert_table_header.columnconfigure(1, weight=1)
        alert_table_header.columnconfigure(2, weight=1)
        alert_table_header.columnconfigure(3, weight=1)
        alert_table_header.columnconfigure(4, weight=2)

        for col, text in enumerate(["#", "HR", "SpO2", "DUR", "TYPE"]):
            ctk.CTkLabel(alert_table_header, text=text, font=("Inter", 10, "bold"),
                         text_color=COLORS["text_sub"]).grid(
                row=0, column=col, padx=8, pady=6, sticky="w")

        # Scrollable alert history body
        self.alert_scroll = ctk.CTkScrollableFrame(insights_scroll, fg_color=COLORS["card"],
                                                    height=250)
        self.alert_scroll.pack(fill="x", pady=(0, 10))
        self.alert_scroll.columnconfigure(0, weight=1)
        self.alert_scroll.columnconfigure(1, weight=1)
        self.alert_scroll.columnconfigure(2, weight=1)
        self.alert_scroll.columnconfigure(3, weight=1)
        self.alert_scroll.columnconfigure(4, weight=2)

        self._alert_rows = []

    def set_connected(self):
        self.status_badge.configure(text="Connected", fg_color="#d1fae5",
                                    text_color="#065f46")

    def set_disconnected(self):
        self.status_badge.configure(text="Disconnected", fg_color="#fee2e2",
                                    text_color="#991b1b")

    def show_warning(self, message, critical=False):
        color = "#fee2e2" if critical else "#fef3c7"
        border = COLORS["red"] if critical else COLORS["yellow"]
        text_color = "#991b1b" if critical else "#78350f"
        self.warning_frame.configure(fg_color=color, border_color=border)
        self.warning_label.configure(text=f"⚠  {message}", text_color=text_color)
        if not self._warning_visible:
            self.tabview.pack_forget()
            self.warning_frame.pack(fill="x", padx=20, pady=(5, 0))
            self.tabview.pack(fill="both", expand=True, padx=15, pady=(5, 15))
            self._warning_visible = True

    def hide_warning(self):
        if self._warning_visible:
            self.warning_frame.pack_forget()
            self._warning_visible = False

    def show_alerts(self, alert_text, critical=False):
        """Show the device alert banner."""
        fg = "#fee2e2" if critical else "#fef3c7"
        border = COLORS["red"] if critical else COLORS["yellow"]
        text_color = "#991b1b" if critical else "#92400e"
        self.alert_frame.configure(fg_color=fg, border_color=border)
        self.alert_label.configure(text=f"🚨  {alert_text}", text_color=text_color)
        if not self._alert_visible:
            self.tabview.pack_forget()
            self.alert_frame.pack(fill="x", padx=20, pady=(5, 0))
            self.tabview.pack(fill="both", expand=True, padx=15, pady=(5, 15))
            self._alert_visible = True

    def hide_alerts(self):
        if self._alert_visible:
            self.alert_frame.pack_forget()
            self._alert_visible = False

    def update_vitals(self, data):
        """Update all dashboard widgets with new data."""
        v = data.get("vitals", {})
        meta = data.get("meta", {})
        alerts = data.get("alerts", {})
        device_info = data.get("device_info", {})
        alert_history_data = data.get("alert_history", {})
        alert_history = alert_history_data.get("records", []) if isinstance(alert_history_data, dict) else alert_history_data
        alert_history_ts = alert_history_data.get("updated_at") if isinstance(alert_history_data, dict) else None
        alert_history_epoch = alert_history_data.get("header_epoch") if isinstance(alert_history_data, dict) else None
        device_state = data.get("device_state", "Unknown")
        alarm_priority = data.get("alarm_priority")

        # --- Device State Badge ---
        state_config = {
            "Monitoring": ("#d1fae5", "#065f46"),
            "Charging": ("#ede9fe", "#5b21b6"),
            "Charged": ("#dbeafe", "#1e40af"),
            "No Signal": ("#fef3c7", "#92400e"),
            "Disconnected": ("#fee2e2", "#991b1b"),
        }
        bg, fg = state_config.get(device_state, (COLORS["border"], COLORS["text"]))
        self.device_state_badge.configure(text=device_state, fg_color=bg, text_color=fg)

        # --- Alarm Priority Badge ---
        if alarm_priority:
            prio_config = {
                "HIGH": ("#fee2e2", "#991b1b", "\u26a0 HIGH"),
                "MED": ("#fef3c7", "#92400e", "\u26a0 MED"),
                "LOW": ("#dbeafe", "#1e40af", "\u26a0 LOW"),
            }
            p_bg, p_fg, p_text = prio_config.get(alarm_priority, (COLORS["border"], COLORS["text"], alarm_priority))
            self.alarm_badge.configure(text=p_text, fg_color=p_bg, text_color=p_fg)
            if not self._alarm_visible:
                self.alarm_badge.pack(side="left", padx=(0, 6), before=self.status_badge)
                self._alarm_visible = True
        else:
            if self._alarm_visible:
                self.alarm_badge.pack_forget()
                self._alarm_visible = False

        # --- Device Alerts ---
        active_alerts = []
        if alerts.get("critical_oxygen"): active_alerts.append("Critical Oxygen")
        if alerts.get("low_oxygen"): active_alerts.append("Low Oxygen")
        if alerts.get("low_heart_rate"): active_alerts.append("Low Heart Rate")
        if alerts.get("high_heart_rate"): active_alerts.append("High Heart Rate")
        if alerts.get("critical_battery"): active_alerts.append("Critical Battery")
        if alerts.get("low_battery"): active_alerts.append("Low Battery")
        if alerts.get("sock_disconnected"): active_alerts.append("Sock Disconnected")
        if alerts.get("sock_off"): active_alerts.append("Sock Off")
        if alerts.get("lost_power"): active_alerts.append("Lost Power")
        if alerts.get("discomfort"): active_alerts.append("Discomfort")
        if alerts.get("low_integrity_read"): active_alerts.append("Low Signal (Yellow)")

        if active_alerts:
            has_critical = any(alerts.get(k) for k in
                             ("critical_oxygen", "low_heart_rate", "high_heart_rate",
                              "critical_battery", "lost_power"))
            self.show_alerts(" \u2022 ".join(active_alerts), critical=has_critical)
        else:
            self.hide_alerts()

        # --- Stale HR detection ---
        current_hr = v.get("hr")
        if current_hr == self._last_hr:
            self._hr_stale_count += 1
        else:
            self._hr_stale_count = 0
            self._last_hr = current_hr

        # Motion artifact detection
        mvb = v.get("mvb") or 0
        motion_artifact = meta.get("motion_artifact", False)

        # Heart rate with color coding (softened during motion artifact)
        hr_color = COLORS["text"]
        if current_hr is not None:
            if motion_artifact and (current_hr > 160 or current_hr < 90):
                hr_color = COLORS["yellow"]  # soften to yellow during movement
            elif 100 <= current_hr <= 160:
                hr_color = COLORS["green"]
            elif (90 <= current_hr < 100) or (160 < current_hr <= 180):
                hr_color = COLORS["yellow"]
            elif current_hr < 90 or current_hr > 180:
                hr_color = COLORS["red"]
        self.hr_card.set_value(current_hr, hr_color)
        if motion_artifact:
            self.hr_card.set_sub("⚡ Motion artifact — reading may be inaccurate")
        else:
            self.hr_card.set_sub("● 100-160 Normal  ● 90-99 Alert  ● <90/>180 Critical")

        # Quality badge on HR card based on band placement state
        bp = v.get("bp")
        is_charging = v.get("chg") == 1

        if is_charging:
            self.hr_card.set_badge("DOCKED", "#ede9fe", "#5b21b6")
        elif motion_artifact:
            self.hr_card.set_badge("MOVING", "#fef3c7", "#92400e")
        elif bp == 10:
            self.hr_card.set_badge("LIVE", "#d1fae5", "#065f46")
        elif bp == 11:
            self.hr_card.set_badge("SETTLING", "#dbeafe", "#1e40af")
        elif bp == 9:
            self.hr_card.set_badge("ACQUIRING", "#dbeafe", "#1e40af")
        elif bp == 8:
            self.hr_card.set_badge("STABILIZING", "#fef3c7", "#92400e")
        elif bp == 1:
            self.hr_card.set_badge("CALIBRATING", "#fef3c7", "#92400e")
        elif bp == 6:
            self.hr_card.set_badge("WEAK", "#fee2e2", "#991b1b")
        elif bp == 7:
            self.hr_card.set_badge("IDLE", "#ede9fe", "#5b21b6")
        else:
            self.hr_card.set_badge("", COLORS["border"], COLORS["text"])

        # Oxygen with color coding (softened during motion artifact)
        ox = v.get("ox")
        ox_color = COLORS["text"]
        if ox is not None:
            if motion_artifact and ox < 95:
                ox_color = COLORS["yellow"]  # soften during movement
            elif ox >= 95:
                ox_color = COLORS["blue"]
            elif ox >= 90:
                ox_color = COLORS["yellow"]
            else:
                ox_color = COLORS["red"]
        self.ox_card.set_value(ox, ox_color)
        oxta = v.get("oxta")
        oxta_text = f"Avg: {oxta}%" if oxta and oxta != 255 else "Avg: --"
        if motion_artifact:
            self.ox_card.set_sub(f"{oxta_text}  ⚡ Motion artifact")
        else:
            self.ox_card.set_sub(f"{oxta_text}  ● ≥95 Normal  ● 90-94 Low  ● <90 Critical")

        # Movement with progress bar and color coding
        mv = v.get("mv")
        if mvb is not None:
            mvb_clamped = max(0, min(100, mvb))
            self.mv_card.set_progress(mvb_clamped)
            if mvb_clamped >= 50:
                mv_color = COLORS["red"]
            elif mvb_clamped >= 25:
                mv_color = COLORS["yellow"]
            else:
                mv_color = COLORS["green"]
            self.mv_card.set_value(f"{mvb_clamped}%", mv_color)
            self.mv_card.set_sub(f"Raw intensity (mv): {mv}")
        else:
            self.mv_card.set_value(None)
            self.mv_card.set_progress(0)
            self.mv_card.set_sub(f"Raw intensity (mv): {mv}" if mv else "")

        # --- Wake detection ---
        ss = v.get("ss")
        if not hasattr(self, '_last_ss'):
            self._last_ss = ss
        if self._last_ss in (8, 15) and ss == 1:
            # Baby transitioned from sleep to awake
            self.show_alerts("👶 Baby woke up!", critical=False)
        self._last_ss = ss

        # Lag
        lag = meta.get("lag_seconds")
        lag_color = COLORS["green"] if lag is not None and lag <= 60 else COLORS["red"]
        lag_display = round(lag, 1) if lag is not None else None
        self.lag_card.set_value(lag_display, lag_color)
        self.lag_card.set_sub("Connection Health")

        # Warning banner
        if meta.get("stale_warning"):
            msg = meta.get("stale_message", "Data may be stale")
            self.show_warning(msg, critical=meta.get("stale_critical", False))
        else:
            self.hide_warning()

        # Tech cards
        onm = v.get("onm")
        if onm == 3:
            self.tech_cards["onm"].set_value("ACTIVE (3)", COLORS["green"])
        elif onm == 0:
            self.tech_cards["onm"].set_value("PAUSED (0)", COLORS["text_sub"])
        else:
            self.tech_cards["onm"].set_value(f"Status {onm}", COLORS["text"])

        mrs = v.get("mrs")
        self.tech_cards["mrs"].set_value("READY" if mrs == 1 else "NOT READY",
                                         COLORS["green"] if mrs == 1 else COLORS["yellow"])

        bp_text, bp_color = f"Code {bp}", COLORS["text"]
        if is_charging:
            bp_text, bp_color = "Docked/Charging", COLORS["purple"]
        elif bp == 1 and motion_artifact:
            bp_text, bp_color = "Moving (1)", COLORS["yellow"]
        elif bp == 1:
            bp_text, bp_color = "Calibrating (1)", COLORS["yellow"]
        elif bp == 6:
            bp_text, bp_color = "Degraded (6)", COLORS["red"]
        elif bp == 7:
            bp_text, bp_color = "Idle/Docked (7)", COLORS["purple"]
        elif bp == 8:
            bp_text, bp_color = "Stabilizing (8)", COLORS["yellow"]
        elif bp == 9:
            bp_text, bp_color = "Acquiring (9)", COLORS["blue"]
        elif bp == 10:
            bp_text, bp_color = "Monitoring (10)", COLORS["green"]
        elif bp == 11:
            bp_text, bp_color = "Settling (11)", COLORS["blue"]
        self.tech_cards["bp"].set_value(bp_text, bp_color)

        bso = v.get("bso")
        self.tech_cards["bso"].set_value("POWER ON" if bso == 1 else "OFF",
                                         COLORS["green"] if bso == 1 else COLORS["red"])

        mvb = v.get("mvb")
        self.tech_cards["mvb"].set_value(f"{mvb}%" if mvb is not None else "-")
        ss = v.get("ss")
        ss_labels = {0: "Inactive", 1: "Awake", 8: "Light Sleep", 15: "Deep Sleep"}
        ss_colors = {0: COLORS["text_sub"], 1: COLORS["yellow"], 8: COLORS["blue"], 15: COLORS["green"]}
        self.tech_cards["ss"].set_value(ss_labels.get(ss, f"State {ss}") if ss is not None else "-",
                                        ss_colors.get(ss, COLORS["text"]))
        rsi = v.get("rsi")
        self.tech_cards["rsi"].set_value(f"{rsi}%" if rsi else "-")
        sc = v.get("sc")
        self.tech_cards["sc"].set_value("Connected" if sc == 2 else f"Code {sc}")
        chg = v.get("chg")
        self.tech_cards["chg"].set_value("⚡ Yes" if chg == 1 else "No",
                                         "#d97706" if chg == 1 else COLORS["text"])
        bat = v.get("bat")
        self.tech_cards["bat"].set_value(f"{bat}%" if bat is not None else "--")

        # Skin temperature
        st = v.get("st")
        if st and st > 0:
            self.tech_cards["st"].set_value(f"{st}°", COLORS["text"])
        else:
            self.tech_cards["st"].set_value("--", COLORS["text_sub"])

        # Sock off
        if alerts.get("sock_off"):
            self.tech_cards["sock_off"].set_value("YES", COLORS["red"])
        else:
            self.tech_cards["sock_off"].set_value("No", COLORS["green"])

        # --- Alert History Summary (lives on Live Vitals tab) ---
        if alert_history:
            self.summary_cards["total_alerts"].set_value(
                str(len(alert_history)),
                COLORS["red"] if len(alert_history) > 50 else COLORS["yellow"])

            # Count unique types
            type_counts = {}
            for rec in alert_history:
                t = rec.get("type_name", "?")
                type_counts[t] = type_counts.get(t, 0) + 1
            types_str = ", ".join(f"{v} {k}" for k, v in type_counts.items())
            self.summary_cards["alert_types"].set_value(
                types_str if len(types_str) <= 30 else f"{len(type_counts)} types", COLORS["text"])

            hrs = [r["hr"] for r in alert_history if 40 <= r["hr"] <= 250]
            if hrs:
                self.summary_cards["hr_range"].set_value(
                    f"{min(hrs)}-{max(hrs)}", COLORS["text"])
            else:
                self.summary_cards["hr_range"].set_value("--", COLORS["text_sub"])

            oxs = [r["ox"] for r in alert_history if 50 <= r["ox"] <= 100]
            if oxs:
                ox_color = COLORS["red"] if min(oxs) < 90 else COLORS["yellow"] if min(oxs) < 95 else COLORS["blue"]
                self.summary_cards["ox_range"].set_value(
                    f"{min(oxs)}-{max(oxs)}%", ox_color)
            else:
                self.summary_cards["ox_range"].set_value("--", COLORS["text_sub"])
        else:
            self.summary_cards["total_alerts"].set_value("0", COLORS["green"])
            self.summary_cards["alert_types"].set_value("None", COLORS["text_sub"])
            self.summary_cards["hr_range"].set_value("--", COLORS["text_sub"])
            self.summary_cards["ox_range"].set_value("--", COLORS["text_sub"])

        # --- Raw Data table ---
        self._update_insights(device_info, alert_history, alert_history_ts, alert_history_epoch)

    def _update_insights(self, device_info, alert_history, alert_ts=None, alert_epoch=None):
        """Update the Device Insights tab with firmware, settings, and alert history."""
        # Device info cards
        for key, card in self.info_cards.items():
            val = device_info.get(key)
            if val is not None:
                display = str(val)
                if len(display) > 25:
                    display = display[:22] + "..."
                color = COLORS["text"]
                if key == "fw_update":
                    color = COLORS["green"] if val == "IDLE" else COLORS["yellow"]
                card.set_value(display, color)
            else:
                card.set_value("--", COLORS["text_sub"])

        # Settings cards
        for key, card in self.settings_cards.items():
            val = device_info.get(key)
            if val is not None:
                if key == "onm_setting":
                    if val == 3:
                        card.set_value("Active (3)", COLORS["green"])
                    elif val == 0:
                        card.set_value("Paused (0)", COLORS["text_sub"])
                    else:
                        card.set_value(f"Mode {val}", COLORS["text"])
                else:
                    card.set_value(str(val), COLORS["text"])
            else:
                card.set_value("--", COLORS["text_sub"])

        # Alert history table
        ts_display = ""
        if alert_epoch:
            ts_display = f" (since {alert_epoch[:10]})"
        elif alert_ts:
            ts_display = f" (updated {alert_ts[:10]})"
        self.alert_count_label.configure(text=f"{len(alert_history)} events{ts_display}")

        # Only rebuild if count changed
        if len(self._alert_rows) // 5 != len(alert_history):
            for widget in self._alert_rows:
                widget.destroy()
            self._alert_rows.clear()

            for i, rec in enumerate(alert_history):
                row_bg = COLORS["card"] if i % 2 == 0 else COLORS["table_header"]

                # Color code based on alert severity
                hr_color = COLORS["text"]
                if rec["hr"] > 0:
                    if 100 <= rec["hr"] <= 160:
                        hr_color = COLORS["green"]
                    elif rec["hr"] > 160 or rec["hr"] < 90:
                        hr_color = COLORS["red"]
                    else:
                        hr_color = COLORS["yellow"]

                ox_color = COLORS["text"]
                if rec["ox"] > 0:
                    if rec["ox"] >= 95:
                        ox_color = COLORS["blue"]
                    elif rec["ox"] >= 90:
                        ox_color = COLORS["yellow"]
                    else:
                        ox_color = COLORS["red"]

                type_color = COLORS["red"] if "Critical" in rec["type_name"] else COLORS["text"]

                cells = [
                    (str(i + 1), COLORS["text_sub"]),
                    (str(rec["hr"]) if rec["hr"] > 0 else "-", hr_color),
                    (f"{rec['ox']}%" if rec["ox"] > 0 else "-", ox_color),
                    (str(rec["duration"]), COLORS["text"]),
                    (rec["type_name"], type_color),
                ]
                for col, (text, color) in enumerate(cells):
                    lbl = ctk.CTkLabel(self.alert_scroll, text=text,
                                       font=("JetBrains Mono", 11),
                                       text_color=color, fg_color=row_bg,
                                       anchor="w")
                    lbl.grid(row=i, column=col, padx=8, pady=2, sticky="nsew")
                    self._alert_rows.append(lbl)


class OwletDesktopApp(ctk.CTk):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.title("Owlet Dream Logger")
        self.geometry("1100x750")
        self.minsize(850, 600)
        self.configure(fg_color=COLORS["bg"])

        self._worker_running = False
        self._loop = None
        self._worker_thread = None

        # Show login first
        self.login_frame = LoginFrame(self, on_login=self._start_connection)
        self.login_frame.pack(fill="both", expand=True)

        self.dashboard_frame = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _start_connection(self, email, password, region):
        """Start the background worker thread."""
        self._worker_running = True
        self._worker_thread = threading.Thread(
            target=self._run_worker_loop,
            args=(email, password, region),
            daemon=True
        )
        self._worker_thread.start()

    def _run_worker_loop(self, email, password, region):
        """Run the async worker loop in a background thread."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._worker(email, password, region))
        except Exception as e:
            logger.error(f"Worker loop error: {e}")
            self.after(0, lambda: self._show_error(str(e)))
        finally:
            self._loop.close()

    async def _worker(self, email, password, region):
        """Async worker: authenticate, discover sock, stream vitals."""
        init_csv_logging(LOG_FILE)

        api = OwletAPI(region, email, password)
        try:
            await api.authenticate()
            logger.info("Authenticated successfully")

            # Switch to dashboard on the main thread
            self.after(0, self._show_dashboard)

            socks = await discover_socks(api)
            if not socks:
                all_devs = await api.get_devices()
                devices_list = []
                if isinstance(all_devs, list):
                    devices_list = all_devs
                elif isinstance(all_devs, dict) and "response" in all_devs:
                    devices_list = all_devs["response"]
                if devices_list:
                    first_dev = devices_list[0].get("device")
                    if first_dev:
                        socks = [Sock(api, first_dev)]

            if not socks:
                self.after(0, lambda: self._show_error("No Owlet sock found on this account."))
                return

            sock = socks[0]
            logger.info("Sock discovered, starting monitoring...")

            stale_count = 0
            max_stale_before_warning = 3
            max_lag_seconds = 30

            while self._worker_running:
                result = await sock.update_properties()

                # Handle token refresh
                if isinstance(result, dict) and "tokens" in result:
                    tokens = result["tokens"]
                    if tokens:
                        logger.info("API tokens refreshed automatically")

                if sock.raw_properties:
                    data = process_properties(sock.raw_properties)
                    lag = data["meta"]["lag_seconds"]

                    if lag > max_lag_seconds:
                        stale_count += 1
                        data["meta"]["stale_warning"] = True
                        data["meta"]["stale_message"] = f"Connection may be lost. Data is {lag:.0f} seconds old."
                        if stale_count >= max_stale_before_warning:
                            data["meta"]["stale_critical"] = True
                            data["meta"]["stale_message"] = "Base station connection lost. Check your Owlet device."
                    else:
                        stale_count = 0

                    # Update GUI on main thread
                    self.after(0, self._update_dashboard, data)

                    log_data_to_csv(LOG_FILE, data["vitals"], lag)

                    logger.info(
                        f"HR: {data['vitals'].get('hr')} | "
                        f"Lag: {lag}s | "
                        f"BP: {data['vitals'].get('bp')}"
                    )

                await asyncio.sleep(UPDATE_INTERVAL)

        except Exception as e:
            logger.error(f"Worker error: {e}")
            self.after(0, lambda: self._show_error(f"Connection failed: {e}"))
        finally:
            await api.close()

    def _show_dashboard(self):
        """Switch from login to dashboard view."""
        self.login_frame.pack_forget()
        self.dashboard_frame = DashboardFrame(self, on_disconnect=self._disconnect)
        self.dashboard_frame.pack(fill="both", expand=True)
        self.dashboard_frame.set_connected()

    def _update_dashboard(self, data):
        """Push new data to the dashboard widgets."""
        if self.dashboard_frame:
            self.dashboard_frame.update_vitals(data)

    def _show_error(self, msg):
        """Show error on login screen or as a popup."""
        if self.dashboard_frame:
            self.dashboard_frame.set_disconnected()
            self.dashboard_frame.show_warning(msg, critical=True)
        else:
            self.login_frame.show_error(msg)

    def _disconnect(self):
        """Stop worker and return to login screen."""
        self._worker_running = False
        if self.dashboard_frame:
            self.dashboard_frame.pack_forget()
            self.dashboard_frame = None
        self.login_frame.pack(fill="both", expand=True)
        self.login_frame.login_btn.configure(state="normal", text="Connect")

    def _on_close(self):
        """Clean shutdown on window close."""
        self._worker_running = False
        self.destroy()


if __name__ == "__main__":
    app = OwletDesktopApp()
    app.mainloop()
