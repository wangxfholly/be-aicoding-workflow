# Design Research：编码前的方案，不是热循环

design-researcher 与 design-critic 都是 **loop-owned child**，不是 `run_graph` node。它们只在进入 `implement` 之前运行一次。方案被 plan 的 Review Gate 接受后冻结；热循环不再重跑它们。

## 1. 为什么不放在 verify

verify 审的是已经写出来的代码和测试。方案拆得对不对必须在 coder 之前回答。放到 verify 里，代码已经按错前提写完，critic 只能事后否定，再把整段 implement 和 verify 重置。

编码前这一道挡的是「方案还没立住就开写」。实现是否偏离已接受的方案，留给 `verify.code_review`：它本来就要读 implementation plan 和 diff。不要第二个 critic。

## 2. 顺序

```text
design-researcher
  搜论文 + 读本地设计 skill → design-brief.md
-> 把 brief 写进图上的 plan artifact（见下）
-> design-critic
  只读 brief、论文笔记、被引用的 skill、plan artifact
-> plan Review Gate
  人接受 digest 之后才允许 workflow transition
-> workflow begin --phase implement
```

critic 说「不合适」不能自己挡住 coder。挡住 coder 的是人在 plan gate 上不接受。否则 critic 就变成第二套调度器。

## 3. brief 必须进图上的 artifact

child 的唯一初始上下文是 Helper 生成的 `prompt_file`。loop 不能把 brief 追加进 prompt，也不能指望 coder 去读 `.ai-goal/`。

因此 brief 的正文必须成为已登记 artifact 的一部分，随后作为 `prior_artifacts` / `allowed_input_paths` 进入 coder：

| profile | 载体 | 谁写 | brief 怎么进去 |
| --- | --- | --- | --- |
| grill | `plan.prd`（workflow-owned） | 主 Agent，`workflow stage-owned` | 写进 run 外的临时 PRD，再 stage-owned |
| full | `plan.solution` 的 `implementation-plan.md` | planner child | researcher 先把 brief 放到仓库内、`.ai-workflow/` 之外的路径；planner 在方案中引用并复述约束。loop 不代写该 artifact |

`.ai-goal/<run-id>/design-brief.md` 只是 researcher 的私有原稿。它不是 coder 的输入，也不是调度真值。

grill 没有 `plan.solution`。方案拆解就写在 `plan.prd` 里，和 acceptance criteria 分段，不能混成愿望清单。full 的方案拆解只属于 `plan.solution`；criteria 仍属于 `spec.spec`。

## 4. design-researcher

只做三件事，然后停：

1. 搜索与本目标直接相关的最新论文或公开技术报告。每条记下标题、URL、日期、和本目标相关的主张。搜不到就写 `no-paper-found`，不得编造引用。
2. 只读目标需要的本地设计 skill，不整包加载。默认目录是 `/Users/admin/repo/ai-agent-book/skills/`。按目标从 `multi-agent-design`、`loop-engineering`、`agent-evaluation`、`context-engineering`、`memory-system`、`tool-design` 中选择；目标用不到的不读。
3. 写 `design-brief.md`：拓扑、角色边界、为什么不用更简单的做法、风险、哪些主张有论文 URL、哪些只是 skill 里的工程判断。

researcher 不得写产品代码，不得调用 workflow helper，不得把论文主张写成 acceptance criterion。

## 5. design-critic

critic 在 planner（或 grill 的主 Agent）写完 plan artifact 之后、`workflow transition` 之前派发。一次。

- 读：`design-brief.md`、论文笔记、被引用的 skill、plan artifact。
- 不读：researcher 的推理过程、planner 的自我说明、任何「我认为已经合适」的叙述。
- 立场是专家审拆解：角色是否多余、是否违反「没有新信息就不该多 agent」、预算和失败模式有没有处理、论文主张有没有被用错。
- 产出 findings，不产出 `met` / `unmet`。方案对错不是布尔值，也不能拿来当 phase 通过。

findings 文件：

```text
.ai-goal/<run-id>/design-review.md
```

每条 finding 必须有 `evidence`（论文 URL、skill 路径，或 plan artifact 的章节）。没有证据的意见不得进入 Review Gate。

## 6. findings 到 rerun

| 证据指向 | rerun node |
| --- | --- |
| 验收标准、scope | grill：`plan.prd`；full：`spec.spec` |
| 拓扑、角色、文件边界、风险 | grill：`plan.prd`；full：`plan.solution` |
| 验证命令、测试范围 | `plan.test_strategy`（仅 full；grill 没有该 node） |

reason 必须 actionable，写明证据来源和下一轮要改的事实。不得使用空 reason 或 `UNABLE_REASON`。

人接受 plan digest 之后，方案冻结。热循环里只有 code-reviewer 或 goal-verifier 指出文件边界、角色、风险这些方案级问题时，才回到上表的 node，再派一次 critic。那是最贵的一跳，不进每一轮。

## 7. 四条禁令

- 不得修改 workflow state，不得编辑 `.ai-workflow/runs/**`。
- 不得调用 workflow helper。
- 不得 stage 任何结果；尝试 stage 会得到 `attempt_owner_mismatch`。
- 不得把 design-review 当作 phase 通过，也不得在人尚未 `review-accept` 时 `begin implement`。
