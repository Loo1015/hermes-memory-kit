# memory-review

An LLM review gate for Hermes `memory()` writes. Every write is sent — together with the
current on-disk MEMORY.md/USER.md and a condensed rule sheet — to a reviewer model already
configured in your Hermes config, which returns one of three verdicts:

| Verdict | Behavior |
|---|---|
| `approve` | Write proceeds |
| `reject` | Blocked; the reason is returned to the model, which can rewrite and retry |
| `defer` | Blocked and parked for human review by default (`defer_blocks: false` to pass through instead) |

> **This is a quality filter, not a security boundary.** It fails open: if the reviewer
> model times out, is unreachable, or returns something unparseable, the write proceeds.
> It exists to catch most bad memory writes, not to guarantee anything.

中文文档：[README.zh-CN.md](README.zh-CN.md)

## What it gates — and what it doesn't

| Surface | Gated? | Notes |
|---|---|---|
| `memory()` tool calls, including background forks | ✅ | The main target. Background-fork blocks are surfaced to the foreground via a receipt mechanism (see Compatibility). |
| `skill_manage` | ❌ | Deliberately ungated: a bad skill doesn't consume always-on prompt budget, and memory-cleanup is the backstop. |
| Direct file edits (`write_file` / `patch` on MEMORY.md) | ❌ | Sanctioned manual channel. The plugin cannot see them and is not supposed to. |
| `retain` / `consolidation` (memory provider) | ❌ | Provider-side risk is "pollutes recall", never "corrupts MEMORY.md". |

Fail-open triggers: reviewer timeout, connection failure, malformed response, missing
model config, or `enabled: false`. The plugin never raises — raising inside
`pre_tool_call` would equal fail-closed.

## How it judges

Each call sends the full proposed operations, the current MEMORY.md/USER.md snapshot, and
six condensed rules to the reviewer:

1. **Retention value** — one-shot debug details, PR numbers, SHAs, temp paths, task progress → reject.
2. **Derivability** — bare facts cheaply re-derivable from authoritative sources → reject (unless re-deriving loses the decision rationale).
3. **Duplication** — equivalent to an existing entry → reject; adds detail → merge suggestion; facts changed → revise.
4. **Cost** — session-temporary state → reject.
5. **Phrasing** — imperative entries ("always/never…") → reject, ask for declarative form; one entry bundling multiple topics → reject, ask to split.
6. **Routing** — user facts belong in USER.md, environment facts in MEMORY.md; wrong target → reject.

The reviewer can see the on-disk memory state, which is what lets it judge duplication and
budget. When unsure it defers rather than guesses. Rewritten retries from the same origin
supersede their stale pending proposals automatically (exact `old_text` match or ≥0.6
similarity), so a fix-it loop never piles up zombie proposals.

## Install

Drop the plugin directory into your Hermes plugins folder, then in `config.yaml`:

```yaml
plugins:
  enabled:
    - memory-review

memory_review:
  alias: workbuddy      # a model_aliases entry; or provider: <name> + model: <name>
  timeout_s: 30
  defer_blocks: true    # false = defer passes through instead of blocking
  # enabled: false      # temporary kill switch, without touching plugins.enabled
```

The reviewer model is resolved from Hermes' own config — zero new credentials. Key
resolution supports literal values, `${VAR}` references, and `key_env` names; keys live in
memory only and are never logged or written to disk. Pick a cheap, fast model: the author's
instance (deepseek-v4.1-flash) measures ~1.7 s per review.

## Daily use

All interaction is plain text + sequence numbers (no interactive menus — see
Compatibility). Slash commands:

| Command | What it does |
|---|---|
| `/memory-review list` | Deferred proposals awaiting human review (seq no, id, time, origin, summary, reason) |
| `/memory-review approve <seq\|id>` | Issues a one-time hash pass; the agent then re-sends the same operations, which skip review |
| `/memory-review reject <seq\|id>` | Discards the proposal |
| `/memory-review approve 1 3` / `reject all` | Batch verdicts by sequence number |
| `/memory-review stats` / `recent` | Cumulative verdict counts / last 10 receipts |
| `/memory-review clean` | Clears pending proposals |

Approve never edits MEMORY.md directly: the plugin only issues a hash pass, and the write
still goes through `memory()`'s normal path (atomic batches, dedup, usage stats). Passes
are single-use.

## Compatibility

- **Desktop (apps/desktop): interactive menus don't work from plugin commands.** The plugin
  deliberately ships text-only output and delegates interaction to the host (GUI panel or
  message-platform buttons). Root cause is upstream (`ask_choice` from a plugin command
  hangs for 120 s on desktop and returns `None` when the session is busy); fixing it means
  changing Hermes source, not the plugin.
- **Review happens before argument validation.** Even a malformed payload gets reviewed —
  which is intentional: the reviewer's reject reason is visible to the model and lets it fix
  the payload.
- **Background-fork receipts ride along.** A blocked background fork can't show its block
  message to the foreground session, so the plugin piggybacks on the next successful
  foreground `memory()` result (`transform_tool_result`) with a one-line "N unread review
  receipts" notice. Errored foreground calls don't consume the receipt cursor; pure
  pass-through calls have no channel to carry it.
- **The reminder is per-turn injected**, not a system-prefix edit: `pre_llm_call` adds a
  one-line "N pending reviews" notice with a 30-minute cooldown (`remind_cooldown_s`),
  re-alerting immediately when the count changes. This keeps the prompt-prefix cache intact.

## Pair with

- [memory-cleanup](https://github.com/Loo1015/hermes-memory-kit) — periodic diet for
  MEMORY.md. The gate and the diet are complementary: the gate keeps junk out, cleanup
  reclaims budget from what already got in. Cleanup applies by writing the file directly,
  not through `memory()`, so its remove-heavy batches don't get re-litigated by this gate.
- [memory-write-discipline](https://github.com/Loo1015/hermes-memory-kit) — decides
  where a fact belongs *before* a single write, which reduces the volume the gate has to
  judge.

## Known limits

- Fail open is a design choice, not a defect: the gate's value is intercepting most bad
  writes, not 100% availability. memory-cleanup is the backstop for whatever slips through.
- The gate judges what the reviewer model can see. A factually wrong but confidently
  phrased write can pass; a genuinely valuable but awkwardly phrased one can be deferred.
  Human review of the deferred queue is the corrective loop.
