# seedream-toolkit

> **面向 agent 的火山方舟（Volcano Engine Ark）《豆包 Seedream 文生图》工具包** —— 出图 + 提示词清理 + 出图前闸门（含内容安全）+ 质检闭环 + 一键挑最佳。
> An agent-oriented toolkit for Volcano Engine Ark **Seedream text-to-image**.

## 为什么做这个 / Why this exists

大多数"提示词指南"是写给人看的。**agent 的失效方式不一样**：会无脑往提示词里加词、不做成本控制、不知道什么时候该多抽、把 24 小时失效的 URL 当结果。

本包把一轮**真实盲评实验**（多场景 × 模型 × 编译器 × 优化器 × 文字 × 编辑）得出的纪律，打包成 agent 可直接执行的形式。

| 常见（人类/默认）做法 | 本包（agent 向） |
|---|---|
| 往提示词里堆更多词 | **只"清理"不"补全"**（实测主动加词≈噪声） |
| 一律用最强模型 | **默认最便宜的 `flash`**（`c/p` 更优约 2×） |
| 一张不合意就加词重来 | **换 `seed` / 多抽挑最佳**（`-n`） |
| 一次到位 | **语义精度靠多抽挑正确**（改措辞无效） |
| 拿临时 URL 当结果 | **强制本地下载**（URL 仅 24h） |
| AI 写的提示词直接出图 / 参数靠猜 | **出图前 Ask Gate**：提示词 + 出图参数（比例/参考图/张数/模型/分辨率）都交你拍板，再花钱 |

## 适合谁 / 适用边界（请先自查）

✅ **高价值**：

- 在 **opencode**（或其它支持 `.agents/skills` 的 agent 平台）上用**火山方舟 Seedream** 出图。
- 想要**文生图 / 图生图 / 图像编辑**，且**在意成本**（默认 0.12 元/张）。
- 愿意用"多抽挑最佳 / 换 seed"代替"死磕提示词"。

⚠️ **价值打折 / 不适用**：

- 想生**视频**（Seedance）→ 本包只含**未接入附录**（有 ≥200 元门槛）。
- 用**非火山引擎**的图模型 → 脚本要改写（但"清理器 + best-of-N"的纪律仍适用）。
- **纯对话平台（不能执行代码）** → 无法生图，本包不适用。

## 内容 / What's inside

```
README.md
TESTING.md
LICENSE
skills/
  volcengine-seedream/          ← 出图：脚本 + Playbook（模型/成本/图生图/避坑/Seedance 附录）
    SKILL.md
    scripts/generate_image.py   ← 纯标准库；文生图/图生图/组图/多变体/元数据 + `--dry-run` 校验/报价 + 自动预览
  seedream-prompt-compiler/     ← 提示词"清理器" + Ask Gate（审提示词 + 审出图参数；R1–R7/R4.8）
    SKILL.md
    CONTENT_SAFETY.md           ← 内容红线清单（写提示词 / 编译前必读）
  seedream-qc/                  ← 质量自检闭环 + Best-of-N
    SKILL.md
command/
  draw.md                       ← /draw <描述>：出图统一入口（文生图 / 图生图·编辑 / 批量挑最佳 / 带自检，全走闸门）
portable/
  PLATFORMS.md                  ← 跨平台接入（Claude Code / Codex / dsh / WorkBuddy / Cursor…）
  agent-prompt.md               ← 通用 agent 提示词（无 skill 系统时直接用）
```

## 核心 / Core idea

```
清理提示词  →  🚦 你确认〔提示词 + 比例/参考图/张数/模型/分辨率〕  →  出图  →  质量靠 best-of-N  →  不满意先换 seed
```

