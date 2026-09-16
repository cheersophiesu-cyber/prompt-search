# prompt-search

找提示词小工具：从图片效果帖、社交媒体或教程链接追溯同款效果的提示词，核验来源和复现反馈，并支持用用户照片进行 Seedream 5.0 Pro 测试。

## 功能

- 从原帖正文、配图、评论及关联教程查找提示词。
- 区分作者原词、同款教程原词和适配稿，说明证据强度与必要条件。
- 分别保存原始提示词、Seedream 适配版和案例记录，便于继续测试。
- 收到测试图片后，使用 Seedream 5.0 Pro 生成一张结果并检查效果。

## 安装

将本仓库克隆到 Codex 的 skills 目录，文件夹名称保持为 `prompt-search`：

```bash
git clone https://github.com/cheersophiesu-cyber/prompt-search.git "${CODEX_HOME:-$HOME/.codex}/skills/prompt-search"
```

如果目标目录已存在，请先检查现有内容。

## 使用

在支持加载该 skill 的 Codex 会话中调用：

```text
$prompt-search 帮我查找这个效果的提示词：https://示例效果帖链接
```

收到检索结果后，可上传一张照片继续测试。检索需要可用的搜索或浏览器工具；某些平台的评论需要登录才能查看。

## 图片测试配置

附带脚本仅使用 Python 3 标准库。找提示词本身不需要生图密钥；调用 Seedream 时需要自行配置火山方舟或 BytePlus 账号及模型权限。

脚本读取以下环境变量，也支持通过 `--env-file` 或 `PROMPT_FINDER_ENV_FILE` 指定已有环境文件：

| 变量 | 用途 |
| --- | --- |
| `ARK_API_KEY` | 对应服务的 API 密钥 |
| `SEEDREAM_BASE_URL` | 对应区域的官方 API 地址；可省略以使用脚本默认地址 |
| `SEEDREAM_MODEL` | 对应区域的 Seedream 5.0 Pro 模型 ID；可省略以使用脚本默认值 |

仅检查本地配置，不联网或生成图片：

```bash
python3 scripts/seedream_generate.py --check
```

完整说明见 [Seedream 测试文档](references/seedream.md)。生成会使用用户自行配置的 API 账号额度，实际可用性以服务商当前权限和接口为准。不要把密钥提交到仓库或发送到聊天中。

## 文件

- [SKILL.md](SKILL.md)：技能入口与完整流程。
- [agents/openai.yaml](agents/openai.yaml)：Codex 界面描述与默认调用提示。
- [references/research.md](references/research.md)：来源核验与复现证据标准。
- [references/seedream.md](references/seedream.md)：图片测试配置和异常处理。
- [scripts/seedream_generate.py](scripts/seedream_generate.py)：单次 Seedream 5.0 Pro 测试脚本。

本仓库不包含本机配置、API 密钥、用户照片或检索案例。
