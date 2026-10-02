"""Modern GUI Application for YouTube AI Monetization Agent."""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from typing import Any

import tools
from agent import YouTubeAgent, DEFAULT_MODEL

YT_KEY_FILE = "api_key.local.txt"
DS_KEY_FILE = "deepseek_key.local.txt"

BG_DARK = "#18181b"
BG_PANEL = "#27272a"
BG_INPUT = "#3f3f46"
ACCENT = "#0284c7"
ACCENT_HOVER = "#0369a1"
TEXT_COLOR = "#f4f4f5"
TEXT_MUTED = "#a1a1aa"
SUCCESS_COLOR = "#22c55e"
ERROR_COLOR = "#ef4444"


class YouTubeAgentGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("YouTube AI Outreach Agent (DeepSeek)")
        self.root.geometry("1100x820")
        self.root.minsize(900, 650)
        self.root.configure(bg=BG_DARK)

        self.msg_queue: queue.Queue = queue.Queue()
        self.is_running = False

        self._setup_styles()
        self._build_ui()
        self._load_saved_keys()
        self.root.after(100, self._process_queue)

    def _setup_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")

        style.configure(".", background=BG_DARK, foreground=TEXT_COLOR, font=("Segoe UI", 10))
        style.configure("TFrame", background=BG_DARK)
        style.configure("Panel.TFrame", background=BG_PANEL)
        style.configure("TLabel", background=BG_DARK, foreground=TEXT_COLOR)
        style.configure("Panel.TLabel", background=BG_PANEL, foreground=TEXT_COLOR)
        style.configure("Muted.TLabel", background=BG_DARK, foreground=TEXT_MUTED, font=("Segoe UI", 9))
        style.configure("PanelMuted.TLabel", background=BG_PANEL, foreground=TEXT_MUTED, font=("Segoe UI", 9))
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"), foreground=TEXT_COLOR)

        style.configure("TEntry", fieldbackground=BG_INPUT, foreground=TEXT_COLOR, insertcolor=TEXT_COLOR, borderwidth=0)
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff", font=("Segoe UI", 10, "bold"), borderwidth=0, padding=6)
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("disabled", BG_INPUT)])

        style.configure("TNotebook", background=BG_DARK, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_PANEL, foreground=TEXT_MUTED, padding=[12, 6], font=("Segoe UI", 10, "bold"))
        style.map("TNotebook.Tab", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])

        # Treeview styling
        style.configure("Treeview", background=BG_PANEL, foreground=TEXT_COLOR, fieldbackground=BG_PANEL, rowheight=26, borderwidth=0)
        style.configure("Treeview.Heading", background=BG_INPUT, foreground=TEXT_COLOR, font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", ACCENT)], foreground=[("selected", "#ffffff")])

    def _build_ui(self):
        # 1. API Keys Bar
        key_frame = ttk.Frame(self.root, style="Panel.TFrame", padding=12)
        key_frame.pack(fill=tk.X, padx=12, pady=(12, 6))

        # Row 0: YouTube API Key
        ttk.Label(key_frame, text="YouTube API Key:", style="Panel.TLabel").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        self.yt_key_entry = ttk.Entry(key_frame, show="•", width=36)
        self.yt_key_entry.grid(row=0, column=1, padx=6, pady=2)

        # Row 0: DeepSeek Key
        ttk.Label(key_frame, text="DeepSeek API Key:", style="Panel.TLabel").grid(row=0, column=2, sticky="w", padx=12, pady=2)
        self.ds_key_entry = ttk.Entry(key_frame, show="•", width=36)
        self.ds_key_entry.grid(row=0, column=3, padx=6, pady=2)

        self.remember_keys_var = tk.BooleanVar(value=False)
        remember_cb = ttk.Checkbutton(key_frame, text="Запомнить ключи", variable=self.remember_keys_var)
        remember_cb.grid(row=0, column=4, padx=12, pady=2)

        # 2. Main Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        self._build_single_tab()
        self._build_niche_tab()

        # 3. Status Bar
        status_frame = ttk.Frame(self.root, padding=(12, 4))
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_lbl = ttk.Label(status_frame, text="Готов к работе", style="Muted.TLabel")
        self.status_lbl.pack(side=tk.LEFT)

    def _build_single_tab(self):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text=" Анализ одного канала ")

        # Top Control Row
        top_box = ttk.Frame(tab, style="Panel.TFrame", padding=10)
        top_box.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(top_box, text="Канал YouTube (handle, ссылка или ID):", style="Panel.TLabel").pack(side=tk.LEFT, padx=6)
        self.channel_entry = ttk.Entry(top_box, width=35)
        self.channel_entry.pack(side=tk.LEFT, padx=6)
        self.channel_entry.insert(0, "@MrBeast")

        self.run_btn = ttk.Button(top_box, text="🚀 Запустить ИИ-агента", style="Accent.TButton", command=self._start_single_agent)
        self.run_btn.pack(side=tk.LEFT, padx=12)

        # Content split
        paned = tk.PanedWindow(tab, orient=tk.HORIZONTAL, bg=BG_DARK, bd=0, sashwidth=6)
        paned.pack(fill=tk.BOTH, expand=True)

        # Left: Live Agent Log (Thoughts & Tool calls)
        left_frame = ttk.Frame(paned, style="Panel.TFrame", padding=8)
        ttk.Label(left_frame, text="🧠 Лог рассуждений и действий ИИ:", style="Header.TLabel").pack(anchor="w", pady=(0, 4))

        self.log_text = tk.Text(
            left_frame, bg=BG_DARK, fg=TEXT_COLOR, insertbackground=TEXT_COLOR,
            relief=tk.FLAT, wrap=tk.WORD, font=("Consolas", 10), padx=8, pady=8
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)
        paned.add(left_frame, minsize=400)

        # Right: Final Output / Cold DM
        right_frame = ttk.Frame(paned, style="Panel.TFrame", padding=8)
        ttk.Label(right_frame, text="✉️ Готовое обращение (Cold DM):", style="Header.TLabel").pack(anchor="w", pady=(0, 4))

        self.out_text = tk.Text(
            right_frame, bg=BG_DARK, fg=TEXT_COLOR, insertbackground=TEXT_COLOR,
            relief=tk.FLAT, wrap=tk.WORD, font=("Segoe UI", 11), padx=8, pady=8
        )
        self.out_text.pack(fill=tk.BOTH, expand=True)
        paned.add(right_frame, minsize=400)

    def _build_niche_tab(self):
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text=" Поиск каналов по нише ")

        # Search Controls
        search_bar = ttk.Frame(tab, style="Panel.TFrame", padding=10)
        search_bar.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(search_bar, text="Ниша / Ключевые слова:", style="Panel.TLabel").pack(side=tk.LEFT, padx=6)
        self.niche_entry = ttk.Entry(search_bar, width=24)
        self.niche_entry.pack(side=tk.LEFT, padx=6)
        self.niche_entry.insert(0, "crypto trading italy")

        self.search_btn = ttk.Button(search_bar, text="🔍 Найти каналы", style="Accent.TButton", command=self._start_niche_search)
        self.search_btn.pack(side=tk.LEFT, padx=8)

        # Filters for Monetization Matrix
        ttk.Label(search_bar, text="Фильтр монетизации:", style="Panel.TLabel").pack(side=tk.LEFT, padx=(16, 4))
        self.filter_var = tk.StringVar(value="Все")
        self.filter_combo = ttk.Combobox(
            search_bar, textvariable=self.filter_var, width=22, state="readonly",
            values=["Все", "Без курса (course: false)", "Без сообщества (community: false)", "Без монетизации (0 методов)"]
        )
        self.filter_combo.pack(side=tk.LEFT, padx=4)
        self.filter_combo.bind("<<ComboboxSelected>>", lambda _: self._apply_table_filters())

        self.agent_selected_btn = ttk.Button(
            search_bar, text="⚡ Запустить ИИ по выбранному", style="Accent.TButton",
            command=self._start_selected_channel_agent
        )
        self.agent_selected_btn.pack(side=tk.RIGHT, padx=6)

        # Table of channels
        cols = ("title", "handle", "subscribers", "videos", "views", "matrix_summary", "country")
        self.tree = ttk.Treeview(tab, columns=cols, show="headings", selectmode="browse")
        self.tree.heading("title", text="Название канала")
        self.tree.heading("handle", text="Ссылка / Handle")
        self.tree.heading("subscribers", text="Подписчики")
        self.tree.heading("videos", text="Видео")
        self.tree.heading("views", text="Просмотры")
        self.tree.heading("matrix_summary", text="Монетизация (Матрица)")
        self.tree.heading("country", text="Страна")

        self.tree.column("title", width=200)
        self.tree.column("handle", width=140)
        self.tree.column("subscribers", width=95, anchor="e")
        self.tree.column("videos", width=70, anchor="e")
        self.tree.column("views", width=105, anchor="e")
        self.tree.column("matrix_summary", width=220)
        self.tree.column("country", width=65, anchor="center")

        self.raw_niche_results: list[dict[str, Any]] = []

        self.tree.pack(fill=tk.BOTH, expand=True)

    def _load_saved_keys(self):
        yt_k = os.environ.get("YOUTUBE_API_KEY", "")
        if not yt_k and os.path.exists(YT_KEY_FILE):
            try:
                with open(YT_KEY_FILE, "r", encoding="utf-8") as f:
                    yt_k = f.read().strip()
            except Exception:
                pass
        if yt_k:
            self.yt_key_entry.insert(0, yt_k)

        ds_k = os.environ.get("DEEPSEEK_API_KEY", "")
        if not ds_k and os.path.exists(DS_KEY_FILE):
            try:
                with open(DS_KEY_FILE, "r", encoding="utf-8") as f:
                    ds_k = f.read().strip()
            except Exception:
                pass
        if ds_k:
            self.ds_key_entry.insert(0, ds_k)

    def _save_keys_if_needed(self, yt_key: str, ds_key: str):
        if self.remember_keys_var.get():
            try:
                with open(YT_KEY_FILE, "w", encoding="utf-8") as f:
                    f.write(yt_key.strip())
                with open(DS_KEY_FILE, "w", encoding="utf-8") as f:
                    f.write(ds_key.strip())
            except Exception:
                pass

    def _log(self, text: str):
        self.msg_queue.put(("log", text))

    def _set_status(self, text: str):
        self.msg_queue.put(("status", text))

    def _process_queue(self):
        while not self.msg_queue.empty():
            msg_type, data = self.msg_queue.get_nowait()
            if msg_type == "log":
                self.log_text.insert(tk.END, data + "\n")
                self.log_text.see(tk.END)
            elif msg_type == "status":
                self.status_lbl.config(text=data)
            elif msg_type == "output":
                self.out_text.delete("1.0", tk.END)
                self.out_text.insert(tk.END, data)
            elif msg_type == "done":
                self.is_running = False
                self.run_btn.config(state=tk.NORMAL)
                self.search_btn.config(state=tk.NORMAL)
                self.agent_selected_btn.config(state=tk.NORMAL)
            elif msg_type == "error":
                messagebox.showerror("Ошибка", data)
            elif msg_type == "niche_results":
                self.raw_niche_results = data
                self._apply_table_filters()

        self.root.after(100, self._process_queue)

    def _apply_table_filters(self):
        for row in self.tree.get_children():
            self.tree.delete(row)

        filter_choice = self.filter_var.get()

        for it in self.raw_niche_results:
            matrix = it.get("matrix", {})
            has_course = matrix.get("course", False)
            has_community = matrix.get("community", False)
            monetization_detected = matrix.get("monetization_detected", False)

            if "Без курса" in filter_choice and has_course:
                continue
            if "Без сообщества" in filter_choice and has_community:
                continue
            if "Без монетизации" in filter_choice and monetization_detected:
                continue

            # Format matrix summary badges
            tags_list = []
            if matrix.get("course"): tags_list.append("🎓 Курс")
            if matrix.get("community"): tags_list.append("👥 Клуб")
            if matrix.get("affiliate"): tags_list.append("🔗 Партнерки")
            if matrix.get("coaching") or matrix.get("consulting"): tags_list.append("💼 Консалтинг")
            if matrix.get("product") or matrix.get("merch"): tags_list.append("📦 Товар")

            matrix_badge = ", ".join(tags_list) if tags_list else "❌ Не обнаружено"
            conf = matrix.get("confidence", 0.0)
            if matrix_badge != "❌ Не обнаружено":
                matrix_badge += f" ({int(conf * 100)}%)"

            subs = f"{int(it['subscribers']):,}" if it['subscribers'].isdigit() else it['subscribers']
            views = f"{int(it['view_count']):,}" if it['view_count'].isdigit() else it['view_count']

            self.tree.insert("", tk.END, values=(
                it["title"],
                it.get("custom_url") or it["channel_id"],
                subs,
                it["video_count"],
                views,
                matrix_badge,
                it["country"]
            ), tags=(it["channel_id"],))

    def _start_single_agent(self):
        if self.is_running:
            return

        yt_k = self.yt_key_entry.get().strip()
        ds_k = self.ds_key_entry.get().strip()
        channel = self.channel_entry.get().strip()

        if not yt_k:
            messagebox.showwarning("Внимание", "Пожалуйста, введите YouTube API Key.")
            return
        if not ds_k:
            messagebox.showwarning("Внимание", "Пожалуйста, введите DeepSeek API Key.")
            return
        if not channel:
            messagebox.showwarning("Внимание", "Укажите канал для анализа.")
            return

        self._save_keys_if_needed(yt_k, ds_k)
        self.is_running = True
        self.run_btn.config(state=tk.DISABLED)
        self.log_text.delete("1.0", tk.END)
        self.out_text.delete("1.0", tk.END)
        self._set_status(f"Агент работает над каналом {channel}...")

        threading.Thread(
            target=self._run_agent_thread,
            args=(channel, yt_k, ds_k),
            daemon=True
        ).start()

    def _run_agent_thread(self, channel: str, yt_key: str, ds_key: str):
        try:
            agent = YouTubeAgent(
                youtube_api_key=yt_key,
                deepseek_api_key=ds_key,
                on_log=self._log
            )
            res = agent.run(channel)

            dm_text = ""
            saved = res.get("saved", {})
            if "outreach_file" in saved and os.path.exists(saved["outreach_file"]):
                with open(saved["outreach_file"], "r", encoding="utf-8") as f:
                    dm_text = f.read()
            else:
                dm_text = res.get("summary", "")

            self.msg_queue.put(("output", dm_text))
            self._set_status("Готово! Отчет и Cold DM сохранены.")
        except Exception as exc:
            self.msg_queue.put(("error", str(exc)))
            self._set_status(f"Ошибка: {exc}")
        finally:
            self.msg_queue.put(("done", None))

    def _start_niche_search(self):
        if self.is_running:
            return

        yt_k = self.yt_key_entry.get().strip()
        query = self.niche_entry.get().strip()
        if not yt_k:
            messagebox.showwarning("Внимание", "Пожалуйста, введите YouTube API Key.")
            return
        if not query:
            messagebox.showwarning("Внимание", "Введите ключевое слово для поиска.")
            return

        self._set_status(f"Поиск каналов в нише '{query}'...")
        self.is_running = True
        self.search_btn.config(state=tk.DISABLED)

        def search_worker():
            try:
                from googleapiclient.discovery import build
                yt = build("youtube", "v3", developerKey=yt_k)
                results = tools.search_channels_by_niche(yt, query, max_results=30)
                self.msg_queue.put(("niche_results", results))
                self._set_status(f"Найдено {len(results)} каналов.")
            except Exception as exc:
                self.msg_queue.put(("error", f"Ошибка поиска: {exc}"))
                self._set_status("Ошибка поиска.")
            finally:
                self.msg_queue.put(("done", None))

        threading.Thread(target=search_worker, daemon=True).start()

    def _start_selected_channel_agent(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Внимание", "Выберите канал из списка.")
            return

        item = self.tree.item(selected[0])
        handle = item["values"][1] or item["values"][0]

        # Switch to Single tab and run
        self.notebook.select(0)
        self.channel_entry.delete(0, tk.END)
        self.channel_entry.insert(0, str(handle))
        self._start_single_agent()


def main():
    root = tk.Tk()
    app = YouTubeAgentGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
