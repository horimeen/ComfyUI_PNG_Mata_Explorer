# ui/image_gallery.py
import os
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk


class ImageGallery(ttk.Frame):
    def __init__(self, master, *, on_open, **kwargs):
        super().__init__(master, **kwargs)
        self.on_open = on_open

        self.thumb_size_var = tk.IntVar(value=96)

        self._paths = []
        self._display_paths = []  # 排序后的最终显示路径
        self._cols = 1

        self._job = None
        self._render_index = 0
        self._render_batch_size = 10  # 批量渲染数，避免覆盖方法名

        self._cache = {}  # (abs_path, size) -> PhotoImage
        self._thumb_labels_by_index = []
        self._cell_frames_by_index = []
        self._thumb_refs = []

        self._render_token = 0
        self._relayout_job = None

        self._selected_index = None

        # 默认排序方式
        self._sort_mode = "name_asc"

        self._build()

    def _build(self):
        list_container = ttk.Frame(self)
        list_container.pack(fill=tk.BOTH, expand=True)

        self.thumb_canvas = tk.Canvas(list_container, bg="#ffffff", highlightthickness=0)
        self.thumb_scroll = ttk.Scrollbar(
            list_container, orient=tk.VERTICAL, command=self.thumb_canvas.yview
        )
        self.thumb_canvas.configure(yscrollcommand=self.thumb_scroll.set)

        self.thumb_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.thumb_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.thumb_inner = ttk.Frame(self.thumb_canvas)
        self.thumb_canvas_window = self.thumb_canvas.create_window(
            (0, 0), window=self.thumb_inner, anchor="nw"
        )

        self.thumb_inner.bind("<Configure>", self._on_inner_configure)
        self.thumb_canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_inner_configure(self, event=None):
        bbox = self.thumb_canvas.bbox("all")
        if bbox:
            self.thumb_canvas.configure(scrollregion=bbox)

    def _on_canvas_configure(self, event=None):
        canvas_w = self.thumb_canvas.winfo_width()
        if canvas_w > 1:
            self.thumb_canvas.itemconfigure(self.thumb_canvas_window, width=canvas_w)

        # 延迟重排，避免频繁刷新
        if self._relayout_job is not None:
            try:
                self.winfo_toplevel().after_cancel(self._relayout_job)
            except Exception:
                pass
        self._relayout_job = self.winfo_toplevel().after(150, self._relayout_if_needed)

    def _relayout_if_needed(self):
        self._relayout_job = None
        if not self._paths:
            return
        # 重新按当前排序和当前列数布局
        self.set_paths(self._paths)

    def bind_mousewheel_when_enter(self, enable: bool):
        if enable:
            self.thumb_canvas.bind("<Enter>", self._bind)
            self.thumb_canvas.bind("<Leave>", self._unbind)
        else:
            self._unbind()

    def _bind(self, event=None):
        self.thumb_canvas.bind_all("<MouseWheel>", self._on_wheel)
        self.thumb_canvas.bind_all("<Button-4>", self._on_wheel)
        self.thumb_canvas.bind_all("<Button-5>", self._on_wheel)

    def _unbind(self, event=None):
        try:
            self.thumb_canvas.unbind_all("<MouseWheel>")
            self.thumb_canvas.unbind_all("<Button-4>")
            self.thumb_canvas.unbind_all("<Button-5>")
        except Exception:
            pass

    def _on_wheel(self, event):
        if hasattr(event, "delta") and event.delta:
            delta_units = -1 * int(event.delta / 120)
        else:
            delta_units = 1 if event.num == 4 else -1
        self.thumb_canvas.yview_scroll(delta_units, "units")

    # ---------------- 排序 ----------------
    def set_sort_mode(self, mode: str):
        """
        设置排序方式:
        name_asc / name_desc / mtime_desc / mtime_asc / size_desc
        """
        self._sort_mode = mode or "name_asc"
        # 重新设置路径，触发刷新
        self.set_paths(self._paths)

    def _apply_sort(self, paths):
        mode = self._sort_mode or "name_asc"

        def safe_stat(p):
            try:
                st = os.stat(p)
                return st.st_mtime, st.st_size
            except Exception:
                return 0, 0

        if mode == "name_desc":
            return sorted(paths, key=lambda p: os.path.basename(p).lower(), reverse=True)

        if mode == "mtime_desc":
            return sorted(paths, key=lambda p: safe_stat(p)[0], reverse=True)

        if mode == "mtime_asc":
            return sorted(paths, key=lambda p: safe_stat(p)[0])

        if mode == "size_desc":
            return sorted(paths, key=lambda p: safe_stat(p)[1], reverse=True)

        # 默认：名称升序
        return sorted(paths, key=lambda p: os.path.basename(p).lower())

    # ---------------- selection/highlight ----------------
    def _apply_selection(self, new_index: int | None):
        old = self._selected_index
        if old is not None and 0 <= old < len(self._cell_frames_by_index):
            fr = self._cell_frames_by_index[old]
            if fr is not None:
                fr.configure(style="")

        self._selected_index = new_index

        if new_index is not None and 0 <= new_index < len(self._cell_frames_by_index):
            fr = self._cell_frames_by_index[new_index]
            if fr is not None:
                style_name = "Gallery.Selected.TFrame"
                style = ttk.Style()
                style.configure(
                    style_name,
                    borderwidth=2,
                    relief="solid",
                    bordercolor="#1e90ff",
                    padding=2,
                )
                fr.configure(style=style_name)

    # ---------------- public ----------------
    def set_paths(self, paths):
        self._paths = list(paths or [])
        self._stop_job()

        self._render_token += 1
        token = self._render_token

        # 排序后的显示列表
        self._display_paths = self._apply_sort(self._paths)

        for w in self.thumb_inner.winfo_children():
            w.destroy()

        n = len(self._display_paths)
        self._thumb_labels_by_index = [None] * n
        self._cell_frames_by_index = [None] * n
        self._thumb_refs = []
        self._render_index = 0
        self._selected_index = None

        size = int(self.thumb_size_var.get())
        self._cols = self._calc_cols(size)

        # 占位图
        placeholder = Image.new("RGB", (size, size), "#d9d9d9")
        placeholder_tk = ImageTk.PhotoImage(placeholder)
        self._thumb_refs.append(placeholder_tk)

        thumb_pad_x = 10
        thumb_pad_y = 12
        fname_pad_y = 4
        wrap_len = size + 50

        for idx, path in enumerate(self._display_paths):
            row = idx // self._cols
            col = idx % self._cols
            fname = os.path.basename(path)

            cell = ttk.Frame(self.thumb_inner, style="")
            cell.grid(
                row=row,
                column=col,
                padx=thumb_pad_x // 2,
                pady=thumb_pad_y // 2,
                sticky="n",
            )

            lbl_img = ttk.Label(cell, image=placeholder_tk)
            lbl_img.image = placeholder_tk
            lbl_img.pack()

            lbl_name = ttk.Label(
                cell, text=fname, wraplength=wrap_len, justify="center"
            )
            lbl_name.pack(pady=(fname_pad_y, 0))

            # 点击：选中 + 打开
            def _on_click(e, p=path, i=idx):
                self._apply_selection(i)
                self.on_open(p)

            for w in (cell, lbl_img, lbl_name):
                w.bind("<Button-1>", _on_click)

            self._thumb_labels_by_index[idx] = lbl_img
            self._cell_frames_by_index[idx] = cell

        for c in range(self._cols):
            self.thumb_inner.grid_columnconfigure(c, weight=1)

        # 延迟渲染
        self._job = self.winfo_toplevel().after(
            10, lambda: self._render_batch(size, token)
        )

    def _calc_cols(self, size: int):
        canvas_w = self.thumb_canvas.winfo_width()
        if canvas_w <= 1:
            canvas_w = 320
        card_w_est = size + 80
        return max(1, canvas_w // card_w_est)

    def _stop_job(self):
        if self._job is not None:
            try:
                self.winfo_toplevel().after_cancel(self._job)
            except Exception:
                pass
        self._job = None

    def _render_batch(self, size: int, token: int):
        # token 失效则停止
        if token != self._render_token:
            self._job = None
            return

        # 缩略图尺寸变化则停止
        if int(self.thumb_size_var.get()) != int(size):
            self._job = None
            return

        if self._render_index >= len(self._display_paths):
            self._job = None
            return

        end = min(len(self._display_paths), self._render_index + self._render_batch_size)

        for i in range(self._render_index, end):
            path = self._display_paths[i]
            lbl_img = self._thumb_labels_by_index[i]
            if lbl_img is None:
                continue

            abs_path = os.path.abspath(path)
            key = (abs_path, int(size))  # 缓存 key 使用绝对路径，避免重复/冲突

            tk_img = self._cache.get(key)
            if tk_img is None:
                try:
                    img = Image.open(abs_path)
                    img.thumbnail((size, size), Image.Resampling.LANCZOS)
                    tk_img = ImageTk.PhotoImage(img)
                    self._cache[key] = tk_img
                except Exception as e:
                    print(
                        f"[ImageGallery] failed to open: {path}\n"
                        f"  abs={abs_path}\n"
                        f"  key={key}\n"
                        f"  error={repr(e)}"
                    )
                    blank = Image.new("RGB", (size, size), "#cccccc")
                    tk_img = ImageTk.PhotoImage(blank)
                    self._cache[key] = tk_img

            lbl_img.configure(image=tk_img)
            lbl_img.image = tk_img
            self._thumb_refs.append(tk_img)

        self._render_index = end

        # 继续下一批
        self._job = self.winfo_toplevel().after(
            10, lambda: self._render_batch(size, token)
        )