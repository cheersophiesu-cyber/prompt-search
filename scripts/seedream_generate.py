#!/usr/bin/env python3
"""One Seedream 5.0 Pro edit request; secrets stay in environment/local config."""

import argparse
import base64
import binascii
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request


PROVIDERS = {
    "https://ark.cn-beijing.volces.com/api/v3": "doubao-seedream-5-0-pro-260628",
    "https://ark.ap-southeast.bytepluses.com/api/v3": "dola-seedream-5-0-pro-260628",
    "https://ark.eu-west.bytepluses.com/api/v3": "dola-seedream-5-0-pro-260628",
}
DEFAULT_BASE = "https://ark.cn-beijing.volces.com/api/v3"
ENV_KEYS = {"ARK_API_KEY", "SEEDREAM_MODEL", "SEEDREAM_BASE_URL"}
MAX_INPUT = 30 * 1024 * 1024
MAX_RESPONSE = 100 * 1024 * 1024


class GenerationError(Exception):
    def __init__(self, code, message, state="failed", **details):
        super().__init__(message)
        self.code = code
        self.state = state
        self.details = details


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward Authorization to a redirected endpoint.


def now():
    return datetime.now(timezone.utc).isoformat()


def read_env_file(path):
    result = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        if not sep or key.strip() not in ENV_KEYS:
            continue
        try:
            parts = shlex.split(value, comments=True, posix=True)
        except ValueError:
            raise GenerationError("ENV_FORMAT", "环境文件相关配置的引号格式错误。") from None
        if len(parts) > 1:
            raise GenerationError("ENV_FORMAT", "环境配置中包含未加引号的空格。")
        result[key.strip()] = parts[0] if parts else ""
    return result


def load_config(env_file=None):
    path = env_file or os.environ.get("PROMPT_FINDER_ENV_FILE")
    # Fully supplied environment settings do not depend on a stale local pointer.
    if not path and not os.environ.get("ARK_API_KEY"):
        local = Path(__file__).resolve().parents[1] / "local-config.json"
        if local.exists():
            config = json.loads(local.read_text(encoding="utf-8"))
            path = config.get("env_file")
            if path and not Path(path).expanduser().is_absolute():
                raise GenerationError("CONFIG_PATH", "env_file 必须是绝对路径。")
    values = read_env_file(Path(path).expanduser()) if path else {}
    for key in ENV_KEYS:
        if os.environ.get(key):
            values[key] = os.environ[key]
    base = values.get("SEEDREAM_BASE_URL", DEFAULT_BASE).rstrip("/")
    if base not in PROVIDERS:
        raise GenerationError("ENDPOINT", "接口地址不在已核实的官方地址中，请核对配置。")
    model = values.get("SEEDREAM_MODEL") or PROVIDERS[base]
    if model != PROVIDERS[base]:
        raise GenerationError("MODEL", "配置不是该区域已核实的 Seedream 5.0 Pro 模型。")
    key = values.get("ARK_API_KEY", "").strip()
    if not key:
        raise GenerationError("MISSING_KEY", "缺少 ARK_API_KEY；请在本机环境或环境文件配置。")
    return {"key": key, "base": base, "model": model}


def image_type(data):
    if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", ".png"
    if len(data) >= 4 and data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", ".jpg"
    if len(data) >= 16 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", ".webp"
    raise GenerationError("IMAGE_FORMAT", "图片须为可识别的 PNG、JPEG 或 WebP。")


def validate_size(size):
    if size in ("1K", "2K"):
        return
    match = re.fullmatch(r"([1-9][0-9]{0,5})x([1-9][0-9]{0,5})", size)
    if match:
        width, height = map(int, match.groups())
        if 921600 <= width * height <= 4624220 and 1 / 16 <= width / height <= 16:
            return
    raise GenerationError("SIZE", "Pro 尺寸须为 1K、2K，或符合像素数和比例限制的宽x高。")


