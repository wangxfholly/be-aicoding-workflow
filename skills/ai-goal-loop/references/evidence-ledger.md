# Evidence Ledger：轮次账本与停滞指纹

loop 需要一个**跨轮次可比对**的证据视图。这个视图不新建事实源，全部从 `workflow status` 的 JSON 派生。

## 1. 账本位置

```text
<repo>/.ai-goal/<run-id>/ledger.jsonl      # 每轮一条 JSON 行
<repo>/.ai-goal/<run-id>/verdicts/round-N.json   # goal-verifier 的 verdict
<repo>/.ai-goal/<run-id>/criteria-digest.txt     # round 1 前的 criteria 冻结摘要
```

刻意放在 `.ai-goal/` 而不是 `.ai-workflow/`：

- `.ai-workflow/**` 与 `.ai-workflow.yaml` 在 `_INTERNAL_DENY_PATTERNS` 中被授权层拒写，写进去只会拿到路径越权错误。
- `.ai-workflow/runs/**` 是 Helper 的不可变证据，loop 不得污染。

账本是 loop 的**私有派生视图**，不是真值源。任何冲突以 `workflow status` 为准。

## 2. 一条账本条目

```json
{
  "round": 2,
  "phase": "verify",
  "attempt_id": "verify:3",
  "artifact_sha256": {
    "implement.code": "…64hex…",
    "verify.unit_test": "…64hex…",
    "verify.code_review": "…64hex…"
  },
  "finding_titles": {
    "verify.code_review": ["sorted(finding.title)", "…"]
  },
  "implementation_baseline": {
    "head_revision": "…",
    "dirty_paths": ["src/foo.py"]
  },
  "verdict": "unmet",
  "proposed_reruns": ["implement.code=<reason>"],
  "fingerprint": "…"
}
```

字段全部来自 `workflow status` 返回的 `RunState`：

- `artifact_sha256` ← `phase_aggregates[attempt_id].children[*].artifact.sha256`（64 hex，`ArtifactRef` 校验）
- `finding_titles` ← 同一 children 的 `findings[*].title`
- `implementation_baseline` ← checkpoint 中的实现基线：`head_revision`（本轮开始时的 HEAD）、`dirty_paths`（本轮触及的脏文件）、`base_revision`
- `verdict` ← goal-verifier 的 JSON

`implementation_baseline` 是判断"本轮到底改了什么"的**唯一可信来源**：`head_revision` 未变且 `dirty_paths` 集合未变，说明实现者几乎没动代码，这比 artifact 摘要更能说明停滞。

## 3. 归一化：指纹怎么算

直接比较原始 JSON 会因 `timestamps`、`attempt_id`、路径顺序等噪声而永远不相等，因此必须**归一化**：

1. **剔除**所有时间字段（`captured_at`、`created_at`、时长）与 `attempt_id`、`run_id`。
2. **剔除**绝对路径前缀，只保留仓库相对路径。
3. 对每轮收集该 node 的 `artifact.sha256`，按其自身排序后拼接。
4. 对 `finding_titles` 用 `sorted(finding.title)` 排序，再做集合去重。
5. 对 `dirty_paths` 同样排序。
6. 对上述四元组取一次 SHA-256，得到该轮的 **fingerprint**。

```text
fingerprint(round) = sha256(
  sorted(node -> artifact.sha256)
  + sorted(finding.title)
  + sorted(dirty_paths)
  + head_revision
)
```

关键点：**只排序、只剔除，不做语义归并**。任何"看起来等价就当成相同"的智能归一化都会让假阴性变成不可见，那正是最危险的失败模式。

## 4. 停滞判定

停滞 = **连续两轮** fingerprint 完全相同。

要求 `AND` 全部成立才判停滞，任一项不同则视为有推进：

| 条件 | 含义 |
| --- | --- |
| `artifact.sha256` 集合相同 | 产物内容一个字没变 |
| `sorted(finding.title)` 相同 | 问题清单没变 |
| `head_revision` 相同 | 没有新提交 |
| `dirty_paths` 集合相同 | 触及的文件没变 |

四者 **AND** 才是停滞；只比摘要更快但也更容易被骗。

### 假阳性

产物重排、改注释、改格式会让 `artifact.sha256` 变化，但问题一个没解决——指纹说"有推进"，实际在打转。缓解手段只有一个：`findings` 的 title 集合作为交叉验证；若 title 集合不变而摘要变，账本条目要显式标注 `suspicious_progress`。

### 假阴性

产物摘要变了、文件也动了，但改动无效——这类停滞指纹看不出来，兜底是 `max_attempts`（见 [non-convergence](non-convergence.md)）。

两种偏差都要在账本里如实记录，不得为了让循环继续而修改归一化规则。

## 5. 恢复

新会话或 stale 后，第一步永远是 `workflow status`，从 `attempts` / `current_attempts` / `phase_aggregates` 重建轮次认知，再从 ledger 读回指纹历史。

不得从聊天记录恢复 attempt、digest、fingerprint 或已 stage 的 child——聊天记录不是证据。
