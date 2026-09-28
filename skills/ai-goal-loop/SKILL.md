---
name: ai-goal-loop
description: Use when 用户显式要求 multi-agent 自我迭代直至达标、goal-driven loop，或要求把测试证据回灌给 coder 的多轮收敛。
---

# AI Goal Loop

这是 ai-workflow-harness 之上的自动驱动层：先在编码前把方案立住，再把 harness 的实现与验证自动跑成**多轮收敛循环**，直到独立 goal-verifier 判定 acceptance criteria 全部有证据通过。**本 skill 不改一行 Python**，run_graph 仍是唯一调度真值，Helper 仍只做机械校验。

一句话定位：**方案先审、测试失败自修、终点人工**。design-critic 在 coder 之前把方案摆到 plan 的 Review Gate；测试失败要 rerun 时，verify gate 自动接受并回到 coder。全部达标、预算耗尽或需要 block 时，仍由人决定。

## Hard gates

- `run_graph 是唯一调度真值`：loop 不新增 node、不模拟 node、不绕过 node；所有调度结论只来自 Helper JSON。
- `每轮开始前必须 workflow status`：轮次与预算从 `attempts[phase]` 重推，不得靠对话记忆计轮次。
- 本 skill 不能作为 `--skill-dir`：`--skill-dir` 恒为 `<repo>/skills/ai-workflow-harness`（原因见下）。
- `design-researcher`、`design-critic`、`goal-verifier` 都是 loop-owned child，不是 run_graph node。loop 不得把它们的结论当作 phase 通过。
- 方案审在 coder 之前，且只在进入 implement 前做一次。人尚未接受 plan digest 时，不得 `workflow begin --phase implement`。
- 本 skill 必须用 `workflow init --goal-loop` 启动。该标志只写入本 run 的 policy，不改变其他 skill 的 verify gate。
- `verify_repair: auto` 只放行「verify 已 finalize，且 effective rerun 非空」的 gate。无 rerun 的达标终审、block、abort 仍是 `human_review`。
- 不得把 `verify_repair` 写进 `.ai-workflow.yaml`，也不得在 run 开始后改 policy。其他 skill 不传 `--goal-loop`，verify 仍恒为人工。
- 不得编辑 `.ai-workflow.yaml`；不得新建 run 来重置 attempt 预算；不得用 `workflow abort` + 新 run 洗掉轮次。
- 任何 state、attempt、dispatch、gate 异常一律 fail closed：`workflow status` 后按 `error.code` 路由，不手改 YAML、不复制旧 JSON。

## 为什么 `--skill-dir` 必须指向 harness

`WorkflowService._validate_skill_dir` 要求 `--skill-dir` 下同时存在 `references/agents/common-phase-contract.md` 和 `OWNER_CONTRACT[node.key]` 对应的每个 child 契约（`coder.md`、`test-runner.md`、`code-reviewer.md` 等）。这些契约只存在于 harness skill 中。

因此把 `--skill-dir` 指向本目录会立刻得到 `invalid_skill_dir: required child contract is missing`。**loop 驱动的是 harness 的状态机，不是自己的。** 本目录只有 loop 自己的参考文档，不承载 child 契约。

## Loop ownership boundary

loop 主 Agent 只做：读 Helper JSON、派发 child 与 loop-owned child、串行 stage、推导 rerun proposal、呈现 gate、写 evidence ledger。

loop **绝不**打开 child artifact 正文来自己判定达标或方案是否合适、绝不代写 ChildResult、绝不替 child 修 artifact。需要更细证据时 rerun 对应 child，或交给 design-critic / goal-verifier 读。

一个必须写死的非对称规则：`dispatch 不追加隐藏上下文` 只约束 **Helper 生成的 `prompt_file`**——loop 不得往里加任何东西。design-researcher、design-critic、goal-verifier 的 prompt 由 loop 自己编写。方案要想被 coder 看见，必须写进图上已登记的 plan artifact，不能只留在 `.ai-goal/`。

## 编码前的方案审

热循环开始前的固定顺序见下方 Exact control order：先 `design-researcher`，再把 brief 写入 plan artifact，再 `design-critic`。人接受 plan digest 之后才允许 `begin implement`。

design-critic 不产出 `met` / `unmet`，也不能自己挡住 coder。它只把 findings 摆到 plan gate；人接受之后方案冻结。热循环不再重跑 researcher 或 critic。实现是否偏离已接受的方案，由 `verify.code_review` 看 plan 和 diff，不另设第二个 critic。

论文检索和 skill 阅读不可机检。critic 的结论只是 evidence，不进停滞指纹。

## 两种拓扑（诚实对比）

方案被接受之后才进入下面任一拓扑。

- **Shape 1**：只在 implement phase 内 rerun `implement.code`，`review_mode: auto_accept` 生效。
- **Shape 2**：走完 verify，把测试证据回灌成 `implement.code` 的 rerun reason。