def prepare_request(args, config):
    if not args.prompt_file or not args.image or not args.output_dir:
        raise GenerationError("INPUT", "需要 --prompt-file、--image 和 --output-dir。")
    if len(args.image) > 10:
        raise GenerationError("IMAGE_COUNT", "一次最多十张明确需要的参考图。")
    prompt = Path(args.prompt_file).expanduser().read_text(encoding="utf-8")
    if not prompt.strip():
        raise GenerationError("PROMPT", "提示词不能为空。")
    validate_size(args.size)
    images, summaries = [], []
    for filename in args.image:
        path = Path(filename).expanduser().resolve()
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_INPUT:
            raise GenerationError("IMAGE_FILE", "输入须为非空图片文件，每张不超过 30 MB。")
        data = path.read_bytes()
        if len(data) > MAX_INPUT:
            raise GenerationError("IMAGE_FILE", "输入图片超过 30 MB。")
        mime, _ = image_type(data)
        images.append("data:" + mime + ";base64," + base64.b64encode(data).decode("ascii"))
        summaries.append({"path": str(path), "mime": mime, "bytes": len(data),
                          "sha256": hashlib.sha256(data).hexdigest()})
    payload = {"model": config["model"], "prompt": prompt,
               "image": images[0] if len(images) == 1 else images,
               "size": args.size, "stream": False, "response_format": "b64_json",
               "output_format": "png", "watermark": args.watermark == "true"}
    summary = {key: value for key, value in payload.items() if key != "image"}
    summary.update({"endpoint": config["base"] + "/images/generations", "images": summaries,
                    "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    "created_at": now()})
    return payload, summary


def write_json(path, data, exclusive=False):
    # Files containing prompts or image URLs are private to this machine user.
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    fd = os.open(path, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def set_status(out, state, **fields):
    write_json(out / "status.json", {"state": state, "updated_at": now(), **fields})


def safe_token(value, secret=""):
    if not isinstance(value, str):
        return None
    if secret:
        value = value.replace(secret, "[REDACTED]")
    return re.sub(r"[^A-Za-z0-9._:\[\]-]", "", value)[:180]


def bounded_read(response):
    data = response.read(MAX_RESPONSE + 1)
    if len(data) > MAX_RESPONSE:
        raise GenerationError("RESPONSE_SIZE", "响应过大，已停止读取；不要自动重新生图。", "unknown")
    return data


def post_once(config, payload, timeout):
    req = urllib.request.Request(
        config["base"] + "/images/generations",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer " + config["key"], "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=timeout) as response:
            request_id = safe_token(response.headers.get("x-request-id"), config["key"])
            raw = bounded_read(response)
    except urllib.error.HTTPError as exc:
        request_id = safe_token(exc.headers.get("x-request-id"), config["key"])
        code = None
        try:
            body = json.loads(exc.read(65536))
            error = body.get("error", {}) if isinstance(body, dict) else {}
            if isinstance(error, dict):
                code = safe_token(error.get("code"), config["key"])
        except (ValueError, OSError):
            pass
        raise GenerationError("HTTP_ERROR", "接口返回 HTTP 错误；未自动重试。",
                              "unknown" if exc.code >= 500 else "failed",
                              http_status=exc.code, provider_code=code, request_id=request_id) from None
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError):
        raise GenerationError("NETWORK", "连接中断或超时，是否已计费未知；未自动重试。", "unknown") from None
    try:
        body = json.loads(raw)
    except (ValueError, UnicodeError):
        raise GenerationError("RESPONSE_JSON", "返回内容不是有效 JSON；未自动重试。", "unknown",
                              request_id=request_id) from None
    if not isinstance(body, dict):
        raise GenerationError("RESPONSE_SHAPE", "返回结构无法识别；未自动重试。", "unknown",
                              request_id=request_id)
    return body, request_id


def save_result(body, out, config, request_id):
    response_model = body.get("model")
    if response_model and response_model != config["model"]:
        raise GenerationError("RESPONSE_MODEL", "返回模型与请求的 Pro 模型不一致。", "unknown",
                              response_model=safe_token(response_model, config["key"]))
    items = body.get("data")
    if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict):
        raise GenerationError("EMPTY_RESULT", "未得到预期的一张图片；保留记录，不自动重试。", "unknown")
    item = items[0]
    if item.get("b64_json"):
        try:
            data = base64.b64decode(item["b64_json"], validate=True)
        except (binascii.Error, ValueError, TypeError):
            raise GenerationError("BASE64", "图片 Base64 数据无效，不自动重新生图。", "unknown") from None
    elif item.get("url"):
        url = item["url"]
        if not isinstance(url, str):
            raise GenerationError("RESULT_URL", "图片地址格式无效。", "unknown")
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise GenerationError("RESULT_URL", "图片地址须为无账户信息的 HTTPS 链接。", "unknown")
        write_json(out / "result-source.json", {"url": url, "request_id": request_id,
                                               "created_at": now()})
        try:
            # Deliberately no API credentials on the download request.
            with urllib.request.build_opener(NoRedirect()).open(url, timeout=60) as response:
                data = bounded_read(response)
        except (OSError, urllib.error.URLError, GenerationError):
            raise GenerationError("DOWNLOAD", "生成结果已返回但下载失败；请从 result-source.json 恢复下载。",
                                  "download_failed") from None
    else:
        code = item.get("error", {}).get("code") if isinstance(item.get("error"), dict) else None
        raise GenerationError("EMPTY_IMAGE", "接口未返回图片数据；未自动重试。", "unknown",
                              provider_code=safe_token(code, config["key"]))
    try:
        _, extension = image_type(data)
    except GenerationError:
        raise GenerationError("RESULT_FORMAT", "返回数据不是可识别的图片。", "unknown") from None
    result = out / ("result" + extension)
    fd = os.open(result, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)
    fields = {"result_path": str(result), "model": config["model"], "request_id": request_id,
              "response_model_confirmed": response_model == config["model"],
              "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    set_status(out, "generated", **fields)
    return fields


def execute(args):
    config = load_config(args.env_file)
    if args.check:
        return {"state": "config_ready", "model": config["model"], "base_url": config["base"],
                "key_present": True, "network_called": False, "authentication_verified": False}
    payload, summary = prepare_request(args, config)
    if args.dry_run:
        return {"state": "dry_run", "model": config["model"], "size": args.size,
                "input_count": len(args.image), "prompt_sha256": summary["prompt_sha256"],
                "network_called": False, "authentication_verified": False}
    out = Path(args.output_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    if any((out / name).exists() for name in ("status.json", "result.png", "result.jpg", "result.webp")):
        raise GenerationError("EXISTING_RUN", "目录已有测试记录；先检查状态，新的测试请使用新目录。")
    try:
        write_json(out / "request-summary.json", summary, exclusive=True)
    except FileExistsError:
        raise GenerationError("EXISTING_RUN", "此目录已提交或准备过请求；不重复生图。") from None
    request_id = None
    try:
        set_status(out, "submitting", model=config["model"])
        body, request_id = post_once(config, payload, args.timeout)
        set_status(out, "response_received", model=config["model"], request_id=request_id)
        fields = save_result(body, out, config, request_id)
        return {"state": "generated", **fields}
    except GenerationError as exc:
        details = {"request_id": request_id, **exc.details}
        set_status(out, exc.state, code=exc.code, message=str(exc), **details)
        raise
    except (OSError, ValueError, TypeError):
        error = GenerationError("LOCAL_RESULT", "结果处理或保存失败；先检查已有记录，不要重新生成。", "unknown")
        try:
            set_status(out, error.state, code=error.code, message=str(error), request_id=request_id)
        except OSError:
            pass
        raise error from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", help="已有 .env 文件路径（只读取相关变量，不执行）")
    parser.add_argument("--check", action="store_true", help="只检查配置，不联网")
    parser.add_argument("--prompt-file", help="UTF-8 提示词文件")
    parser.add_argument("--image", action="append", help="本地 PNG/JPEG/WebP，可重复指定")
    parser.add_argument("--output-dir", help="本次请求的独立输出目录")
    parser.add_argument("--size", default="2K")
    parser.add_argument("--watermark", choices=("true", "false"), default="true")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--dry-run", action="store_true", help="验证本地输入，不发送请求")
    args = parser.parse_args()
    try:
        if not 1 <= args.timeout <= 600:
            raise GenerationError("TIMEOUT", "超时应在 1 到 600 秒之间。")
        result = execute(args)
    except GenerationError as exc:
        print(json.dumps({"state": exc.state, "code": exc.code, "message": str(exc), **exc.details},
                         ensure_ascii=False), file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, AttributeError):
        print(json.dumps({"state": "failed", "code": "LOCAL_CONFIG_OR_FILE",
                          "message": "本地文件或配置无法读取，请检查路径、权限和 JSON 格式。"},
                         ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