- **模型路由**：默认 `flash`；仅"精确编辑 / 图层 / 结构精度硬要求"才用 `pro`。
- **成本**：`flash` 0.12 / `pro` 0.30–0.60 元/张（`lite` 官方**已停止新购**，11-24 关停）；**1K 与 1.5K 同价 → 永远用 1.5K**。
- **失败处置**：优先**换 seed**（而非改提示词）。
- **出图前闸门（Ask Gate）**：生成前把**提示词**（通过 / 改）和**出图参数**（比例 / 参考图 / 单张或批量 / `flash` 或 `pro` / 分辨率）**逐项交你拍板**，每项带推荐默认、可"全部用推荐"，**获准才花钱**。
- **自动预检 + 报价**：Ask Gate 确认参数时会**自动先跑 `--dry-run`**（零成本）——校验参数是否自洽 + 打印**预估费用**，通过后才真正出图。
- **无条件 + 不擅自重抽**：**任何出图都先过闸门**（提示词再具体也一样）；**未经你确认，不得自行重抽 / 换 seed / 跑第二轮**。
- **出图后自动预览**：成功后自动用系统看图打开（`--no-preview` 关闭）。
- **默认输出**：`<用户主目录>\Pictures\seedream`（自动创建，可改）。
- **内容安全（判定树）**：写提示词 / 编译前对照 [`CONTENT_SAFETY.md`](skills/seedream-prompt-compiler/CONTENT_SAFETY.md)，按**意图 + 语境**分三层：**硬红线 → 拒绝**、**灰区 → 说明风险后交你确认**、其余 → 放行。

## 🚀 傻瓜式安装（把这句丢给你的 agent 就行）

**最短版**：

```
阅读 https://github.com/WangYr-Peppa/seedream-toolkit
按 portable/PLATFORMS.md 的规则，把它装成这台机器上的 seedream 工具包。
```

**若它不知道你用哪个平台**，用这个更明确的版本（把【】换成你的平台）：

```
我用的平台是【OpenCode / Claude Code / OpenAI Codex / DeepSeek Harness / Cursor …】。

请先阅读 https://github.com/WangYr-Peppa/seedream-toolkit —— 重点读 README.md 与 portable/PLATFORMS.md，
然后按【本平台】的规则装到这台机器上：

  1) skills/volcengine-seedream/、skills/seedream-prompt-compiler/、skills/seedream-qc/
     → 复制到本平台约定的 skills 目录
  2) command/draw.md → 复制到本平台的自定义命令目录（若不支持命令，改为规则/指令）
  3) 确认环境变量 ARK_API_KEY 已设置，且账号已开通要用的 Seedream 模型
  4) 装完汇报：放了哪些文件 / 是否需要重启 / 怎么自查安装成功

不确定的地方先问我，不要猜；不要修改与本工具包无关的文件。
```

> 各平台确切路径见 [`portable/PLATFORMS.md`](portable/PLATFORMS.md)。装完**自查**：说一句「画一张：一只橘猫」，看它是否**先逐项问参数 → 自动 `--dry-run` 报价 → 确认后才出图**，并把图片**下载到本地**。完整测试见 [`TESTING.md`](TESTING.md)。

## 安装 / Install

> 🎯 **不在 OpenCode？** → [`portable/PLATFORMS.md`](portable/PLATFORMS.md)：Claude Code / Codex / dsh / WorkBuddy / Cursor 的放置位置与格式。
> 💬 **没有 skill 系统但能跑代码？** → [`portable/agent-prompt.md`](portable/agent-prompt.md)（贴进系统指令即可）。

### OpenCode（原生）

1. 复制到全局目录：
   ```
   ~/.config/opencode/skills/volcengine-seedream/
   ~/.config/opencode/skills/seedream-prompt-compiler/
   ~/.config/opencode/skills/seedream-qc/
   ~/.config/opencode/command/draw.md
   ```
   （或把 `skills/` 加进 `opencode.json` 的 `skills.paths`。）
2. 设置环境变量 `ARK_API_KEY`（火山方舟控制台「API Key 管理」创建）；账号**开通**要用的模型。
3. **重启 opencode**（配置只在启动时加载一次）。

> `.agents/skills/` 这份路径在 Codex / DeepSeek Harness 通用 —— **同一份 skills 可给多家用**。

