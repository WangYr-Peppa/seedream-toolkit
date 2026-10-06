---
description: 文档/PPT 批量配图（读大纲→建 job→一次批量确认→批量生图→回填→出文档）
---

目标文档/大纲：$ARGUMENTS

按 seedream-toolkit 的**批量配图契约**执行——**一次性批量确认**，不逐张打断：

1. **建 job**：读文档/大纲（用 `office`/`markitdown`；或用户已给的 deck 规格）→ 识别缺图位 → 写 `illustration_job.json`
   （结构见 `volcengine-seedream/scripts/illustrate.py` 头部注释：`style` 全局风格锁、`aspect_default`/`model`/`size`、`out_dir`、`items[{id,content,aspect?}]`）。
2. 🚦 **一次批量确认**：展示「N 张 / 统一风格 / 比例分布 / 预算」，**先跑** `illustrate.py gen job.json --dry-run` 报总价；整批过 `CONTENT_SAFETY.md` 判定树。**未获确认不得生成。**
3. **出图**：`illustrate.py gen job.json --result result.json`（**失败项列出、不静默重抽**；命令默认 `flash + 1.5K`）。
4. **回填**：`illustrate.py resolve deck.json --result result.json -o deck.resolved.json`（把 `image_id` 填成 `image` 路径）。
5. **组装**：`office/scripts/deck.py deck.resolved.json -o output/幻灯片-主题-YYYYMMDD.pptx`（或 `report.py` 出 Word）。
6. **交付**：成品路径 + 用图清单（id→prompt→文件）+ 总花费。

> 脚本：`volcengine-seedream/scripts/illustrate.py`（gen/resolve）、`office/scripts/deck.py`。契约与思路见 README「批量配图」一节。
