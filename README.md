# Hermes Memory Kit

**English** · [中文](README.zh-CN.md)

Tools that keep [Hermes Agent](https://hermes-agent.nousresearch.com/docs) long-term memory **small and honest**: a gate on writes, a diet for what got in, and the discipline for deciding where a fact belongs in the first place.

> This is a **memory-tool kit** — one plugin plus two skills. It doesn't touch Hermes internals and it doesn't add an automatic cleaner: upstream Hermes treats memory overflow as intended behavior, not a bug.

---

## Why this exists

Hermes injects `MEMORY.md` and `USER.md` into the system prompt every turn. Three consequences follow, and none are handled by defaults:

1. **Everything written is paid for forever.** "Phase 3 done" and "tried port 8080, worked" sit in the prompt on every message for the rest of the year.
2. **Nothing judges whether a fact belongs there.** A one-off debug detail and a machine-wide hard constraint look identical once written.
3. **When it fills up, it just fills up.** There's no auto-compaction. Writes start failing and you find out mid-task.

Memory quality isn't a size problem — it's a **routing** problem. That's what this kit fixes, on three layers:

| Layer | Tool | When it runs |
|---|---|---|
| **Gate** | `plugins/memory-review` — LLM review of every `memory()` write | Before the write lands |
| **Discipline** | `skills/memory-write-discipline` — value/ownership/loading gates for the agent's own judgment | At write time (probabilistic) |
| **Diet** | `skills/memory-cleanup` — inventory → relocation plan → approved apply | When memory is already bloated |

The three connect: discipline reduces what needs gating, the gate blocks most of what discipline misses, cleanup reclaims budget from whatever slips through both. None of them alone is "memory is now clean."

---

## Contents

### `plugins/memory-review` — the gate

An LLM review gate for `memory()` writes. Every write is sent — with the current on-disk
MEMORY.md/USER.md and the rule sheet embedded in the plugin (`_RULES`, the single live
policy source) — to a reviewer model already configured in Hermes; verdicts are
approve / reject with reason / defer-to-human. Since 0.6.x the verdict taxonomy is
explicit: **defer = worth keeping but misplaced** — pending doubles as a human routing
inbox (route it to the right skill / project file / USER, then close the item);
**reject = belongs nowhere** (duplicates, transient state, re-derivable bare values,
stale facts, wording-only issues the writer can fix and resubmit). Admission to MEMORY
is strict: environment manuals, configs, paths, incident history and project state go to
on-demand homes by default; only pre-emptive protections that would cause a concrete
serious error *before normal lookup* qualify.

- **Zero new credentials**: the reviewer resolves from `model_aliases` / `providers`; keys never leave memory.
- **Fail open by design** — it is a quality filter, not a security boundary. Details and config: [`plugins/memory-review/README.md`](plugins/memory-review/README.md) ([中文](plugins/memory-review/README.zh-CN.md)).
- **Honestly documented limits**: desktop interactive menus don't work from plugin commands (text-only output); background-fork blocks are surfaced via ride-along receipts; a rewrite loop auto-supersedes stale pending proposals; truncated reviewer output is salvaged by regex instead of failing open (0.6.1); small reviewer models vary between identical runs — borderline verdicts are probabilistic, cleanup remains the backstop.

### `skills/memory-write-discipline` — the discipline (original)

Four parts worth reading even if you never install it:

- **§1 Three gates.** Value / scope / loading. The rule that matters most: *you may not use a later gate to veto an earlier one* — "not worth paying tokens every turn" must not kill a fact that legitimately belongs in a scoped file.
- **§3 Four questions.** Value, derivability, duplication, cost. The negative list (PR numbers, SHAs, temp paths, task progress) contains instances of these four, not separate rules.
- **§4 Writing style.** Declarative, not imperative. `User prefers concise replies` ✓ / `Always respond concisely` ✗ — an imperative gets re-read as a live instruction and can override what the user actually just asked.
- **§5 Tool mechanics.** `patch` replaces a *span*, not a whole entry. Pass only the opening sentence and the old tail survives — the file grows and the call still returns success.

It also covers a **date-tag** policy and why the default is *no dates*: a timestamp is one signal, but it breaks `patch` addressing, creates duplicates that exact-match dedup can't catch, and — decisively — invites downstream code to treat **age as staleness**, which is exactly backwards for hard constraints that grow more valuable with age.

### `skills/memory-cleanup` — the diet (fork)

MIT fork of TechNickAI's `memory-cleanup` v0.1.2. Its core principle is worth quoting verbatim: *"This is not a deletion pass. It is a routing pass."*

Kept as a **frozen fork, not tracking upstream** — upstream no longer ships this file. Three local adaptations are documented in [`THIRD-PARTY.md`](THIRD-PARTY.md); no original rules were removed.

---

## Two maintenance strategies for MEMORY

Since the skill layer can't be mechanically enforced, curation needs a strategy:

**Strategy A: free writes + gate + cleanup after the fact (what the author runs)**

- Let `memory()` write freely; the review gate (plugin) + discipline (skill, probabilistic) raise quality
- The 80% yellow line is a **hard trigger**: when the tool reports `current/limit` ≥ 80%, the agent must add a warning line that turn and suggest a cleanup dry-run
- The cost is "window pollution": between cleanup runs, bad entries keep occupying the per-turn prompt budget. With a low write rate and low watermark, that cost is small

**Strategy B: approve every write (`memory.write_approval: true`)**

- Mechanically enforced: all memory/skills writes land in a pending directory for human review
- The catch: review gets deferred to a moment when you **no longer have the context that motivated the write** — batch-approving a day later produces the worst judgments; scheduled/background task writes pile up

**Trade-off in one line:** the problem with B isn't review itself, it's review timing. If your write rate is low, take A and treat the yellow line as the gate. Keep discipline either way.

---

## Install

**1. The plugin** — copy `plugins/memory-review/` into your Hermes plugins directory, then in `config.yaml`:

```yaml
plugins:
  enabled:
    - memory-review

memory_review:
  alias: <a cheap, fast model from model_aliases>
  timeout_s: 30
  defer_blocks: true
```

Full config surface and daily commands: [`plugins/memory-review/README.md`](plugins/memory-review/README.md).

**2. The skills**

```bash
git clone https://github.com/Loo1015/hermes-memory-kit.git
cp -r hermes-memory-kit/skills/memory-write-discipline <SKILLS_DIR>/
cp -r hermes-memory-kit/skills/memory-cleanup           <SKILLS_DIR>/
```

`<SKILLS_DIR>` comes from `hermes config get skills_dir` (commonly `~/.hermes/skills/`). **Don't copy absolute paths out of anyone's setup, including the author's.**

Verify:

```bash
hermes skills list | grep memory
```

Both lines should read `enabled`.

**3. Know what is and isn't enforced**

- The **plugin is mechanical**: every `memory()` call is intercepted by code, every time.
- The **skills are not a deterministic channel**: the model decides whether to load them based on description; installed, they're still just documentation on disk. Don't paper over this with a SOUL.md reminder — that's one more line paid every turn, still not a guarantee.

**4. Optional first run** — ask your agent, in-session:

> Run memory-cleanup against my MEMORY.md and USER.md as a dry-run. Produce the review artifacts. Don't change anything yet.

---

## Thresholds

Proportional, so they follow your config instead of hardcoding numbers:

| Usage | Behavior |
|---|---|
| < 80% | Nothing |
| ≥ 80% (yellow) | One line at the end of the reply: which layer, characters, percentage, suggestion |
| ≥ 95% (red) | Warning + **must** free equal space in the same atomic batch before the next write |

These are **this project's own operating thresholds, not platform behavior.** Hermes only hard-rejects at 100% (and checks the final state of the whole batch). 80/95 exist because you want to start compressing while you still have room to think, not while a write is being refused.

---

## Known sharp edges

All observed, not theorized:

1. **`memory()` has `add` / `patch` / `remove` — no `replace`.** Calling `replace` errors out and points you at `patch`.
2. **`patch` replaces a span.** Partial `old_text` → the old tail stays, the entry grows, and it returns success. Rewriting an entry requires the *complete* entry as `old_text`.
3. **Exact-match dedup only, no semantic dedup.** You must hunt near-duplicates yourself before writing.
4. **Writes land immediately but only reach the system prompt next session.** Memory is a frozen snapshot; you can't read back what you wrote this turn.
5. **Characters, not bytes.** A CJK-heavy memory file is ~3× its byte size. Use the `current/limit` the tool reports, not `os.path.getsize`.
6. **Never batch-edit memory from a background proposal.** A fork with no shell can write but cannot verify; auto-generated memory edits have been observed corrupting content. Keep a human in the loop.
7. **A pointer is not delivery.** "It's in Hindsight" proves the content is stored and retrievable, not that prefetch will surface it when needed.
8. **Writing a `patch` `old_text` from the in-session snapshot fails.** Always read the file on disk before patching. (Observed: one 3-operation atomic batch rolled back entirely because of this.)
9. **The yellow-line check only fires after a `memory()` write.** Background fork writes bypass the checkpoint entirely. To check proactively, run `hermes memory status`.
10. **`patch` `old_text` must match the on-disk entry verbatim.** The fact you want to edit may be folded into another entry — patching from memory of what it "should" say usually just fails to match.

---

## When *not* to use this

- You want memory to grow and prefer retrieval over curation — use a memory provider (Hindsight, Mem0, …) and skip the kit.
- You're on a throwaway profile, or your memory files are tiny and fresh.
- You expect automation. The gate runs on writes; nothing cleans memory on its own — cleanup is called deliberately.

---

## Files

```
plugins/
  memory-review/                      the write gate (plugin + slash commands)
    __init__.py · plugin.yaml
    README.md · README.zh-CN.md
skills/
  memory-write-discipline/SKILL.md    original, MIT
  memory-cleanup/SKILL.md             fork of TechNickAI's v0.1.2, MIT
README.md · README.zh-CN.md           this file (EN) + 中文说明
THIRD-PARTY.md                        attribution + the local changes
CHANGELOG.md · LICENSE
```

---

## History

Born as `hermes-memory-plus` (a skill pair), renamed `hermes-memory-skills`, then `hermes-memory-kit` when the review-gate plugin joined — the contents stopped being skills-only. Old names redirect on GitHub.
