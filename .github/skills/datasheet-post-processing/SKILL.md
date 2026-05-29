---
name: datasheet-post-processing
description: 'Skill-first workflow for post-processing raw MinerU PDF-to-Markdown datasheet output. Use when: inspecting converted datasheets, adapting a sample splitter script, building a numbered section file tree, localizing MinerU images, cleaning table-of-contents noise, preserving parent-section prose, validating generated manuals.'
argument-hint: 'raw markdown files and output directory'
---

# Datasheet Post Processing

Use this skill when a user has one or more raw MinerU PDF-to-Markdown files and wants a clean, local, navigable manual tree.

The goal is reproducible post-processing guided by inspection, not a universal parser and not hand-editing generated fragments. The included Python script is a sample starting point; adapt it to the current document's actual heading, TOC, and image patterns.

## Expected Inputs

- One or more raw Markdown files from MinerU, in document order.
- Optional reference output style from a previous processed manual.
- Desired output directory name.

## Expected Output

- A merged full Markdown file, usually `00_full_manual.md`.
- A front matter and original TOC file, usually `00_front_matter_and_toc.md`.
- A numbered folder/file tree where each section can be opened progressively.
- Local image files under `assets/images/` unless the user requests remote links.
- A top-level `README.md` with the section tree and source file locations.

## Core Rules

1. Preserve the raw MinerU files unchanged.
2. Rebuild section hierarchy from heading text, not from Markdown heading depth, because MinerU often converts every visual heading to `#`.
3. Treat explicit dotted section numbers as structural headings:
   - `1.0 Title` is a level-1 section.
   - `1.1 Title` is a level-2 section.
   - `12.14.60.1 Title` is a level-4 section.
4. Do not treat bare numeric text as structural headings:
   - `8 AND 16-BIT ACCESS` is content, not section `8.0`.
   - `1.8V to 3.3V variable voltage I/O` is content, not section `1.8`.
5. Ignore clear original TOC lines, especially dotted-leader or visibly separated page-number rows such as `5.0 Register Map .... 32`. Be conservative with ambiguous single-space lines such as `12.0 EtherCAT 196`; prefer keeping possible real section headings and flagging TOC noise during validation over deleting real content.
6. Keep unnumbered headings inside their current numbered section unless the manual clearly uses a different scheme.
7. When a parent section has prose before child sections, write it as `00_<section-title>.md`, not `index.md`.
8. Keep generated path components short for Windows/Git compatibility. Use section numbers plus a short title slug and hash; keep the full section title inside the Markdown and README tree.
9. Prefer generated output over manual edits; tune or replace the sample parser and regenerate when the tree looks wrong.

## Workflow

1. Inspect the raw Markdown.
   - Search for headings with `^#{1,6}\s+`.
   - Identify the structural heading pattern.
   - Check whether the document is split across multiple Markdown files.
   - Count image links and determine whether they are remote MinerU URLs, file URLs, or relative paths.

2. Choose the heading parser.
   - For datasheets with `N.0`, `N.M`, `N.M.K` headings, use dotted-number parsing.
   - Collapse `N.0` to level 1 but keep the title text as `N.0 Title`.
   - Use the number tuple for ordering, not lexical filename order.
   - Avoid adding broad TOC heuristics to the default sample script. Document-specific rules are acceptable when validation proves they are needed.

3. Merge source files.
   - Preserve source order.
   - Add an HTML comment separator such as `<!-- Source split: second-file.md -->` between chunks.
   - Track source file and source line for each generated section.

4. Localize images.
   - Download `http` and `https` images into `assets/images/`.
   - Copy `file:` or local relative images into the same directory.
   - Use nearby labels such as `FIGURE 12-5: ...` or `TABLE 12-3: ...` in image filenames.
   - Add a short hash from the original URL to avoid collisions.
   - Rewrite all image links to relative paths from each generated Markdown file.

5. Split sections.
   - Text before the first structural heading goes to the front matter file.
   - Each leaf section becomes `<ordinal>_<section-title>.md`.
   - Each parent section becomes `<ordinal>_<section-title>/`.
   - Parent prose before child sections becomes `00_<section-title>.md` inside that folder.
   - If paths may be committed on Windows, cap each generated section stem to a short length such as 42 characters.

6. Build the output README.
   - Include source files.
   - Include full manual and front matter filenames.
   - Include localized image count.
   - Render the full section tree with source locations.

7. Validate.
   - Verify expected top-level section count against the original TOC.
   - Search for false positives such as repeated `8.0 AND 16-BIT ACCESS`.
   - Search for remaining `index.md`; there should usually be none.
   - Search for remote image links if images were supposed to be localized.
   - Open one shallow section and one deep section to confirm relative images resolve.

## Sample Script

Use or adapt [post_process_mineru_markdown.py](./scripts/post_process_mineru_markdown.py). Treat it as a starter script for common MinerU datasheet output, not as a complete Markdown parser.

Typical command:

```bash
python .github/skills/datasheet-post-processing/scripts/post_process_mineru_markdown.py raw_part1.md raw_part2.md --output output/manual --clean
```

## Common Fixes

- If top-level section count is too high, the heading regex is too permissive. Require an explicit dotted number such as `\d+\.\d+`, then validate before adding broader TOC filters.
- If `1.1` appears as a top-level section, convert `N.0` to level 1 and `N.M` to level 2.
- If parent directories contain only child files and no parent overview, that is fine when the parent had no prose before the first child.
- If a parent overview is named `index.md`, rename the generator output to `00_<section>.md` so users do not mistake it for a table of contents.
- If `git add` fails with `Filename too long`, shorten generated path components and regenerate; do not rely on every collaborator enabling long-path support.
- If image names are generic, improve nearby context extraction around figure and table labels.
- If generated file paths are too long, shorten only the filename stem, not the visible section title inside the Markdown.
- If a TOC line and a real section title are ambiguous, keep the title and catch the duplicate/noise during validation. Losing real sections is worse than leaving extra generated files.

## Completion Criteria

A task is complete when the generated manual can be opened progressively from the output README, images are local or intentionally remote, the section tree matches the original TOC, and the generation command can be rerun without manual cleanup.
