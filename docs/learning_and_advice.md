# Working with Claude on Existing Projects

Advice on the best approach when bringing an existing codebase to Claude for development work.

## Approaches

### 1. Let Claude examine the codebase

- Works well for: small/medium projects, clean code, standard patterns
- Risk: Claude may miss intent, infer wrong assumptions, or focus on implementation details over purpose

### 2. Mini spec + codebase

- Works well for: complex projects, non-obvious design decisions, unconventional patterns
- Benefit: You communicate *intent*, Claude sees *implementation*, gaps become visible

### 3. CLAUDE.md (ongoing reference)

- Best for: projects you'll work on repeatedly with Claude
- Acts as persistent context across sessions

## Recommendations

### For one-off or new-to-Claude projects

Write a brief context doc (~20-50 lines) covering:

- What the app does (1-2 sentences)
- Key files and their roles
- Non-obvious decisions ("we use X because Y")
- Current pain points or focus areas

Then let Claude explore the code with that context.

### For ongoing projects

Maintain a CLAUDE.md that evolves. You don't need a full spec - just enough to prevent Claude from making wrong assumptions.

### The hybrid pattern that works well

```
"Here's what this app does: [2 sentences].
Key files are X, Y, Z.
I want to [task].
Explore the codebase and tell me your understanding before making changes."
```

This lets you correct misunderstandings before Claude writes code.

## Vibe Coding vs Spec-Driven Development

| Approach | Description | Best For |
|----------|-------------|----------|
| **Vibe coding** | Iterative, conversational; guide as you go, make decisions in the moment | Exploration, evolving requirements, learning what you want |
| **Spec-driven** | Detailed specification upfront, AI implements autonomously | Clear requirements, reproducible builds, larger features |

Most real projects use a mix of both - start with enough spec to establish direction, then iterate on details.
