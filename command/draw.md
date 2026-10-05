---
description: 单张文生图（先过 Ask Gate 确认提示词与参数，再出图）
---

用户描述：$ARGUMENTS

1. 按 `seedream-prompt-compiler` 清理提示词（剥元指令 / 抽参数 / 去堆叠 / 否转正；**默认不补全**）。
2. 🚦 **走 Ask Gate**：展示「编译后提示词 + 一句话 diff + 风险」，**并逐项确认出图参数**（画面比例 / 有无参考图 / 单张或批量 / `flash` 或 `pro` / 分辨率，每项带推荐，可“全部用推荐”）。**未获确认不得生成。**
3. 获准后调用 `volcengine-seedream/scripts/generate_image.py` 出图（默认 `5.0-flash` + `1.5K`）。
4. 交付图片**本地路径**（脚本成功后会自动预览）。