## 诚实的限制 / Honest limitations

- ⚠️ **结论来自小样本盲评**（n ≤ 39，单 seed）。**方向可信，具体数字别当精确值**；"编译器无增益""默认 flash"若要坐实需更大样本。
- ⚠️ **没有银弹**：语义精度（计数 / 左右 / 动作）与审美差异**主要由抽样决定**，改措辞无效 → 只能多抽或上 pro。
- ⚠️ **价格与模型时效性**：单价/模型 ID 为 2026-10 于 cn-beijing 实测，**随时可能变**；以方舟控制台/价格页为准。
- ⚠️ **QC 依赖视觉子 agent**（opencode 用 `@observer`）；单 agent 平台需退化为"agent 自检"或跳过。
- ⚠️ **提示词仍是"AI 写的"**：清理器可能把模糊诉求直译成画面词、或改变结构（实测："脚部交代清楚"→"脚趾画清楚"→ 女孩丢了袜子）→ 本包用 **Ask Gate** 兜底：**你拍板后才生成**。
- ⚠️ **纯对话平台不能生图**（需执行代码 + 下载）。

## 怎么自查它有没有用 / Verify

1. 说一句出图需求 → 看它是否**先停下来**：把**提示词**交你过目，**并逐项问出图参数**（比例 / 参考图 / 单张或批量 / 模型 / 分辨率），**而不是闷头直接出图**。
2. 说 **`画一张：一只橘猫`** → 看它是否：**先逐项问参数 → 自动 `--dry-run` 报价 → 确认后**用 `flash`+`1.5K` 出 **1 张**并下载到本地；**不自动出第二张**。
3. 说 **`/draw <一句话描述>`** 并在闸门里选**「4 张挑最佳」** → 看它是否出 4 张并**排序挑出第一名**。
4. 说 **`/draw <描述>`** 并在闸门里选**「带自检」** → 看它是否走"确认 → 生成 → 视觉体检 → 不合格重抽"（**仅此时才允许自动重抽**）。
5. 完整测试清单见 [`TESTING.md`](TESTING.md)。

## FAQ

- **为什么控制台看不到 Seedream 4.0 / 4.5？** 它们在 **2026-09-24** 被方舟列入**第十批下线**（EOM 停止新购；2026-11-24 EOS 关停），所以**控制台不再放开新开通**；`5.0-lite` 同理。现在**可新开通**的生图模型只有 `5.0-flash` / `5.0-pro`（+ `4.0(20260415)`）。详见[模型下线公告](https://docs.volcengine.com/docs/ark/model-deprecation-notice)。
- **Ask Gate 提交时卡死 / 按回车没反应？** 这是 **opencode 的已知 bug**（`question` 组件键盘绑定死锁：[#36382](https://github.com/anomalyco/opencode/issues/36382)；修复 PR [#36550](https://github.com/anomalyco/opencode/pull/36550) **未合并**）。触发路径：**在某一问里手动输入自定义答案后，再用鼠标点 "Confirm" 提交**。
  - **规避**：① 少用鼠标、尽量**纯键盘**在选项里选；② **单次问题数 ≤4、每题选项 ≤4**（本工具包已按此约束）；③ 别在自定义输入后再切到 Confirm。
  - **卡死后**：`Esc` / `Ctrl+C` 可能全失效 → 关终端，用 **`opencode --continue`** 恢复会话（数据通常没丢）。
  - **自测**：卡死后**鼠标还能动、键盘全哑** → 命中此 bug；若**鼠标也点不动** → 是桌面版 webview 的另一类问题。

## 许可证 / License

- 代码与配置（`SKILL.md`、`scripts/`、`command/`）：**MIT**（见 `LICENSE`）。

## 来源 / Origin

Derived from a real tuning session (2026-10): a multi-scenario blind evaluation across single/multi-subject, text rendering, and image-editing, comparing raw vs compiled prompts, `flash` vs `pro`, and Ark prompt-optimization on/off — conclusions baked into the skills. No account-specific or personal content is included.
