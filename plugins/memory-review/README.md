# memory-review

An LLM review gate for Hermes `memory()` writes. Every write is sent — together with the
visible on-disk MEMORY.md/USER.md snapshot and the `_RULES` policy — to a reviewer model already
configured in your Hermes config, which returns one of three verdicts:

| Verdict | Behavior |
|---|---|
| `approve` | Write proceeds |
| `reject` | Blocked and discarded; the reason goes back to the model, which can rewrite and retry (foreground or background fork) |
| `defer` | Blocked and routed to human review by default: content worth keeping but not resident-layer goes into the pending inbox for a human to move to the right place (`defer_blocks: false` to pass through instead) |

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

The sole runtime policy source is [`_RULES`](__init__.py); this section is only an
overview, not a second rule sheet. Each call sends that policy, the complete operations,
and the visible MEMORY.md/USER.md snapshot to the reviewer, in this order:

1. Determine the batch's actual add/patch/remove effect, including deletion safety.
2. Route by scope: project material stays with the project; stable cross-task user
   preferences belong in USER.md.
3. Apply MEMORY.md's strict global-exception gate; ordinary system-environment material
   belongs in authoritative configuration, project records, or on-demand skills.
4. Check duplication and declarative, single-topic phrasing.

The line between the two blocking verdicts is **whether the content is worth keeping**, not
which layer it belongs to:

- `reject` = should not be stored in any layer: duplicate of a visible entry, temporary state /
  task progress / patch handoff, one-off debugging detail, PR numbers/SHAs, expired or disproven
  facts, bare values one line of authoritative config already answers (port, path, install
  location), empty pointers ("see X"), and pure phrasing problems (imperatives, multi-topic
  bundles — rewrite and resubmit, nothing is lost).
- `defer` = worth keeping but misplaced: belongs in a skill, a project AGENTS.md, project records
  or authoritative config docs; wrong `target` (a global preference written to MEMORY, a
  single-project rule written globally); key facts unresolved in a way that affects admission or
  deletion safety. It lands in pending, which doubles as the **human-routing inbox**.
- Mixed batches: if any substantive "worth keeping" content is present → `defer` (the human drops
  the worthless part while routing); if nothing in the batch could live anywhere → `reject`.

`reject`/`defer` only recommend a destination, never a completed migration. Rewritten retries from
the same origin can supersede older pending proposals (exact `old_text` match or ≥0.6 similarity);
cleanup preserves the current deferred proposal.

## Install

Plugin code is loaded at gateway startup. Disk edits take effect at the next restart;
editing these files does not reload an already-running gateway.

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
| `/memory-review list` | The defer inbox (seq no, id, time, origin, summary, reason — the reason carries the suggested destination) |
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
- **Pending doubles as the routing inbox.** `defer` accumulates "worth keeping but misplaced"
  content under `pending/memory-review/`; clear it with `/memory-review list` on a regular basis
  (`reject <id>` to close an item once routed). The queue never touches MEMORY.md and costs no
  always-on budget; identical content hashes to the same id so it does not pile up, and a
  rewritten resubmission supersedes its similar predecessors.
- The reviewer sees only the policy, operations and up to 6,000 characters from each
  on-disk memory file. It cannot inspect external skill/project bodies or migration proof;
  a proposal claiming "skill X already covers this" is not verification. Model judgments
  can be wrong; human review corrects unresolved admission/deletion cases.
- An unknown but parseable `decision` currently falls through to an `approve` receipt.
  This is a known fail-open boundary, not validation of a fourth verdict.
