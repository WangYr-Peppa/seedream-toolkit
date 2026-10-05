---
description: 带自检的出图闭环（Ask Gate → 生成 → 视觉体检 → 不合格重抽）
---

描述：$ARGUMENTS

按 `seedream-qc` 跑闭环：

1. 编译提示词（`seedream-prompt-compiler`）。
2. 🚦 **走 Ask Gate**：确认提示词 + 出图参数（比例 / 参考图 / 张数 / 模型 / 分辨率）。
3. 生成（`volcengine-seedream/scripts/generate_image.py`）。
4. 交 @observer 按评分表体检 → 不合格**只改一处**重抽（默认封顶 2 次）→ 交付最佳。
