# Seedream 5.0 Pro 图片测试

## 配置

附带脚本使用 Python 3 标准库，无需安装 SDK。密钥读取 `ARK_API_KEY`；模型读取 `SEEDREAM_MODEL`；地址读取 `SEEDREAM_BASE_URL`。读取顺序为当前环境变量优先，其次指定的环境文件。不会 `source` 或执行环境文件。

环境文件选择顺序：显式 `--env-file`，环境变量 `PROMPT_FINDER_ENV_FILE`，Skill 根目录可选的 `local-config.json` 中 `env_file`。`local-config.json` 只存本机环境文件的绝对路径，不存密钥；移植 Skill 时不要打包这个本机配置。路径失效时修复路径或改用环境变量，不到无关目录搜索密钥。

国内默认地址为 `https://ark.cn-beijing.volces.com/api/v3`，模型为 `doubao-seedream-5-0-pro-260628`。BytePlus 应使用自己账号对应地址及 `dola-seedream-5-0-pro-260628`，不能混用国内密钥。脚本限制官方地址与已知 Pro 模型；如官方更新或使用专属 endpoint，先核实其确实为 5.0 Pro，再更新脚本中配对配置。不要偷偷降级为 Lite/4.x。

## 调用

以下示意路径需要换成实际绝对路径，`<skill-dir>` 是本 SKILL.md 所在目录。不要把带密钥的命令放入聊天。

先检查配置，完全离线、不生图、不测试鉴权：

```bash
python3 <skill-dir>/scripts/seedream_generate.py --check
```

把本次发送的完整提示词写入 UTF-8 文件；图片必须是用户这次上传并已查看的本地文件。准备请求而不发送：

```bash
python3 <skill-dir>/scripts/seedream_generate.py --prompt-file /absolute/case/prompt-seedream.txt --image /absolute/input/photo.png --output-dir /absolute/case/test-001 --dry-run
```

实际生成，删去 `--dry-run`：

```bash
python3 <skill-dir>/scripts/seedream_generate.py --prompt-file /absolute/case/prompt-seedream.txt --image /absolute/input/photo.png --output-dir /absolute/case/test-001
```

多图明确需要时按角色顺序重复 `--image`，提示词中的「图1/图2」与顺序相同。脚本接收 PNG/JPEG/WebP；其他格式应在本地转成 PNG/JPEG，保留原文件，不能只改扩展名。默认 `--size 2K`，也可给 `1K` 或符合模型约束的 `宽x高`。默认保留 API 的 AI 水印（`--watermark true`）；用户要求无可见水印时可传 `false`。

请求为 `/images/generations` 的一次非流式 POST，携带 `model`、`prompt`、`image`、`size`、`output_format=png`、`response_format=b64_json`、`stream=false` 和 `watermark`。默认不启用组图、联网搜索或多图层。图像文件直接编码在请求中，不经第三方托管。

## 结果与异常

脚本在输出目录保存 `request-summary.json`（发送文本、文件路径和摘要，不含 Base64 或密钥）、`status.json` 及成功时的 `result.png`/`result.jpg`。输出目录已含实际请求记录时拒绝重复生成，避免误计费；新一次用户要求的测试使用新目录。

- `--check` 或 `--dry-run` 成功仅说明本地配置/请求可以准备，不代表接口鉴权成功或已经生成。
- 网络/超时：请求可能已被服务器接受，状态为 `unknown`；不自动重新 POST。
- HTTP 错误：记录状态码、错误类型和可用的请求 ID。401/403 检查账号密钥和模型权限；429 等待后由用户决定是否重试；参数错误按官方文档修正；内容拒绝按规则处理，不能通过换词或模型绕过。
- 图片 URL 下载失败：`result-source.json` 保留已生成图片的地址，仅恢复该地址下载，禁止再次生图。下载不得携带 API 认证头。URL 有有效期，应及时保存。
- 图片响应无法解析或返回的模型不是目标 Pro：保留状态和响应模型信息，不把它说成测试成功，不自动再发请求。

脚本成功后必须实际查看结果图，再对照原效果判断。图片显示优先使用本地文件绝对路径。

## 接口依据

核对时间：2026-09-16。API 会更新；模型不存在、参数改变时重新查官方文档，不能猜新模型 ID。

- [火山方舟图片生成接口](https://www.volcengine.com/docs/82379/1541523)
- [BytePlus 官方图片生成教程](https://docs.byteplus.com/api/docs/ModelArk/1824121)：可核对 Pro 的图生图、Base64 返回、PNG 输出及 1K/2K 规格。
- BytePlus 的 `dola-` 前缀不用于国内服务。
