# Goal Verifier：run graph 之外的独立验证者

goal-verifier 是 loop 达标判定的唯一来源。它**不是 run_graph node**，而是 loop 自己派发的 **loop-owned child**。

## 1. 为什么它不是 run_graph node

CLI 没有扩展点：`_FULL_RUN_GRAPH` 是模块常量，`build_run_graph` 只能过滤不能新增；`stage` 与 `stage-owned` 都通过 owner 校验拒绝不在 `attempt.owner.nodes` 里的 child。

因此 goal-verifier **不能**是第 9 个 node，也**不能** stage 任何结果。它的产出是一份普通 JSON 文件，写在 loop 自己的 ledger 目录下。

## 2. 这不违反 harness 边界，而是加强它

harness 的边界是"workflow 不打开 child artifact 正文来补做 child 判断"。违反的形态是**主 Agent 自己读 artifact、自己下结论**。

goal-verifier 恰恰相反：主 Agent 依然不读 artifact 正文——它把"读证据 + 下判定"整件事外包给另一个 agent，且该 agent 独立于实现者。这是对边界的加强。

因此 verifier 是**被授权读证据正文的那个 agent**，主 Agent 不是。这条要写清楚，否则读起来会自相矛盾。

## 3. blind：不读实现者的推理

verifier 只看证据，**不读实现者的推理**：

- 读：`workflow status` 的 JSON 摘要、ledger、criteria 清单、命令退出码、artifact 内容。
- 不读：coder 的自我说明、上一轮 rerun reason 里的辩解、任何"我认为已经修好了"的叙述。

这是 **blind** 验证：verifier 必须能从证据本身独立得出结论，而不是被实现者的叙事锚定。与 `ai-workflow-harness` 中 code-reviewer 的 anti-anchored 要求同源。

## 4. verdict schema

verdict 文件必须是下列形状，键不可增减：

```json
{
  "verdict": "unmet",
  "criteria": [
    {
      "id": "AC-1",
      "status": "fail",
      "evidence": "verify.unit_test 的 artifact sha256 与退出码",
      "command": "unit_test",
      "observed": "exit status 1；3 个用例失败"
    }
  ],
  "blockers": ["AC-2 依赖的 verify.integration_test 不在 run graph 上"],
  "recommended_node": "implement.code"
}
```

字段约束：

- `verdict` ∈ {`met`, `unmet`, `unverifiable`}。
  - `met`：全部 criteria 有通过证据。
  - `unmet`：至少一条有失败证据。
  - `unverifiable`：证据不足或 criterion 不可机检——**不得降级成 `met`**。
- `criteria[].status` ∈ {`pass`, `fail`, `unknown`}；每条都要给 `evidence`、`command`、`observed`。
- `blockers` 列出阻止判定的外部因素（环境、权限、缺失 node）。
- `recommended_node` 必须是 run graph 中真实存在的 node，供翻译成 rerun 使用。

## 5. verdict 到 rerun 的翻译

verdict **不是** state，必须翻译成 `NODE=REASON` 才能进入 workflow：

| 证据指向 | rerun node |
| --- | --- |
| 需求、验收标准、scope 问题 | `spec.spec` |
| 方案拆解、文件边界、风险 | `plan.solution` |
| 验证命令、测试范围 | `plan.test_strategy` |
| 实现缺陷、编译错误 | `implement.code` |
| build 证据不足 | `verify.build` |
| 单测失败或覆盖不足 | `verify.unit_test` |
| 集测 case、mock、数据问题 | `verify.integration_test` |
| correctness/security/perf 结论问题 | `verify.code_review` |

reason 必须 actionable：写明要修正的事实、证据来源与目标。不得使用 `UNABLE_REASON` 占位符或空字符串，否则 `workflow review` 会抛 `invalid_transition`。

## 6. 四条禁令

- 不得修改 workflow state，不得直接编辑 `.ai-workflow/runs/**`。
- 不得调用 workflow helper（`status` / `begin` / `stage` / `finalize` / `review` / `transition` 全部禁止）。
- 不得 stage 任何结果；尝试 stage 会得到 `attempt_owner_mismatch`。
- 不得把 verdict 当作 phase 通过：verdict 说达标 ≠ `verify.code_review` 可以跳过，两者判的是不同问题——reviewer 判代码质量，verifier 判目标达成。

## 7. 可信度的诚实边界

Helper 对 verifier 零约束：没有 attempt_id、没有 barrier、没有路径授权、没有 digest 校验、不受不可变写入保护。任何能写 ledger 目录的进程都能伪造它的 verdict。

因此它的可信度上限就是"loop 主 Agent 的记账"。这也是为什么最终达标仍必须经过 verify 的 `human_review`——**verifier 提供判定与证据，人保留确认权**。
