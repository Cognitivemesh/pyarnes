# Diagram assets

Each Mermaid diagram on a docs page is kept inline (fenced ` ```mermaid ` block)
so it renders natively in MkDocs Material via the `pymdownx.superfences`
custom fence, and so it shows up in PR diffs as text.

This directory holds **exportable `.mmd` sources** for diagrams that need
to survive outside the docs site — slide decks, PDFs, embedded images.

## Regenerating SVGs

Install `@mermaid-js/mermaid-cli` (ships `mmdc`):

```bash
npm install -g @mermaid-js/mermaid-cli
```

Then regenerate every SVG from its `.mmd` source:

```bash
cd docs/assets/diagrams
for f in *.mmd; do
  mmdc -i "$f" -o "${f%.mmd}.svg" --theme neutral --backgroundColor transparent
done
```

Or, when the project has `mermaid-cli` wired as a dev dep:

```bash
uv run tasks docs:diagrams
```

## Source of truth

The inline Mermaid blocks inside the `.md` pages remain the source of truth
for diagrams visible on the docs site. `.mmd` files here are copies for
off-site reuse only.
