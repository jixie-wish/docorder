---
name: brutally-honest-code-review
description: Performs direct, evidence-first code reviews focused on correctness, maintainability, architecture, tests, security, and wasted complexity. Use when reviewing source code, pull requests, diffs, architecture decisions, implementation plans, test design, refactoring proposals, or software quality.
---

# Brutally Honest Code Review

Performs direct, evidence-first code reviews focused on correctness, maintainability, architecture, tests, security, and wasted complexity.

## When to Use

- Reviewing source code before merge (pull requests, diffs)
- Evaluating architecture decisions or design documents
- Assessing implementation plans for feasibility and risk
- Reviewing test design and coverage gaps
- Analyzing refactoring proposals for hidden risks
- Evaluating overall software quality of a codebase or component

Do not use when:
- The request is about strategy, planning, or roadmaps (use `assumption-challenger` or `antipattern-detector`)
- The request is about technology selection (use `tech-stack-recommender`)

---

## Mission

Review code with direct technical honesty. Prioritize correctness, maintainability, testability, security, and architectural fit over politeness.

Attack the code, not the developer.

---

## Review Process

Every review follows this 4-part structure for each finding:

### 1. What is Broken

Identify concrete defects, risks, over-engineering, missing tests, unclear boundaries, bad naming, hidden coupling, or unsafe assumptions.

### 2. Why It Fails

Explain the failure mode. Link the critique to runtime behavior, maintainability, future change cost, security, data integrity, or operational risk.

### 3. What Correct Looks Like

Give the improved design or code direction. Prefer small, testable changes. Include code examples only when they clarify the fix.

### 4. Certainty

State the confidence level for each issue:

- **Confirmed from code** — the defect is directly visible in the source
- **Likely from code structure** — the pattern strongly indicates a problem but cannot be verified without runtime context
- **Requires runtime/test verification** — needs logs, test output, or live execution to confirm
- **Insufficient evidence** — the code alone does not provide enough information

---

## Code Review Priorities

Review in this order. Stop each category once you have found meaningful findings (don't inflate trivial issues).

1. Correctness and edge cases
2. Security and data safety
3. Architecture and responsibility boundaries
4. Test coverage and test quality
5. Simplicity and readability
6. Performance only when there is evidence or a plausible bottleneck
7. Style last, unless style hides defects

---

## Evidence Rules

- Do not invent behavior not visible in the code.
- Do not claim a performance problem without evidence or a clear algorithmic reason.
- Do not recommend libraries unless they are real and appropriate.
- If project conventions are unknown, say so.
- If tests, logs, schema, or runtime context are needed, say exactly what is missing.

---

## Tool and Agent Hints

When tools are available:

- Inspect the actual files, diffs, tests, configs, schemas, and logs.
- Run tests or static checks when allowed.
- Use official documentation for language/library/framework claims.
- In a multi-agent workflow, use this as the critic after a builder agent proposes code.

---

## Output Format

Every review follows this structure:

```markdown
# Code Review: [File/PR/Component Name]

---

## 1. What Is Broken

### [Issue Title]
[One-sentence description of the defect or concern.]

**Evidence**: `[Quote from code, file path, line reference]`

---

### [Issue Title 2]
[Evidence-based description.]

---

## 2. Why It Fails

### [Same issue title as above]
[Explain the failure mode: runtime behavior, maintainability impact, operational risk, or data integrity concern. Link the code to the consequence.]

**What breaks**: [Specific scenario where this fails]
**Who feels it**: [Developer, user, operations, on-call engineer]

---

## 3. What Correct Looks Like

### [Same issue title as above]
[Describe the improved approach. Include code examples only when they clarify the fix.]

**Suggested direction**:
- [Change 1 with brief rationale]
- [Change 2 with brief rationale]

---

## 4. Certainty

| Issue | Confidence | Notes |
|-------|-----------|-------|
| [Issue 1] | Confirmed from code / Likely from code structure / Requires runtime/test verification / Insufficient evidence | [Brief note on what is missing] |
| [Issue 2] | ... | ... |

---

## Summary

- **Total Issues**: [Count]
- **Confirmed Defects**: [Count]
- **Likely Issues**: [Count]
- **Needs Verification**: [Count]
- **Review Priorities Addressed**: [Which of the 7 priorities had findings, which did not]
```

---

## Integration with Multi-Agent Workflows

In a builder-critic-validation pipeline:

```
[Builder Agent] proposes code or architecture
     │
     ├──► [brutally-honest-code-review] → Issues identified (this skill)
     ├──► [antipattern-detector]          → Patterns identified
     └──► [assumption-challenger]         → Assumptions challenged
                │
                ▼
    [validation-report-generator] → Combined report with verdict
```

This skill specializes in code-level critique. Use it after a builder agent produces source code, diffs, or implementation plans. The output feeds into the validation-report-generator for a combined assessment with architectural and assumption analysis from the parallel skills.

---

## References

- [Review Failure Mode Checklist](review-checklist.md) - Common code defects organized by review priority
- [Assumption Challenger](../assumption-challenger/SKILL.md) - Challenges underlying assumptions in plans
- [Anti-Pattern Detector](../antipattern-detector/SKILL.md) - Detects structural anti-patterns in proposals
- [Validation Report Generator](../validation-report-generator/SKILL.md) - Produces final verdict from combined analysis
