import customtkinter as ctk
import geopandas as gpd
import os
import json
import shutil
import sys
import threading
import zipfile
from tkinter import filedialog, messagebox

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".shp_converter", "config.json")


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(data: dict):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

gpd.options.io_engine = "pyogrio"

ENCODING_OPTIONS = {
    "GBK / GB2312（国内历史数据）": "gbk",
    "UTF-8": "utf-8",
    "自动识别（根据 .cpg 文件）": None,
}

CRS_PRESETS = {
    "CGCS2000 (EPSG:4490)": "4490",
    "WGS84 (EPSG:4326)": "4326",
    "北京 1954 (EPSG:4214)": "4214",
    "西安 1980 (EPSG:4610)": "4610",
    "Web 墨卡托 (EPSG:3857)": "3857",
    "自定义...": "",
}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("SHP 坐标转换工具")
        self.geometry("620x650")
        self.resizable(False, False)

        self.selected_files = []
        self._converting = False
        self._config = load_config()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # 标题
        ctk.CTkLabel(self, text="SHP 坐标转换工具", font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(24, 4))
        ctk.CTkLabel(self, text="选择 .shp 文件，批量转换坐标系",
                     text_color="gray").pack(pady=(0, 16))

        # 文件选择区域
        file_frame = ctk.CTkFrame(self)
        file_frame.pack(fill="x", padx=24, pady=(0, 10))

        ctk.CTkLabel(file_frame, text="源文件：").pack(side="left", padx=(12, 4), pady=12)

        self.folder_entry = ctk.CTkEntry(file_frame, placeholder_text="请选择一个或多个 .shp 文件", width=370)
        self.folder_entry.pack(side="left", padx=4, pady=12)

        ctk.CTkButton(file_frame, text="浏览", width=72, command=self.browse_files).pack(side="left", padx=(4, 12))

        # 源文件编码选择区域
        enc_frame = ctk.CTkFrame(self)
        enc_frame.pack(fill="x", padx=24, pady=(0, 10))

        ctk.CTkLabel(enc_frame, text="源文件编码：").pack(side="left", padx=(12, 4), pady=12)

        saved_enc = self._config.get("source_encoding", "GBK / GB2312（国内历史数据）")
        if saved_enc not in ENCODING_OPTIONS:
            saved_enc = "GBK / GB2312（国内历史数据）"

        self.enc_menu = ctk.CTkOptionMenu(
            enc_frame,
            values=list(ENCODING_OPTIONS.keys()),
            command=lambda _: self._persist_config(),
            width=260,
        )
        self.enc_menu.set(saved_enc)
        self.enc_menu.pack(side="left", padx=(4, 12), pady=12)

        # 目标坐标系选择区域
        crs_frame = ctk.CTkFrame(self)
        crs_frame.pack(fill="x", padx=24, pady=(0, 10))

        ctk.CTkLabel(crs_frame, text="目标坐标系：").pack(side="left", padx=(12, 4), pady=12)

        saved_preset = self._config.get("last_crs_preset", "CGCS2000 (EPSG:4490)")
        saved_epsg = self._config.get("last_epsg", "4490")
        if saved_preset not in CRS_PRESETS:
            saved_preset = "自定义..."

        self.crs_menu = ctk.CTkOptionMenu(
            crs_frame,
            values=list(CRS_PRESETS.keys()),
            command=self.on_crs_preset_change,
            width=220,
        )
        self.crs_menu.set(saved_preset)
        self.crs_menu.pack(side="left", padx=(4, 12), pady=12)

        ctk.CTkLabel(crs_frame, text="或手动输入 EPSG：").pack(side="left", padx=(4, 4))

        self.epsg_entry = ctk.CTkEntry(crs_frame, width=90, placeholder_text="如 4490")
        self.epsg_entry.insert(0, saved_epsg)
        self.epsg_entry.pack(side="left", padx=(0, 12), pady=12)

        # 输出格式选择区域
        fmt_frame = ctk.CTkFrame(self)
        fmt_frame.pack(fill="x", padx=24, pady=(0, 10))

        ctk.CTkLabel(fmt_frame, text="输出格式：").pack(side="left", padx=(12, 4), pady=12)

        saved_fmt = self._config.get("output_format", "文件夹")
        self.fmt_switch = ctk.CTkSegmentedButton(
            fmt_frame,
            values=["文件夹", "ZIP 压缩包"],
            command=self.on_fmt_change,
            width=200,
        )
        self.fmt_switch.set(saved_fmt)
        self.fmt_switch.pack(side="left", padx=(4, 12), pady=12)

        self.fmt_hint = ctk.CTkLabel(fmt_frame, text="", text_color="gray", font=ctk.CTkFont(size=12))
        self.fmt_hint.pack(side="left", padx=(0, 12))
        self._update_fmt_hint(saved_fmt)

        # 进度条
        self.progress_bar = ctk.CTkProgressBar(self)
        self.progress_bar.pack(fill="x", padx=24, pady=(0, 4))
        self.progress_bar.set(0)

        self.progress_label = ctk.CTkLabel(self, text="", text_color="gray", font=ctk.CTkFont(size=12))
        self.progress_label.pack(anchor="w", padx=24)

        # 开始转换按钮
        self.convert_btn = ctk.CTkButton(self, text="开始转换", height=40,
                                         font=ctk.CTkFont(size=14, weight="bold"),
                                         command=self.start_conversion)
        self.convert_btn.pack(pady=12)

        # 日志区域
        ctk.CTkLabel(self, text="转换日志", anchor="w").pack(fill="x", padx=24)
        self.log_box = ctk.CTkTextbox(self, height=180, font=ctk.CTkFont(family="Courier", size=12))
        self.log_box.pack(fill="both", expand=True, padx=24, pady=(4, 8))
        self.log_box.configure(state="disabled")

        # 配置日志高亮 tag
        tb = self.log_box._textbox
        tb.tag_configure("crs",    foreground="#1a85cc", font=("Courier", 12, "bold"))
        tb.tag_configure("target", foreground="#e36209", font=("Courier", 12, "bold"))

        # 清空日志按钮
        ctk.CTkButton(self, text="清空日志", width=90, height=28,
                      fg_color="transparent", border_width=1,
                      command=self.clear_log).pack(anchor="e", padx=24, pady=(0, 16))

    def _update_fmt_hint(self, fmt):
        if fmt == "ZIP 压缩包":
            self.fmt_hint.configure(text="每个文件打包为同名 .zip")
        else:
            self.fmt_hint.configure(text="每个文件保存为独立文件夹")

    def on_fmt_change(self, choice):
        self._update_fmt_hint(choice)
        self._persist_config()

    def on_crs_preset_change(self, choice):
        epsg = CRS_PRESETS.get(choice, "")
        self.epsg_entry.delete(0, "end")
        if epsg:
            self.epsg_entry.insert(0, epsg)
        self._persist_config()

    def _persist_config(self):
        save_config({
            "last_crs_preset": self.crs_menu.get(),
            "last_epsg": self.epsg_entry.get().strip(),
            "output_format": self.fmt_switch.get(),
            "source_encoding": self.enc_menu.get(),
        })

    def _get_source_encoding(self):
        return ENCODING_OPTIONS.get(self.enc_menu.get())

    def browse_files(self):
        files = filedialog.askopenfilenames(
            title="选择 .shp 文件",
            filetypes=[("Shapefile", "*.shp"), ("所有文件", "*.*")]
        )
        if files:
            self.selected_files = list(files)
            display = f"已选择 {len(files)} 个文件" if len(files) > 1 else files[0]
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, display)
            self.clear_log()
            threading.Thread(target=self.show_crs_info, daemon=True).start()

    def show_crs_info(self):
        self.log(f"已选择 {len(self.selected_files)} 个文件，当前坐标系信息如下：\n{'─' * 40}")
        enc = self._get_source_encoding()
        read_kwargs = {"encoding": enc} if enc else {}
        for shp_path in self.selected_files:
            file_name = os.path.basename(shp_path)
            try:
                data = gpd.read_file(shp_path, rows=1, **read_kwargs)
                if data.crs is None:
                    self.log(f"  {file_name} — 原始坐标系：未知（缺少 .prj 文件）", tag="crs")
                else:
                    self.log(f"  {file_name} — 原始坐标系：{data.crs.to_string()}", tag="crs")
            except Exception as e:
                self.log(f"  {file_name} — 读取失败：{e}")
        self.log('─' * 40)

    def log(self, message, tag=None):
        tb = self.log_box._textbox
        self.log_box.configure(state="normal")
        start = tb.index("end-1c")
        tb.insert("end", message + "\n")
        if tag:
            tb.tag_add(tag, start, tb.index("end-1c"))
        tb.see("end")
        self.log_box.configure(state="disabled")

    def clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")
        self.progress_bar.set(0)
        self.progress_label.configure(text="")

    def start_conversion(self):
        if not self.selected_files:
            self.log("[错误] 请先选择 .shp 文件")
            return

        epsg_str = self.epsg_entry.get().strip()
        if not epsg_str.isdigit():
            self.log("[错误] EPSG 编号无效，请输入纯数字，如 4490")
            return

        self.convert_btn.configure(state="disabled", text="转换中...")
        self.progress_bar.set(0)
        self.progress_label.configure(text="")
        self._converting = True

        use_zip = self.fmt_switch.get() == "ZIP 压缩包"
        source_enc = self._get_source_encoding()
        self._persist_config()
        thread = threading.Thread(target=self.run_conversion, args=(int(epsg_str), use_zip, source_enc), daemon=True)
        thread.start()

    def run_conversion(self, target_epsg, use_zip, source_enc):
        shp_files = self.selected_files
        total = len(shp_files)

        source_dir = os.path.dirname(shp_files[0])
        parent_dir = os.path.dirname(source_dir)
        output_dir = os.path.join(parent_dir, f"转换结果_EPSG{target_epsg}")
        os.makedirs(output_dir, exist_ok=True)

        self.log(f"目标坐标系：EPSG:{target_epsg}", tag="target")
        fmt_label = "ZIP 压缩包" if use_zip else "文件夹"
        enc_label = source_enc.upper() if source_enc else "自动识别"
        self.log(f"源文件编码：{enc_label}  输出格式：{fmt_label}\n开始转换 {total} 个文件...\n{'─' * 40}")

        read_kwargs = {"encoding": source_enc} if source_enc else {}
        success, failed = 0, 0

        for i, shp_path in enumerate(shp_files, 1):
            file_name = os.path.basename(shp_path)
            base_name = os.path.splitext(file_name)[0]
            try:
                data = gpd.read_file(shp_path, **read_kwargs)

                if data.crs is None:
                    self.log(f"[跳过] {file_name} — 缺少 .prj 文件，无法识别坐标系")
                    failed += 1
                else:
                    converted = data.to_crs(epsg=target_epsg)

                    # 先保存到临时子文件夹
                    sub_dir = os.path.join(output_dir, base_name)
                    os.makedirs(sub_dir, exist_ok=True)
                    converted.to_file(os.path.join(sub_dir, file_name), encoding="utf-8")

                    if use_zip:
                        zip_path = os.path.join(output_dir, f"{base_name}.zip")
                        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                            for f in os.listdir(sub_dir):
                                zf.write(os.path.join(sub_dir, f), arcname=f)
                        shutil.rmtree(sub_dir)
                        self.log(f"[成功] {base_name}.zip")
                    else:
                        self.log(f"[成功] {file_name}")

                    success += 1

            except Exception as e:
                self.log(f"[失败] {file_name} — {e}")
                failed += 1

            progress = i / total
            self.after(0, lambda p=progress, cur=i, t=total: self._update_progress(p, cur, t))

        self.log(f"{'─' * 40}\n转换完成：成功 {success} 个，失败/跳过 {failed} 个")
        self.log(f"结果保存在：{output_dir}")
        self.after(0, self.reset_button)

    def _update_progress(self, value, current, total):
        self.progress_bar.set(value)
        self.progress_label.configure(text=f"{current} / {total}")

    def reset_button(self):
        self._converting = False
        self.convert_btn.configure(state="normal", text="开始转换")

    def _on_close(self):
        if self._converting:
            confirmed = messagebox.askyesno(
                title="确认退出",
                message="文件正在转换中，强制退出可能导致输出文件不完整。\n\n确定要退出吗？"
            )
            if not confirmed:
                return
        self.destroy()
        sys.exit(0)


if __name__ == "__main__":
    app = App()
    app.mainloop()
