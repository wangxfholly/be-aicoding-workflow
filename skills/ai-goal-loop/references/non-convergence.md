# Non-convergence：不收敛时的升级路径

loop 的底线是：**不达标就停，并把证据摆全**。无声降级、悄悄放宽判据、伪造一个"通过"都比停在半路更糟。

## 1. 四个 block 触发器

只要命中任意一个，立刻 `workflow block`，不再进入下一轮。方案级异议不属于这四个触发器：design-critic 有证据的 finding 走 plan rerun，不走 `workflow block`。

| 触发器 | 判据 | 证据要求 |
| --- | --- | --- |
| **预算耗尽** | 循环路径上任一 phase 的 `remaining <= 1` 且 criteria 未全通过 | 各 phase 的 `attempts[phase]` 与 `max_attempts` |
| **指纹停滞** | **连续两轮** fingerprint 完全相同（见 evidence ledger） | 两轮的 `artifact.sha256`、`sorted(finding.title)`、`head_revision`、`dirty_paths` |
| **acceptance criteria 不可机检** | criterion 依赖的 node 不在 `run_graph` 上，或无法从证据判定 | criterion id、缺失的 node 名、`disabled_nodes` 快照 |
| **环境或权限失败** | 命令因环境、凭据、权限、网络失败，而非代码失败 | 命令、error.code、原始输出摘要 |

**提前一轮**触发：不要等到 Helper 自己抛 `attempt_limit` 才停。`attempt_limit` 只给一行错误码，loop 自己 block 能给出完整证据包。

## 2. block 的证据包

```bash
workflow block --reason "<含轮次、证据与仍失败的 acceptance criteria 的完整陈述>"
```

reason 必须包含五段，缺一不可：

1. **轮次**：已跑几轮、每轮消耗了哪些 phase 的预算。
2. **触发条件**：命中了上表哪一个触发器。
3. **仍失败的 acceptance criteria**：逐条列出 id、断言、期望 vs 观测、证据来源。
4. **已排除的路径**：试过哪些 rerun 目标、哪一轮改了什么。
5. **建议的人类动作**：放宽判据 / 改需求 / 换方案 / 放弃。

reason 不是日志，是给人做决策用的。不得写"无法完成"这种无信息量的句子。

模板：

```text
round 4/5 命中 指纹停滞（连续两轮 fingerprint 相同）
implement.attempts=4/5, verify.attempts=3/5
仍失败：AC-2（集成测试断言 order.status == "paid"，实际 "pending"，证据 verify.integration_test#round3/4）
已排除：round3/round4 各 rerun 一次 implement.code，head_revision 未变、dirty_paths 未变
建议：确认支付状态机是否需要外部回调桩；若需要，请指定桩的实现位置后再 resume
```

模板里的每一行都对应上面五段中的一段。

## 3. block 之后的禁止动作

- **不得 self-block + self-resume**：block 与 resume 都是人类决定，loop 自产自销等于绕过 Review Gate。
- 不得编辑 `.ai-workflow.yaml` 抬 `max_attempts`（`review_mode` 在 `init` 时冻结，抬预算属于洗预算）。
- **不得用 `workflow abort`** + 新建 run 来把 `attempts` 洗回 0。
- 不得在 `status` 显示 blocked 时继续 begin / stage / finalize / review / transition。
- 不得把 verdict 的 `unverifiable` 改写为 `met` 以求收敛。

## 4. 人类的三条出口

blocked 只能由人解除。人类看到证据包后有三条路：

| 出口 | 命令 | 适用 |
| --- | --- | --- |
| 按证据再试一轮 | `workflow resume --rerun NODE=REASON` | 触发器是环境问题，或人补了 loop 拿不到的信息 |
| 改判据 | 改 criteria 后按 grill/full 走对应 node 的 rerun | 原判据不可机检或已过时 |
| 放弃 | `workflow abort` | 目标本身不成立 |

`resume --rerun` 需要显式的 `NODE=REASON`，且 reason 要与 block 证据包一致——人类不是在"再试一次"，是在指定下一轮修什么。

## 5. 预算放大是使用前提，不是补救手段

想让 loop 跑 10 轮，必须在 `workflow init` **之前**把 `max_attempts` 抬到 11+。run 开始后改 YAML 无效。

因此正确的顺序是：先形式化 goal，确认可机检，再决定 `max_attempts`，最后 `workflow init`。反过来的顺序会让 loop 在第一轮就撞上 `attempt_limit`，而那时它连 block 的证据都还没攒够。

## 6. 报告诚实性

向用户汇报时，必须区分三种终局，不得混用措辞：

- **达标**：全部 criteria 有通过证据，且已过 verify 的 `human_review`。
- **blocked**：有完整证据的不收敛，等待人类决策。
- **未验证**：本地跑通但未经真实客户端验收——不得声称"已通过"或"reference-parity"。

verifier 的 verdict 只影响第一项的**前提**，不构成终审。终审在人的 `review-accept`。