| 维度 | Shape 1 | Shape 2 |
| --- | --- | --- |
| 全自动 | 是 | 测试失败自修是；达标终审否 |
| 拿到测试证据 | **否**（implement phase 内无测试 child） | 是 |
| 每轮消耗的 phase 预算 | `implement` +1 | `implement` +1、`verify` +1 |
| 适用 | 纯实现推进、无可执行验收 | 用户的真实诉求：测试报告回灌 coder |

用户要的"测试报告发给写代码的 agent"**只能由 Shape 2 满足**。测试失败并给出 actionable rerun 时，verify gate 自动接受，不需要人点一次。全部 criteria 有通过证据、没有 rerun 时，终审仍是 `human_review`。这条只存在于 `--goal-loop` 的 run；其他 skill 的 verify gate 不受影响。

## Round budget

轮次上限的**唯一真值**是 `.ai-workflow.yaml` 的 `max_attempts`（默认 3），它由 Helper 表达为 `state.artifacts.attempts`。

- `attempts[phase]` 单调递增、永不回退；rerun 只清 `current_attempts`，不动 `attempts`。
- 于是轮数上界不是"每轮一次"，而是"循环路径上每个 phase 各 `max_attempts` 次，取最小值"。
- loop 自己的策略上限只能**下调**：`effective_round_cap = min(用户给定, 路径上剩余预算)`。策略上限永远不得高于机械预算，否则失败形态是信息量很低的 `attempt_limit`，而不是带完整证据的 `block`。
- 预算将尽（`remaining <= 1` 且未达标）时**提前一轮**主动 `workflow block`。

放大 `max_attempts` 是**使用前提**：想让 loop 跑 10 轮，必须在 `workflow init` 之前把配置抬到 11+。run 开始后改 YAML 无效——`review_mode` 在 `init` 时冻结，且中途抬预算属于被禁止的洗预算行为。

## Exact control order

```text
workflow status
-> design-researcher → design-brief.md
-> workflow begin --phase plan --skill-dir <repo>/skills/ai-workflow-harness
-> 把 brief 写入 plan artifact 并 stage / stage-owned
-> design-critic（implement 之前，只此一次）
-> workflow review
-> workflow review-accept --expected-digest DIGEST
-> workflow transition
-> workflow status
-> workflow begin --phase implement --skill-dir <repo>/skills/ai-workflow-harness
-> dispatch all sibling children before waiting
-> workflow stage  (每个 ChildResult 串行)
-> barrier 满足后 workflow finalize
-> workflow review          (implement gate：review_mode=auto_accept 时自动 accept)
-> workflow transition
-> workflow status
-> workflow begin --phase verify --skill-dir <repo>/skills/ai-workflow-harness
-> dispatch / stage / barrier / finalize
-> dispatch goal-verifier   (run_graph 之外，只读 evidence)
-> 写 evidence ledger 本轮条目与归一化指纹
-> workflow review --rerun NODE=REASON
-> workflow transition   (verify_repair=auto 且 effective rerun 非空时自动 accept)
-> workflow status
```

Transition 后必须立刻 `workflow status`，不得凭 transition 前的预期推进。人未接受 plan digest 时，控制顺序停在 plan gate，不得跳到 implement。

## Non-convergence

四个 block 触发器：预算耗尽、连续两轮指纹停滞、acceptance criteria 不可机检、环境或权限失败。全部走 `workflow block`，附完整证据包，交人决定 `resume` / `abort` / 修改验收标准。

方案级问题不是 block 触发器。critic 有证据的异议走 plan rerun；没有证据的意见不得进入 gate。

## Prohibited shortcuts

Do not edit `.ai-workflow.yaml` to raise the budget, and do not start a new run to launder attempts. 不得编辑 `.ai-workflow.yaml` 抬预算，不得新建 run 重置预算，不得 self-block + self-resume，不得把 goal-verifier 或 design-critic 的结论当作 phase 通过，不得在方案未被接受时开始编码，不得为了过关把 expected output 改成 broken behavior。

## Reference index

- 编码前的方案审：[design research](references/design-research.md)
- 循环与预算数学：[loop control](references/loop-control.md)
- 目标形式化与预检：[goal contract](references/goal-contract.md)
- 独立验证者契约：[goal verifier](references/goal-verifier.md)
- 账本与停滞指纹：[evidence ledger](references/evidence-ledger.md)
- 不收敛与升级：[non-convergence](references/non-convergence.md)

## Error posture

Helper error 只按 `error.code` 路由，不按 message 猜：

- `attempt_limit` → 收集证据，调用 `workflow block`，等待人类；不得改配置重试。
- `invalid_skill_dir` → 说明 `--skill-dir` 必须指向 `skills/ai-workflow-harness`，不扩大路径。
- `barrier_incomplete` → 继续等待缺失 sibling，不算 child failure。
- `review_gate_mismatch` → `workflow status` 后重新 `workflow review`；不 block。
- `stale_review_gate` → `workflow status` 后 `workflow block`；旧 acceptance 永久作废。
- 未列出的 code 也先 fail closed + `workflow status`，不根据 message 文本伪造恢复动作。
