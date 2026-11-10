# Hermes Memory Skills

**English** · [中文](README.zh-CN.md)

A skill pair for [Hermes Agent](https://hermes-agent.nousresearch.com/docs) that keeps long-term memory **small and honest**, instead of letting it grow until writes start failing.

> This is a **skill repository**, not a plugin and not a memory provider. It ships two `SKILL.md` files plus one line of config. It doesn't touch Hermes internals and it doesn't add an automatic cleaner — upstream Hermes treats memory overflow as intended behavior, not a bug.

---

## The problem

Hermes injects `MEMORY.md` and `USER.md` into the system prompt every turn. Three consequences follow, and none are handled by defaults:

1. **Everything written is paid for forever.** "Phase 3 done" and "tried port 8080, worked" sit in the prompt on every message for the rest of the year.
2. **Nothing judges whether a fact belongs there.** A one-off debug detail and a machine-wide hard constraint look identical once written.
3. **When it fills up, it just fills up.** There's no auto-compaction. Writes start failing and you find out mid-task.

Memory quality isn't a size problem — it's a **routing** problem. That's what these skills fix.

---

## What it changes

| | Before | After |
|---|---|---|
| **Write time** | Whatever the agent thought was worth remembering | Three gates + four questions decide *whether* it's stored, *which layer* it belongs to, and *how* it loads |
| **Full memory** | Discovered when a write gets rejected | Warned at 80%; at 95% no write without freeing equal space first |
| **Cleanup** | Ad-hoc deletion, risking hard-won constraints | Routing pass: each fact moves to its smallest correct home. Deletion is the last resort, behind an approval gate |

Two skills, two jobs:

- **`memory-write-discipline`** — runs *before* a write. Value gate → ownership/scope gate → loading-cost gate. Answers "does this deserve to exist, and where does it live?"
- **`memory-cleanup`** — runs *when memory is already bloated*. Inventory → relocation plan → proposed files → checklist → apply. Dry-run by default, human approval required.

They connect through a capacity threshold: writing is cheap, so put a tripwire on it.

---

## Contents

### `memory-write-discipline` — original

The discipline layer. Four parts worth reading even if you never install it:

- **§1 Three gates.** Value / scope / loading. The rule that matters most: *you may not use a later gate to veto an earlier one* — "not worth paying tokens every turn" must not kill a fact that legitimately belongs in a scoped file.
- **§3 Four questions.** Value, derivability, duplication, cost. The negative list (PR numbers, SHAs, temp paths, task progress) contains instances of these four, not separate rules.
- **§4 Writing style.** Declarative, not imperative. `User prefers concise replies` ✓ / `Always respond concisely` ✗ — an imperative gets re-read as a live instruction and can override what the user actually just asked.
- **§5 Tool mechanics.** `patch` replaces a *span*, not a whole entry. Pass only the opening sentence and the old tail survives — the file grows and the call still returns success.

It also covers a **date-tag** policy and why the default is *no dates*: a timestamp is one signal, but it breaks `patch` addressing, creates duplicates that exact-match dedup can't catch, and — decisively — invites downstream code to treat **age as staleness**, which is exactly backwards for hard constraints that grow more valuable with age.

### `memory-cleanup` — fork

MIT fork of TechNickAI's `memory-cleanup` v0.1.2. Its core principle is worth quoting verbatim: *"This is not a deletion pass. It is a routing pass."*

Kept as a **frozen fork, not tracking upstream** — upstream no longer ships this file. Three local adaptations are documented in [`THIRD-PARTY.md`](THIRD-PARTY.md); no original rules were removed.

---

## Install

**1. Get the skills**

```bash
git clone https://github.com/Loo1015/hermes-memory-skills.git
cp -r hermes-memory-skills/skills/memory-write-discipline <SKILLS_DIR>/
cp -r hermes-memory-skills/skills/memory-cleanup           <SKILLS_DIR>/
```

`<SKILLS_DIR>` comes from `hermes config get skills_dir` (commonly `~/.hermes/skills/`). **Don't copy absolute paths out of anyone's setup, including the author's.**

Verify:

```bash
hermes skills list | grep memory
```

Both lines should read `enabled`.

**2. Check your caps**

```bash
hermes config get memory.memory_char_limit   # default 6000
hermes config get memory.user_char_limit     # default 4000
```

**3. Add the tripwire — this step is not optional**

Skills are **not a deterministic channel**. The model decides on its own whether to load one, based on the description; there is no forced trigger. A skill therefore can't be the *only* delivery mechanism for a rule you depend on.

Put one line in a layer that's injected every turn (`SOUL.md`, or global `AGENTS.md`):

```markdown
Check memory capacity after writing: at >=80% add a warning line, at >=95% free space before writing.
Bulk cleanup only via memory-cleanup (dry-run + user approval). Never auto-clean.
```

Without this line, the two `SKILL.md` files are just documentation sitting on disk.

**4. Optional first run**

Ask your agent, in-session:

> Run memory-cleanup against my MEMORY.md and USER.md as a dry-run. Produce the review artifacts. Don't change anything yet.

You get an inventory, a relocation plan, proposed files and a checklist. Nothing is written until you approve — that gate is part of the skill.

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
3. **Exact-match dedup only, no semantic dedup.** `Voce Rick speed 1.55` and `voce rick velocità 1.55` are two entries. You must hunt near-duplicates yourself before writing.
4. **Writes land immediately but only reach the system prompt next session.** Memory is a frozen snapshot; you can't read back what you wrote this turn.
5. **Characters, not bytes.** A CJK-heavy memory file is ~3× its byte size. Use the `current/limit` the tool reports, not `os.path.getsize`.
6. **Never batch-edit memory from a background proposal.** A fork with no shell can write but cannot verify; auto-generated memory edits have been observed corrupting content. Keep a human in the loop.
7. **A pointer is not delivery.** "It's in Hindsight" proves the content is stored and retrievable, not that prefetch will surface it when needed.

---

## When *not* to use this

- You want memory to grow and prefer retrieval over curation — use a memory provider (Hindsight, Mem0, …) and skip both skills.
- You're on a throwaway profile, or your memory files are tiny and fresh.
- You expect automation. Neither skill cleans memory on its own; both are called deliberately.

---

## Files

```
skills/
  memory-write-discipline/SKILL.md   original, MIT
  memory-cleanup/SKILL.md            fork of TechNickAI's v0.1.2, MIT
README.zh-CN.md                      中文说明
THIRD-PARTY.md                       attribution + the three local changes
CHANGELOG.md
LICENSE
```

## License

MIT. Fork attribution and adaptation details in [`THIRD-PARTY.md`](THIRD-PARTY.md).
