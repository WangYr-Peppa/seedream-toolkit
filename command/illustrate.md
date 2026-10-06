---
description: 文档/PPT 批量配图（读大纲→建 job→一次批量确认→批量生图→回填→出文档）
---

目标文档/大纲：$ARGUMENTS

按 seedream-toolkit 的**批量配图契约**执行——**一次性批量确认**，不逐张打断：

1. **建 job**：读文档/大纲（用 `office`/`markitdown`；或用户已给的 deck 规格）→ 识别缺图位 → 写 `illustration_job.json`
   （结构见 `volcengine-seedream/scripts/illustrate.py` 头部注释：`style` 全局风格锁、`aspect_default`/`model`/`size`、`out_dir`、`items[{id,content,aspect?}]`）。
2. 🚦 **一次批量确认**：展示「N 张 / 统一风格 / 比例分布 / 预算」，**先跑** `illustrate.py gen job.json --dry-run` 报总价；整批过 `CONTENT_SAFETY.md` 判定树。**未获确认不得生成。**
3. **出图**：`illustrate.py gen job.json --result result.json --jobs 4 [--skip-existing] [--matte --bg '#RRGGBB']`
   （**失败项列出、不静默重抽**；默认 `flash + 1.5K`；`--jobs` 并发；`--skip-existing` 跳过已存在；`--matte` 顺手把底色对齐并回报 `seam_dev` 接缝偏差）。
4. **回填 / 组装**（二选一）：
   - **规格生成**：`illustrate.py resolve deck.json --result result.json -o deck.resolved.json`（`image_id`→`image`），再 `office/scripts/deck.py deck.resolved.json -o output/xxx.pptx`。
   - **美化已有 PPT**：`illustrate.py embed 原deck.pptx --placements P.json -o 新deck.pptx`（按坐标插/换图，**在副本上操作**）。
5. **组装**：`office/scripts/deck.py deck.resolved.json -o output/幻灯片-主题-YYYYMMDD.pptx`（或 `report.py` 出 Word）。
6. **交付**：成品路径 + 用图清单（id→prompt→文件）+ 总花费。

> 脚本：`volcengine-seedream/scripts/illustrate.py`（gen/resolve）、`office/scripts/deck.py`。契约与思路见 README「批量配图」一节。
