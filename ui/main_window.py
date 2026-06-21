# main_window.py
import os
import json
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image

# 假设你的目录结构如下，确保这些模块存在
from core.image_scanner import scan_png_files
from core.metadata_reader import MetadataHandler, pretty_json
from core.metadata_writer import MetadataWriter
from ui.image_gallery import ImageGallery
from ui.image_preview import ImagePreview
from ui.metadata_panel import MetadataPanel

# 可选拖放
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DRAG_DROP = True
except ImportError:
    DRAG_DROP = False

APP_NAME = "png_metadata_viewer_enhanced_final"
CONFIG_FILE = os.path.join(os.path.expanduser("~"), f".{APP_NAME}.json")


def load_config():
    default = {
        "last_folder": "",
        "folder_history": [],
        "thumb_size": 96,
        "preview_initial_scale": 1.0,
        "sort_mode": "name_asc",
        "window_geometry": "1600x900",  # 记录窗口大小和位置
        "left_pane_width": 360,         # 记录左侧面板宽度
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    default.update(data)
    except Exception:
        pass
    return default


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class MainWindow:
    def __init__(self):
        self.cfg = load_config()

        if DRAG_DROP:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()

        self.root.title("PNG 元数据查看器（最终整合版）")
        
        # --- 恢复上次的窗口位置和大小 ---
        self.root.geometry(self.cfg.get("window_geometry", "1600x900"))

        self.current_file = None
        self.current_folder = ""
        self.extra_params = ""
        self.raw_meta = {}

        self.thumb_size_var = tk.IntVar(value=int(self.cfg.get("thumb_size", 96)))
        self.sort_mode_var = tk.StringVar(value=self.cfg.get("sort_mode", "name_asc"))

        self._setup_ui()
        self._load_last_folder()

        if DRAG_DROP:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self.on_drop)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def _setup_ui(self):
        # 使用 PanedWindow 实现可拖动的分割条
        self.main_pane = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        # ===== 左侧区域 =====
        self.left_frame = ttk.Frame(self.main_pane, width=int(self.cfg.get("left_pane_width", 360)))
        # 注意：PanedWindow 添加组件时需要显式指定权重
        self.main_pane.add(self.left_frame, weight=1)

        top_bar = ttk.Frame(self.left_frame)
        top_bar.pack(fill=tk.X, padx=6, pady=6)

        self.folder_combo = ttk.Combobox(top_bar, state="readonly")
        self.folder_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.folder_combo.bind("<<ComboboxSelected>>", self.on_folder_combo_change)

        ttk.Button(top_bar, text="浏览", command=self.choose_folder).pack(side=tk.RIGHT, padx=3)

        thumb_ctrl = ttk.Frame(self.left_frame)
        thumb_ctrl.pack(fill=tk.X, padx=6, pady=(0, 6))

        ttk.Label(thumb_ctrl, text="缩略图大小").pack(side=tk.LEFT)

        self.gallery = ImageGallery(self.left_frame, on_open=self.load)
        self.gallery.thumb_size_var.set(int(self.thumb_size_var.get()))

        self.thumb_scale = ttk.Scale(
            thumb_ctrl, from_=64, to=220, orient=tk.HORIZONTAL,
            variable=self.thumb_size_var,
            command=self.on_thumb_scale_moving
        )
        self.thumb_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        self.thumb_label = ttk.Label(
            thumb_ctrl, text=f"{self.thumb_size_var.get()} px", width=10, anchor="e"
        )
        self.thumb_label.pack(side=tk.RIGHT)

        # 排序控制
        sort_ctrl = ttk.Frame(self.left_frame)
        sort_ctrl.pack(fill=tk.X, padx=6, pady=(0, 6))
        ttk.Label(sort_ctrl, text="排序").pack(side=tk.LEFT)

        sort_values = [
            ("name_asc", "文件名升序"),
            ("name_desc", "文件名降序"),
            ("mtime_desc", "修改时间降序"),
            ("mtime_asc", "修改时间升序"),
            ("size_desc", "文件大小降序"),
        ]
        self._sort_mode_map = {label: mode for mode, label in sort_values}
        self._sort_label_map = {mode: label for mode, label in sort_values}

        self.sort_combo = ttk.Combobox(
            sort_ctrl, state="readonly", values=list(self._sort_label_map.values()), width=14
        )
        self.sort_combo.set(self._sort_label_map.get(self.sort_mode_var.get(), "文件名升序"))
        self.sort_combo.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        self.sort_combo.bind("<<ComboboxSelected>>", self.on_sort_change)

        ttk.Button(self.left_frame, text="刷新列表", command=self.refresh_list).pack(fill=tk.X, padx=6, pady=(0, 6))

        self.gallery.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.gallery.bind_mousewheel_when_enter(True)
        self.gallery.set_sort_mode(self.sort_mode_var.get())

        # ===== 中间区域 (预览) =====
        center = ttk.Frame(self.main_pane, width=780)
        self.main_pane.add(center, weight=3)

        preview_frame = ttk.LabelFrame(center, text="图片预览（鼠标滚轮缩放，双击重置）")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        self.preview = ImagePreview(
            preview_frame,
            get_scale_default=lambda: float(self.cfg.get("preview_initial_scale", 1.0))
        )
        self.preview.pack(fill=tk.BOTH, expand=True)

        # ===== 右侧区域 (元数据) =====
        right = ttk.Frame(self.main_pane, width=460)
        self.main_pane.add(right, weight=1)

        self.panel = MetadataPanel(right, on_save=self.save, on_reload=self.reload_current)
        self.panel.pack(fill=tk.BOTH, expand=True)

        # 强制刷新布局，确保 PanedWindow 识别初始宽度
        self.root.update_idletasks()
        self.left_frame.configure(width=int(self.cfg.get("left_pane_width", 360)))

    # --- 内部功能方法 ---

    def on_thumb_scale_moving(self, event=None):
        self.thumb_label.config(text=f"{self.thumb_size_var.get()} px")
        self.cfg["thumb_size"] = int(self.thumb_size_var.get())
        save_config(self.cfg)
        self.gallery.thumb_size_var.set(int(self.thumb_size_var.get()))

        if getattr(self, "thumb_pending_after", None) is not None:
            try:
                self.root.after_cancel(self.thumb_pending_after)
            except:
                pass
        self.thumb_pending_after = self.root.after(180, self.refresh_list)

    def on_sort_change(self, event=None):
        label = self.sort_combo.get()
        mode = self._sort_mode_map.get(label, "name_asc")
        self.sort_mode_var.set(mode)
        self.cfg["sort_mode"] = mode
        save_config(self.cfg)
        self.gallery.set_sort_mode(mode)

    def choose_folder(self):
        d = filedialog.askdirectory(initialdir=self.current_folder or self.cfg.get("last_folder") or None)
        if d:
            self.set_folder(d)

    def _load_last_folder(self):
        last = self.cfg.get("last_folder", "")
        history = self.cfg.get("folder_history", [])
        combos = []
        if last and os.path.isdir(last):
            combos.append(last)
        for p in history:
            if p and os.path.isdir(p) and p not in combos:
                combos.append(p)

        self.folder_combo["values"] = combos
        if combos:
            self.folder_combo.set(combos[0])
            self.set_folder(combos[0])

        self.thumb_size_var.set(int(self.cfg.get("thumb_size", 96)))
        self.thumb_label.config(text=f"{self.thumb_size_var.get()} px")
        self.gallery.thumb_size_var.set(int(self.thumb_size_var.get()))

        mode = self.cfg.get("sort_mode", "name_asc")
        self.sort_mode_var.set(mode)
        if hasattr(self, "_sort_label_map") and hasattr(self, "sort_combo"):
            self.sort_combo.set(self._sort_label_map.get(mode, "文件名升序"))
        self.gallery.set_sort_mode(mode)

    def set_folder(self, folder):
        self.current_folder = folder
        self.folder_combo.set(folder)
        history = list(self.cfg.get("folder_history", []))
        if folder in history: history.remove(folder)
        history.insert(0, folder)
        history = history[:30]
        self.cfg["last_folder"] = folder
        self.cfg["folder_history"] = history
        self.cfg["thumb_size"] = int(self.thumb_size_var.get())
        save_config(self.cfg)

        values = [folder] + [p for p in history if p != folder]
        self.folder_combo["values"] = values
        self.refresh_list()

    def on_folder_combo_change(self, event=None):
        folder = self.folder_combo.get()
        if folder and os.path.isdir(folder):
            self.set_folder(folder)

    def refresh_list(self):
        folder = self.current_folder or self.folder_combo.get()
        if folder and os.path.isdir(folder):
            paths = scan_png_files(folder)
            self.gallery.set_paths(paths)

    def on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        if not files: return
        path = files[0].strip("{").strip("}")
        
        if os.path.isdir(path):
            self.set_folder(path)
        elif path.lower().endswith(".png"):
            self.load(path)
        else:
            img_extensions = ('.jpg', '.jpeg', '.bmp', '.webp', '.tiff', '.jfif')
            if path.lower().endswith(img_extensions):
                try:
                    base, _ = os.path.splitext(path)
                    new_path = base + ".png"
                    img = Image.open(path)
                    img.save(new_path, "PNG")
                    self.load(new_path)
                except Exception as e:
                    try: self.load(path)
                    except: messagebox.showerror("错误", f"转换失败: {e}")
            else:
                try: self.load(path)
                except: pass

    def show_info(self, path, raw_meta):
        try:
            st = os.stat(path)
            size_kb = st.st_size / 1024
            mtime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
        except:
            size_kb, mtime = 0, ""

        try:
            img = Image.open(path)
            width, height = img.size
            fmt = img.format
        except:
            width, height, fmt = 0, 0, ""

        lines = [f"文件名: {os.path.basename(path)}", f"路径: {path}", f"格式: {fmt}", 
                 f"尺寸: {width} x {height}", f"文件大小: {size_kb:.1f} KB", f"修改时间: {mtime}", "", "PNG 元数据字段:"]
        
        for k, v in raw_meta.items():
            v_str = str(v)[:1200] + ("..." if len(str(v)) > 1200 else "")
            lines.append(f"\n[{k}]")
            lines.append(v_str)

        self.panel.set_info_text("\n".join(lines))

    def load(self, path):
        try:
            pos, neg, wf, extra, raw_meta = MetadataHandler.load(path)
            self.current_file = path
            self.extra_params = extra
            self.raw_meta = raw_meta
            self.show_info(path, raw_meta)
            self.panel.set_fields(pos, neg, pretty_json(wf))
            self.preview.set_image(Image.open(path), scale=None)
            self.root.title(f"PNG 元数据查看器 - {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("加载失败", str(e))

    def reload_current(self):
        if self.current_file and os.path.exists(self.current_file):
            self.load(self.current_file)

    def save(self):
        if not self.current_file:
            messagebox.showwarning("提示", "请先打开一张 PNG 图片")
            return
        pos, neg, wf_edited = self.panel.get_fields()
        try:
            MetadataWriter.save(self.current_file, pos, neg, wf_edited, self.extra_params)
            messagebox.showinfo("成功", f"已保存：\n{self.current_file}")
            self.load(self.current_file)
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def on_close(self):
        # --- 在关闭时保存当前布局 ---
        try:
            self.cfg["window_geometry"] = self.root.geometry()
            self.cfg["left_pane_width"] = self.left_frame.winfo_width()
            self.cfg["last_folder"] = self.current_folder
            self.cfg["thumb_size"] = int(self.thumb_size_var.get())
            self.cfg["sort_mode"] = self.sort_mode_var.get()
            save_config(self.cfg)
        except Exception:
            pass
        self.root.destroy()

    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = MainWindow()
    app.run()