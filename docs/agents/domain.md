# Domain Docs

How the engineering skills should consume this repo's domain documentation when exploring the codebase.

## Before exploring, read these

- **`CONTEXT.md`** at the repo root.
- **`CONTEXT-MAP.md`** at the repo root if it exists. It points at one `CONTEXT.md` per context; read each one relevant to the topic.
- **`docs/adr/`** for ADRs that touch the area being changed. In multi-context repos, also check `src/<context>/docs/adr/` for context-scoped decisions.

If any of these files do not exist, proceed silently. Do not flag their absence or suggest creating them upfront. The domain-modeling flow creates them lazily when terms or decisions actually get resolved.

## File structure

This repo currently uses a single-context layout:

```text
/
├── CONTEXT.md
├── docs/adr/
└── src/
```

If the repo later becomes multi-context, add `CONTEXT-MAP.md` at the root:

```text
/
├── CONTEXT-MAP.md
├── docs/adr/
└── src/
    ├── frontend/
    │   ├── CONTEXT.md
    │   └── docs/adr/
    └── backend/
        ├── CONTEXT.md
        └── docs/adr/
```

## Use the glossary's vocabulary

When output names a domain concept, such as an issue title, refactor proposal, hypothesis, or test name, use the term as defined in `CONTEXT.md`. Do not drift to synonyms the glossary explicitly avoids.

If the concept is not in the glossary yet, treat that as a signal: either the language is being invented and should be reconsidered, or there is a real gap to note for domain modeling.

## Flag ADR conflicts

If output contradicts an existing ADR, surface it explicitly rather than silently overriding it.
