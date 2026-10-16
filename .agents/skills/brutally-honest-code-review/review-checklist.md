# Code Review Failure Mode Checklist

Catalog of common code review failure modes organized by review priority. Use as a scan reference during analysis — not every mode applies to every review.

---

## 1. Correctness and Edge Cases

| Failure Mode | Symptoms | What to Check |
|--------------|----------|---------------|
| Null/undefined handling | Missing null checks, silent crashes | All inputs that can be null — function params, loop results, DB queries |
| Off-by-one errors | Fencepost loops, array index out of bounds | Loop boundaries: `<=` vs `<`, empty input edge case |
| Race conditions | Intermittent failures, data corruption | Shared mutable state without synchronization |
| Type coercion bugs | Silent type mismatches, wrong comparisons | `==` vs `===`, implicit string-to-number conversion |
| Missing error branches | Errors swallowed, unhandled exceptions | Every `catch` block: is it logging or swallowing? |
| Incorrect defaults | Wrong fallback values, silent misconfiguration | All default parameters and configuration fallbacks |
| Inconsistent state | Partial updates, torn writes | Atomicity of multi-step operations |

## 2. Security and Data Safety

| Failure Mode | Symptoms | What to Check |
|--------------|----------|---------------|
| Injection vectors | Unsanitized inputs in queries/commands | All user input reaching query builders, shell commands, templates |
| Auth bypass | Missing authorization checks on endpoints/operations | Every sensitive operation: who can call it? Is auth verified? |
| Data leakage | Sensitive data in logs, responses, URLs | PII, tokens, passwords — check all serialization paths |
| Privilege escalation | Users accessing resources they shouldn't | Cross-reference role checks with resource ownership |
| Unsafe deserialization | Insecure object loading from untrusted sources | `eval`, `unserialize`, dynamic imports from user input |
| Missing rate limiting | DoS vulnerability, brute force attacks | API endpoints accepting repeated requests without throttling |

## 3. Architecture and Responsibility Boundaries

| Failure Mode | Symptoms | What to Check |
|--------------|----------|---------------|
| God classes/modules | Single file/function doing too much | Count responsibilities — should each be its own unit? |
| Circular dependencies | Modules importing each other | Import graph: does any cycle exist? Which direction should flow? |
| Leaked abstractions | Implementation details visible through API | Public interfaces exposing internal structures or implementation quirks |
| Mixed concerns | One file handling multiple domains | Can the file's responsibilities be split by domain rather than type? |
| Tight coupling to external systems | Hard to test, hard to replace | All direct calls to services — are they abstracted behind interfaces? |
| Missing layer boundaries | UI code talking directly to database | Verify every path goes through the intended architectural layers |

## 4. Test Coverage and Quality

| Failure Mode | Symptoms | What to Check |
|--------------|----------|---------------|
| Missing unit tests | No tests for core logic paths | Every public function should have positive, negative, and edge-case tests |
| Brittle integration tests | Tests failing due to infrastructure, not code | Are they testing the right thing? Can they run offline? |
| Test-data coupling | Tests depending on shared mutable state | Are test cases independent? Does order matter? |
| No negative tests | Only happy-path assertions verified | Every function: are error cases and invalid inputs tested? |
| Mocking too aggressively | Tests passing but production failing | Are mocks hiding real dependencies or masking real behavior? |
| Tests not exercising public API | Implementation-only coverage | Are consumers of the code actually covered? |

## 5. Simplicity and Readability

| Failure Mode | Symptoms | What to Check |
|--------------|----------|---------------|
| Unnecessary abstraction | Indirection that adds no flexibility | Can a function be inlined without losing meaning? Should this even be its own thing? |
| Misleading names | Variable/function names not matching behavior | Read names in isolation — do they communicate intent clearly? |
| Dead code | Comments referencing removed logic, unused branches | `// TODO` comments left for months, imported but never called |
| Cognitive overload | Functions or files too deep/wide to hold in memory | Function length > 50 lines? Nesting depth > 3? Consider splitting |
| Copy-paste duplication | Nearly identical code blocks | Extract common logic; if it's duplicated twice, it will be a third time |

## 6. Performance (Evidence-Required)

| Failure Mode | Symptoms | When to Flag |
|--------------|----------|-------------|
| Unnecessary N+1 queries | Loops issuing database calls | Only when you can see the query being called in a loop without batching |
| Blocking I/O in hot path | Request handlers doing network calls sequentially | When latency requirements are visible (API response, UI interaction) |
| Unbounded caching | Caches growing without eviction | When memory usage is uncontrolled or stale data becomes a risk |
| Missing indexes | Full table scans on large tables | Only when you've seen the schema and can infer query patterns |
| O(n²) or worse algorithms | Nested loops over user-provided input | When complexity scales with unbounded external data |

## 7. Style (Last Resort)

Flag style issues only when they hide defects or violate established project conventions:

- Formatting inconsistencies that cause merge conflicts in hot paths
- Convention violations that would trigger CI failures
- Naming convention breaks that make code unreadable to team members

Do not flag: subjective formatting preferences, lint rules that can be auto-fixed.

---

## Certainty Scale Reference

When reporting findings, use this scale and justify your choice:

| Level | Meaning | Justification Required |
|-------|---------|----------------------|
| **Confirmed from code** | The defect is directly visible — a reviewer with no runtime context would agree | Quote the specific line(s) that prove it |
| **Likely from code structure** | The pattern strongly indicates a problem; reasonable to flag even without runtime verification | Explain why the code structure makes this probable |
| **Requires runtime/test verification** | The issue may or may not exist; needs execution to resolve | Specify what test, log, or metric would confirm/deny it |
| **Insufficient evidence** | Too speculative to include as a finding; note only if relevant to overall risk assessment | Explain exactly what data is missing and why it matters |
