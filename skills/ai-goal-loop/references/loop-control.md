# Loop Control：预算数学与两种拓扑

本文件是 loop 最反直觉的部分。所有结论都以 Helper 的持久化状态为准，loop 不维护第二套计数。

## 1. 轮次与预算的真实语义

`max_attempts` 是 **per-phase 的 run 级总预算**，不是"每轮预算"。三条机械事实决定了一切：

| 事实 | 后果 |
| --- | --- |
| `attempts[phase]` 单调递增、永不回退 | `max_attempts` 用一次少一次，整个 run 生命周期内不恢复 |
| rerun 只清 `current_attempts`，不动 `attempts` | rerun 不会"退还"预算 |
| `apply_reruns` 只重置 earliest phase 之后的所有 node | rerun 越靠上游，重跑的 phase 越多，消耗越大 |

因此 loop 每次 begin 之前必须先 `workflow status`，从 `state.artifacts.attempts` 读出各 phase 已用次数，再算剩余。

```text
remaining[phase] = max_attempts - attempts[phase]
effective_round_cap = min(用户给定上限, 循环路径上所有 phase 的 remaining 最小值)
```

`effective_round_cap` **只能下调，不能上调**。策略上限高于机械预算时，失败形态会退化成一句信息量很低的 `attempt_limit`，而不是 loop 自己带完整证据的 block。

## 2. 四种 rerun 的消耗

| 循环动作 | 消耗 | 可用轮数 |
| --- | --- | --- |
| rerun `implement.code`（phase 停在 implement） | `implement` +1 | `max_attempts` 轮 |
| rerun `implement.code`（从 verify 发起） | `implement` +1，`verify` +1 | `max_attempts` 轮，且 verify 预算同时消耗 |
| rerun `verify.unit_test` / `verify.code_review`（只修测试资产或复审） | `verify` +1 | `max_attempts` 轮，implement 不动 |
| rerun `plan.solution`（深 rerun） | `plan` +1，`implement` +1，`verify` +1 | 由 `plan` 剩余预算决定，最先耗尽 |

最便宜的一轮是只 rerun 单个 `verify.*`；最贵的是 `plan.*`。loop 在预算将尽时应优先选择便宜路径，或在无法达标时直接 block。

## 3. rerun 传播是 phase 粒度，不是依赖图

`apply_reruns` **只重置 earliest phase 之后**所有 phase 的全部 node 为 `pending`，并清空其 reason。两个必须记住的推论：

- rerun `implement.code` 会把 `verify.build`、`verify.unit_test`、`verify.integration_test`、`verify.code_review` **全部**重置为 pending，即使只点名了一个。
- **同一 phase 内的兄弟 node 不受影响**：只 rerun `verify.unit_test` 时，`verify.build` 与 `verify.code_review` 保持 `valid`。

另外，earliest phase 之外被点名的 node 不会被打成 RERUN，其 reason 会丢失。跨 phase 的多条反馈必须拆成多条 proposed rerun，且要预期下游被整段重置。

## 4. 一轮的边界与两种拓扑

一轮 = `finalize -> review -> review-accept -> transition`。`effective_reruns` 为空表示本 phase 无待修项。

两种拓扑都从**已被人接受的 plan**起。design-researcher 与 design-critic 不属于一轮，也不在热循环里重跑。人尚未接受 plan digest 时，不得进入下面任一拓扑。

### Shape 1：只在 implement phase 内循环

```text
begin --phase implement -> dispatch coder -> stage -> finalize
-> review (auto_accept) -> transition -> status
-> review --rerun implement.code=<reason> -> review-accept -> transition
```

`review_mode: auto_accept` 在此生效（implement 不是 verify），因此**全自动**。但 implement phase 内没有测试 child，**拿不到任何测试证据**——不满足"测试报告回灌 coder"的诉求。

### Shape 2：走完 verify，把测试证据回灌

```text
begin --phase implement -> dispatch coder -> stage -> finalize
-> review (auto_accept) -> transition
-> begin --phase verify -> dispatch test-runner / code-reviewer -> stage -> finalize
-> dispatch goal-verifier (run_graph 外) -> 写 ledger
-> review --rerun implement.code=<来自测试与 review 的证据>
-> transition   <-- goal-loop run：effective rerun 非空时自动 accept
-> status (回到 implement)
```

**Shape 2 的测试失败自修只在 `workflow init --goal-loop` 的 run 上生效。** policy 里的 `verify_repair: auto` 让「verify 已 finalize 且 effective rerun 非空」的 gate 自动 accept。没有 `--goal-loop` 的 run，verify gate 仍恒为 `human_review`，其他 skill 不受影响。

无 rerun 的达标终审不自动接受。block、abort、self-resume 也不受这条旁路影响。

选择建议：用户明确要求测试证据回灌时用 Shape 2，并事先告知人类每轮都要确认；只要求推进实现时用 Shape 1。

## 5. 两个容易踩的语义坑

### review_mode 在 `init` 时冻结

`review_mode` 在 `workflow init` 时被写进 run policy 证据并持久化校验。**run 开始后改 `.ai-workflow.yaml` 完全无效**，包括中途把 `human` 改成 `auto_accept`，或抬 `max_attempts`。后者还属于被禁止的洗预算行为。

### `unable_to_complete` 会强制 loop 写 reason

child 返回 `unable_to_complete` 时，`finalize` 会把该 node 置为 RERUN 并写入 `UNABLE_REASON` 占位符。而下一次 `workflow review` 对占位 reason **抛 `invalid_transition`**。

也就是说：只要本轮有任何 child unable，loop **不能"什么都不提"地 transition**，必须自己写出一条 `actionable reason`——说明 blocker、证据来源和下一轮 child 应做什么。禁止直接沿用占位符，也禁止空 reason。

## 6. 禁止的轮次手法

- 不得编辑 `.ai-workflow.yaml` 提高 `max_attempts`。
- 不得用 `workflow abort` + `workflow init` 新建 run 来把 `attempts` 洗回 0；新 run 会让全部 node 回到 pending，等于重置预算。
- 不得 self-block + self-resume 来绕过 verify 的 `human_review`。
- 不得在 `status` 显示 blocked 时继续 begin/stage/finalize/review/transition。

## 7. 恢复

新会话或 stale 后第一步总是 `workflow status`，从 `attempts` / `current_attempts` / `phase_aggregates` 重建轮次认知，再从 ledger 读回指纹历史。不得从聊天记录恢复 attempt、digest 或已 stage 的 child。
