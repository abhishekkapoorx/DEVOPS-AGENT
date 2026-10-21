# Domain Docs

This is a single-context repository. Domain documentation lives at the repository root and in the root ADR directory.

## Before exploring

- Read `GLOSSARY.md` when using or introducing domain terminology.
- Read ADRs in `docs/adr/` that touch the area being changed.
- If these files are empty or have no relevant entries, proceed without flagging their absence.

## File structure

```text
/
├── GLOSSARY.md
├── docs/
│   └── adr/
└── src/
```

## Use the glossary vocabulary

Use domain concepts as defined in `GLOSSARY.md` in issue titles, proposals, refactors, and tests. If a needed concept is missing, record that gap for domain modeling rather than silently inventing competing terminology.

## Flag ADR conflicts

If proposed work contradicts an existing ADR, surface the conflict explicitly instead of silently overriding the decision.
