# 跨平台接入指南

> 核实日期：2026-10。平台路径参照同类 agent-skill 实践（含 [`WangYr-Peppa/search-playbook`](https://github.com/WangYr-Peppa/search-playbook) 的 PLATFORMS 约定）。平台格式**变动很快，使用前请以各平台官方文档为准**。

* * *

## TL;DR

1. 🎯 **`<name>/SKILL.md`（含 `name` + `description` frontmatter）正在成为跨平台事实标准** → 本包的 3 个 `SKILL.md` **几乎原样可移植**。
2. 🔑 **本包对 opencode 的真正依赖只有两处**：命令 `command/draw.md` / `illustrate.md`、以及 `seedream-qc` 里的 `@observer` 子 agent。**其余（SKILL.md + Python 脚本）平台中立。**
3. 🐍 **脚本只用 Python3 标准库 + 环境变量 `ARK_API_KEY`** → 任何能执行 shell/python 的 agent 都能用。
4. ⚠️ **纯对话平台（无工具执行）不能生图** —— 本包需要真正跑脚本、下载图片。

* * *

## 依赖分析：哪些是 opencode 专属

| 组件 | 依赖 opencode？ | 其它平台怎么办 |
|---|---|---|
| `skills/*/SKILL.md` | ❌（跨平台约定） | 复制到平台的 skills 目录即可 |
| `skills/volcengine-seedream/scripts/generate_image.py` | ❌（Python 标准库） | 直接执行 |
| `command/{draw,illustrate}.md` | ✅（opencode 命令机制） | 各平台自定义命令/规则，或直接说"出 4 张挑最好" |
| `@observer`（QC 评分 + 图→提示词反推） | ✅（OMO-Slim 子 agent 约定） | 有子 agent → 建一个视觉子 agent；无 → agent 自检，或跳过 |
| `skills.paths` / `opencode.json` | ✅ | 用平台对应机制 |

**结论**：**核心（清理规则 + 生成脚本 + Playbook）是平台中立的**；只有"命令"和"质检子 agent"两处需要按平台改写。

* * *

## 总表

| 平台 | skills 放哪 | 命令/规则放哪 | 子 agent | 移植难度 |
|---|---|---|---|---|
| **OpenCode**（原生） | `~/.config/opencode/skills/<n>/SKILL.md` | `~/.config/opencode/command/*.md` | 需插件（如 OMO-Slim） | — |
| **Claude Code** | `~/.claude/skills/<n>/SKILL.md` 或 `.claude/skills/` | `~/.claude/commands/*.md` | ✅ `~/.claude/agents/*.md` | ⭐ 极低 |
| **OpenAI Codex** | `.agents/skills/<n>/` 或 `~/.agents/skills/` | `~/.codex/AGENTS.md`；项目 `AGENTS.md` | 未证 | ⭐ 极低 |
| **DeepSeek Harness (`dsh`)** | `.agents/skills/` 或 `.dsh/skills/` | `cordis.yml` | ✅ 插件 | ⭐ 极低 |
| **WorkBuddy** | `.codebuddy/skills/<n>/SKILL.md` | 工作区设置 | ✅ | ⭐ 低 |
| **Cursor** | Skills 路径未证 | `.cursor/rules/*.mdc`（**必须 `.mdc`**） | ✅ `.cursor/agents/*.md` | 中 |
| **纯对话版** | — | 各平台"自定义指令" | — | ⚠️ 不适用（需执行代码） |

* * *

## 各平台接入动作

### OpenCode（原生）

1. 复制 `skills/*` → `~/.config/opencode/skills/`；`command/*.md` → `~/.config/opencode/command/`。
2. 重启（配置只在启动时加载）。
3. 若用 oh-my-opencode-slim：给需要的 agent 开 skill 白名单（如 orchestrator 的 `skills: ["*"]`）。

### Claude Code

```bash
mkdir -p ~/.claude/skills
cp -r skills/volcengine-seedream        ~/.claude/skills/
cp -r skills/seedream-prompt-compiler   ~/.claude/skills/
cp -r skills/seedream-qc                ~/.claude/skills/
cp command/*.md ~/.claude/commands/ 2>/dev/null || true
```
- `SKILL.md` 的 `name`/`description` 本来就符合 Claude Skill 约定，**几乎零改动**。
- code-exec 平台把 QC 的 `@observer` 换成一个视觉子 agent（`~/.claude/agents/`）。

### OpenAI Codex / DeepSeek Harness

- 把 `skills/<n>/` 放进 **`.agents/skills/`**（Codex 与 dsh **共用同一路径**，一份给两家用）。
- 分档/流程纪律并进 `AGENTS.md`。

### WorkBuddy

- `skills/<n>/` → 工作区 `.codebuddy/skills/<n>/`。

### Cursor

- 把 `seedream-prompt-compiler` 的**规则**转成 `.cursor/rules/seedream.mdc`；生成脚本仍可直接跑。

* * *

## 移植原则（为什么不用重写）

```
SKILL.md（清理规则 / Playbook / QC 评分表）+ generate_image.py  = 【内容】，平台中立
        │
        └─ 各平台只回答一个问题：这份内容【放哪、叫什么、什么格式】
```

**唯一真正依赖平台架构的**：命令机制、以及 QC 需要的"视觉子 agent"。单 agent 平台可退化为"agent 自检"或跳过质检。

* * *

## 未证 / 下次复核

1. **Cursor Skills 的确切路径与 frontmatter** —— 仅确认有专页，未取页。
2. **Codex 的文件型子 agent 规范** —— 官方未见专页。
3. **WorkBuddy 用户级 skills 路径** —— 属推断。
4. ⚠️ 平台格式变动极快 → 每隔几个月复核。
