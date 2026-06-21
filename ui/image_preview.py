# ui/image_preview.py
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk


class ImagePreview(ttk.Frame):
    def __init__(self, master, *, get_scale_default, on_render_done=None, **kwargs):
        super().__init__(master, **kwargs)
        self.get_scale_default = get_scale_default
        self.on_render_done = on_render_done

        self.preview_canvas = tk.Canvas(self, bg="#666666", highlightthickness=0)
        self.preview_canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.base_image = None
        self.display_image = None

        self.preview_scale = float(self.get_scale_default())
        self._auto_fit = True

        self.preview_img_item = None

        self._render_debounce_job = None
        self._pending_render = False

        self.preview_canvas.bind("<Configure>", self._on_canvas_configure)

        self.preview_canvas.bind("<MouseWheel>", self.on_wheel)
        self.preview_canvas.bind("<Button-4>", self.on_wheel)
        self.preview_canvas.bind("<Button-5>", self.on_wheel)
        self.preview_canvas.bind("<Double-Button-1>", self.reset_zoom)

        self._preview_has_focus = False
        self.preview_canvas.bind("<Enter>", lambda e: setattr(self, "_preview_has_focus", True))
        self.preview_canvas.bind("<Leave>", lambda e: setattr(self, "_preview_has_focus", False))

        # 拖拽（保持你原逻辑的简单版本）
        self.preview_canvas.bind("<Button-1>", self._on_press)
        self.preview_canvas.bind("<B1-Motion>", self._on_drag)
        self._drag_start = None
        self._drag_orig_img_pos = None

    def set_image(self, pil_image, scale=None):
        self.base_image = pil_image.convert("RGBA") if pil_image else None

        if scale is None:
            self._auto_fit = True
        else:
            self.preview_scale = float(scale)
            self._auto_fit = False

        # 关键：不直接 render；等 Canvas 尺寸有效后由 Configure 触发渲染
        self._pending_render = True
        self._request_render()

    def get_has_focus(self):
        return self._preview_has_focus

    def _canvas_size_valid(self):
        cw = self.preview_canvas.winfo_width()
        ch = self.preview_canvas.winfo_height()
        return cw >= 2 and ch >= 2

    def _canvas_fit_scale(self):
        if self.base_image is None:
            return float(self.get_scale_default())

        cw = self.preview_canvas.winfo_width()
        ch = self.preview_canvas.winfo_height()
        bw, bh = self.base_image.size

        # 留一点边距避免贴边
        margin = 0.98
        sx = (cw / bw) * margin
        sy = (ch / bh) * margin
        return max(0.01, min(sx, sy))

    def _request_render(self):
        if self._render_debounce_job is not None:
            try:
                self.after_cancel(self._render_debounce_job)
            except Exception:
                pass

        self._render_debounce_job = self.after(50, self._do_render_if_needed)

    def _do_render_if_needed(self):
        self._render_debounce_job = None
        if not self._pending_render:
            return
        if not self._canvas_size_valid():
            # 尺寸还没就绪：继续等
            self._request_render()
            return

        self._pending_render = False
        if self._auto_fit:
            self.preview_scale = self._canvas_fit_scale()
        self.render()

    def _on_canvas_configure(self, event=None):
        # 画布尺寸变化：如果处于 auto-fit，就重绘；否则不强制缩放
        if self.base_image is None:
            return
        if not self._canvas_size_valid():
            return

        if self._auto_fit:
            self._pending_render = True
            self._request_render()
        else:
            # 手动缩放模式：只重绘一次也行；一般不需要。这里保持不重绘。
            pass

    def on_wheel(self, event):
        if self.base_image is None:
            return

        # 滚轮 => 用户控制缩放，退出 auto-fit
        self._auto_fit = False

        # Windows: event.delta；Linux: Button-4/5
        delta = event.delta if hasattr(event, "delta") and event.delta else (120 if event.num == 4 else -120)
        if delta > 0:
            self.preview_scale *= 1.12
        else:
            self.preview_scale /= 1.12

        self.preview_scale = max(0.05, min(self.preview_scale, 50.0))
        self._pending_render = True
        self._request_render()

    def reset_zoom(self, event=None):
        self._auto_fit = True
        self._pending_render = True
        self._request_render()

    def render(self):
        if self.base_image is None:
            return

        w, h = self.base_image.size
        new_w = max(1, int(w * self.preview_scale))
        new_h = max(1, int(h * self.preview_scale))

        resized = self.base_image.resize((new_w, new_h), Image.Resampling.LANCZOS)
        self.display_image = ImageTk.PhotoImage(resized)

        self.preview_canvas.delete("all")

        cw = max(self.preview_canvas.winfo_width(), 1)
        ch = max(self.preview_canvas.winfo_height(), 1)
        cx = cw // 2
        cy = ch // 2

        self.preview_img_item = self.preview_canvas.create_image(
            cx, cy, image=self.display_image, anchor=tk.CENTER
        )

        if self.on_render_done:
            self.on_render_done()

    def _on_press(self, event):
        if self.base_image is None or not self.preview_img_item:
            return
        self._drag_start = (event.x, event.y)
        coords = self.preview_canvas.coords(self.preview_img_item)
        if len(coords) >= 2:
            self._drag_orig_img_pos = (coords[0], coords[1])
        else:
            self._drag_orig_img_pos = (event.x, event.y)

    def _on_drag(self, event):
        if self.base_image is None or not self.preview_img_item:
            return
        if self._drag_start is None or self._drag_orig_img_pos is None:
            return

        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        newx = self._drag_orig_img_pos[0] + dx
        newy = self._drag_orig_img_pos[1] + dy
        self.preview_canvas.coords(self.preview_img_item, newx, newy)