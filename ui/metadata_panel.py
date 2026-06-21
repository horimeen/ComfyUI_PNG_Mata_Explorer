# ui/metadata_panel.py
import tkinter as tk
from tkinter import ttk


class MetadataPanel(ttk.Frame):
    def __init__(self, master, *, on_save, on_reload, **kwargs):
        super().__init__(master, **kwargs)

        paned = ttk.PanedWindow(self, orient=tk.VERTICAL)
        paned.pack(fill=tk.BOTH, expand=True)

        # ---------- 上半：信息区 ----------
        info_grp = ttk.Frame(paned)
        ttk.Label(
            info_grp,
            text="图片信息（文件/尺寸/PNG 元数据字段摘要）"
        ).grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))

        info_text_wrap = ttk.Frame(info_grp)
        info_text_wrap.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        info_grp.grid_rowconfigure(1, weight=1)
        info_grp.grid_columnconfigure(0, weight=1)

        self.info_text = tk.Text(info_text_wrap, wrap=tk.WORD, height=12)
        info_scroll = ttk.Scrollbar(info_text_wrap, orient=tk.VERTICAL, command=self.info_text.yview)
        self.info_text.configure(yscrollcommand=info_scroll.set)

        self.info_text.grid(row=0, column=0, sticky="nsew")
        info_text_wrap.grid_rowconfigure(0, weight=1)
        info_text_wrap.grid_columnconfigure(0, weight=1)

        info_scroll.grid(row=0, column=1, sticky="ns")

        self.info_text.configure(state=tk.DISABLED)

        # ---------- 下半：编辑区 ----------
        meta_grp = ttk.Frame(paned)
        ttk.Label(
            meta_grp,
            text="元数据编辑（保存覆盖原图）"
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(6, 2))

        meta_grp.grid_columnconfigure(0, weight=1)

        # 关键：把三个可拖拽区域放进一个内层垂直 PanedWindow
        editor_area = ttk.Frame(meta_grp)
        editor_area.grid(row=1, column=0, sticky="nsew", padx=10, pady=(4, 8))
        meta_grp.grid_rowconfigure(1, weight=1)
        editor_area.grid_rowconfigure(0, weight=1)
        editor_area.grid_columnconfigure(0, weight=1)

        inner_paned = ttk.PanedWindow(editor_area, orient=tk.VERTICAL)
        inner_paned.grid(row=0, column=0, sticky="nsew")

        def make_labeled_text_box(parent, label, height=6):
            wrapper = ttk.Frame(parent)
            ttk.Label(wrapper, text=label).pack(anchor="w", padx=10, pady=(8, 0))

            box = ttk.Frame(wrapper)
            box.pack(fill="both", expand=True, padx=10, pady=(4, 8))
            box.grid_rowconfigure(0, weight=1)
            box.grid_columnconfigure(0, weight=1)

            txt = tk.Text(box, wrap=tk.WORD, height=height)
            scr = ttk.Scrollbar(box, orient=tk.VERTICAL, command=txt.yview)
            txt.configure(yscrollcommand=scr.set)

            txt.grid(row=0, column=0, sticky="nsew")
            scr.grid(row=0, column=1, sticky="ns")

            return wrapper, txt

        # 三段：正向 / 负向 / 工作流（均可拖拽分隔）
        pos_frame, self.txt_pos = make_labeled_text_box(inner_paned, "正向提示词:", height=6)
        neg_frame, self.txt_neg = make_labeled_text_box(inner_paned, "负向提示词:", height=4)
        wf_frame, self.txt_wf = make_labeled_text_box(inner_paned, "工作流（ComfyUI JSON）:", height=10)

        inner_paned.add(pos_frame, weight=1)
        inner_paned.add(neg_frame, weight=1)
        inner_paned.add(wf_frame, weight=1)

        # 最底部按钮：固定高度，不参与拖拽（从而“整体高度不变”且“此消彼长”发生在三个框之间）
        btn_frame = ttk.Frame(meta_grp)
        btn_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 8))
        btn_frame.grid_columnconfigure(0, weight=1)

        ttk.Button(
            btn_frame,
            text="💾 保存到原图（覆盖）",
            command=on_save
        ).pack(side=tk.LEFT)

        ttk.Button(
            btn_frame,
            text="加载当前文件",
            command=on_reload
        ).pack(side=tk.LEFT, padx=8)

        # 让下半拖拽时分配空间更明确
        paned.add(info_grp, weight=2)
        paned.add(meta_grp, weight=3)

        self._paned = paned
        self._inner_paned = inner_paned

    # ---------------- 对外接口：main_window.py 会调用 ----------------
    def set_info_text(self, text: str):
        self.info_text.configure(state=tk.NORMAL)
        self.info_text.delete("1.0", tk.END)
        self.info_text.insert("1.0", text or "")
        self.info_text.configure(state=tk.DISABLED)

    def set_fields(self, pos: str, neg: str, wf_pretty: str):
        self.txt_pos.delete("1.0", tk.END)
        self.txt_pos.insert("1.0", pos or "")

        self.txt_neg.delete("1.0", tk.END)
        self.txt_neg.insert("1.0", neg or "")

        self.txt_wf.delete("1.0", tk.END)
        self.txt_wf.insert("1.0", wf_pretty or "")

    def get_fields(self):
        pos = self.txt_pos.get("1.0", tk.END)
        neg = self.txt_neg.get("1.0", tk.END)
        wf_edited = self.txt_wf.get("1.0", tk.END)
        return pos, neg, wf_edited