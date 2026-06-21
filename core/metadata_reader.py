import json
import codecs
from PIL import Image


def _try_json_string_unescape(s: str) -> str:
    try:
        return json.loads(f'"{s}"')
    except Exception:
        return s


def decode_text(text):
    """
    尽力修复 PNG 元数据中可能出现的 Unicode 转义/乱码情况。
    与你原脚本 decode_text 保持一致。
    """
    if text is None:
        return ""

    if not isinstance(text, str):
        if isinstance(text, (bytes, bytearray)):
            for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "big5", "latin1", "cp1252"):
                try:
                    return text.decode(enc)
                except Exception:
                    pass
            return str(text)
        text = str(text)

    s = text

    # 1) 尝试把 \uXXXX 这种做一次转义解码
    try:
        s = codecs.decode(s, "unicode_escape")
    except Exception:
        pass

    # 2) 双重转义：\\u4e2d\\u6587
    if "\\u" in s or "\\U" in s:
        s = _try_json_string_unescape(s)

    # 3) 常见“拉丁1乱码”启发式回退（非保证，只是尽力）
    suspicious_markers = ("Ã", "Â", "ä", "å", "æ", "ç", "È", "é", "ê", "ë", "ì", "í", "î", "ï", "ð", "ñ", "ò")
    if any(m in s for m in suspicious_markers):
        for enc in ("utf-8", "utf-8-sig", "gb18030", "gbk", "cp936", "big5"):
            try:
                b = s.encode("latin1", errors="strict")
                s3 = b.decode(enc, errors="strict")
                if any("\u4e00" <= ch <= "\u9fff" for ch in s3):
                    s = s3
                    break
            except Exception:
                continue

    return s


def pretty_json(text):
    if not text:
        return ""
    s = decode_text(text).strip()
    if not s:
        return ""
    try:
        obj = json.loads(s)
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except Exception:
        return s


def find_first_non_empty(d, keys):
    for k in keys:
        v = d.get(k, "")
        if v is not None and str(v).strip() != "":
            return v
    return ""


class MetadataHandler:
    @staticmethod
    def parse_parameters(params_str):
        positive = ""
        negative = ""
        extra = ""

        params_str = decode_text(params_str)
        if not params_str:
            return positive, negative, extra

        params_str = params_str.replace("\r\n", "\n").replace("\r", "\n")
        lines = params_str.split("\n")

        # 正向：取第一条非空
        for ln in lines:
            if ln.strip():
                positive = ln.strip()
                break

        # negative：找 "Negative prompt:"
        for i, line in enumerate(lines):
            if line.startswith("Negative prompt:"):
                negative = line[len("Negative prompt:"):].strip()
                extra = "\n".join(lines[i + 1:]).strip()
                break
        else:
            # 没找到 negative，则其余当 extra
            if len(lines) > 1:
                extra = "\n".join(lines[1:]).strip()

        return positive, negative, extra

    @staticmethod
    def load(filepath):
        img = Image.open(filepath)
        if img.format != "PNG":
            raise ValueError("仅支持 PNG 格式")

        info = img.info or {}

        parameters = find_first_non_empty(info, ["parameters", "sd_parameters", "SD parameters"])
        prompt = find_first_non_empty(info, ["prompt", "positive_prompt", "sd_prompt", "positive", "text"])
        negative_prompt = find_first_non_empty(info, ["negative_prompt", "negative", "negativePrompt"])
        workflow = find_first_non_empty(info, ["workflow", "comfyui_workflow", "comfy_workflow", "sd_workflow"])

        pos_from_params, neg_from_params, extra = MetadataHandler.parse_parameters(parameters)

        pos_final = decode_text(prompt).strip() if str(prompt).strip() else pos_from_params.strip()
        neg_final = decode_text(negative_prompt).strip() if str(negative_prompt).strip() else neg_from_params.strip()
        wf_final = decode_text(workflow).strip()
        extra_final = decode_text(extra).strip()

        # 右侧展示：返回全部原始info字段（尽力解码）
        raw_meta = {}
        for k, v in info.items():
            try:
                raw_meta[k] = decode_text(v)
            except Exception:
                raw_meta[k] = str(v)

        return pos_final, neg_final, wf_final, extra_final, raw_meta
