from PIL import Image, PngImagePlugin
from core.metadata_reader import decode_text


class MetadataWriter:
    @staticmethod
    def save(filepath, positive, negative, workflow, extra_params):
        img = Image.open(filepath)
        if img.format != "PNG":
            raise ValueError("仅支持 PNG 格式")

        old_info = img.info.copy()
        new_info = PngImagePlugin.PngInfo()

        # 保留除这几个业务键之外的其它文本块
        preserve_keys = [k for k in old_info.keys() if k not in (
            "parameters", "prompt", "negative_prompt", "workflow",
            "comfyui_workflow", "comfy_workflow", "sd_workflow",
            "sd_parameters", "positive_prompt", "negative"
        )]

        for key in preserve_keys:
            try:
                new_info.add_text(key, str(old_info[key]))
            except Exception:
                pass

        positive = decode_text(positive).strip()
        negative = decode_text(negative).strip()
        workflow = decode_text(workflow).strip()
        extra_params = decode_text(extra_params).strip()

        params = positive
        if negative:
            params += f"\nNegative prompt: {negative}"
        if extra_params:
            params += f"\n{extra_params}"

        # 写入业务字段
        new_info.add_text("parameters", params)
        new_info.add_text("prompt", positive)
        new_info.add_text("negative_prompt", negative)
        if workflow:
            new_info.add_text("workflow", workflow)

        img.save(filepath, format="PNG", pnginfo=new_info)
