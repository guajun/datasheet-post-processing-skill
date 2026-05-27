# Datasheet Post Processing Skill

A small workflow package for turning raw MinerU PDF-to-Markdown output into a local, navigable datasheet tree.

It captures a repeatable pattern learned while post-processing LAN9252 datasheet Markdown:

- Merge one or more raw Markdown chunks in document order.
- Detect numbered datasheet headings such as `12.0`, `12.2`, and `12.14.60.1` even when all headings were converted to `#`.
- Ignore table-of-contents lines and unnumbered OCR headings that should stay inside their parent section.
- Split content into a progressive file tree.
- Preserve parent-section prose as `00_<section>.md` before child sections.
- Download remote MinerU images into `assets/images/`.
- Rewrite image links to relative local paths.
- Emit a top-level `README.md` with the section tree and source locations.

## Repository Layout

```text
.github/skills/datasheet-post-processing/SKILL.md
.github/skills/datasheet-post-processing/scripts/post_process_mineru_markdown.py
README.md
```

## Quick Start

Run the example script with one or more raw MinerU Markdown files:

```powershell
python .github/skills/datasheet-post-processing/scripts/post_process_mineru_markdown.py `
  input/LAN9252_1-200.md `
  input/LAN9252_201-329.md `
  --output output/LAN9252 `
  --clean
```

On bash-like shells:

```bash
python .github/skills/datasheet-post-processing/scripts/post_process_mineru_markdown.py \
  input/LAN9252_1-200.md \
  input/LAN9252_201-329.md \
  --output output/LAN9252 \
  --clean
```

The output directory will contain:

```text
output/LAN9252/
├── 00_front_matter_and_toc.md
├── 00_full_manual.md
├── 01_1.0_PREFACE/
├── 02_2.0_GENERAL_DESCRIPTION.md
├── ...
├── assets/images/
└── README.md
```

## Workflow

1. Convert the PDF with MinerU to Markdown.
2. Keep the raw Markdown chunks unchanged as source material.
3. Inspect the heading style:
   - Numbered datasheets usually use `# 1.0 ...`, `# 1.1 ...`, `# 1.1.1 ...`.
   - Some OCR conversions use `#` for every visual heading, so the script rebuilds depth from the heading number, not the Markdown heading level.
   - Unnumbered headings such as `SPECIAL CSR HANDLING`, `Notes:`, or `8 AND 16-BIT ACCESS` are kept as normal content unless explicitly numbered with a dotted section number.
4. Run the post-processing script.
5. Review the generated `README.md` tree and a few deep sections.
6. If the tree has false positives, tune the heading parser before editing generated files by hand.
7. Commit the raw sources, script, generated tree, or whichever artifacts your project wants to keep.

## Output Semantics

When a section has child sections and also has its own prose before the first child heading, that prose is written as:

```text
00_<section-title>.md
```

For example, if `12.2 Distributed Clocks` has one introductory sentence before `12.2.1`, the folder becomes:

```text
02_12.2_Distributed_Clocks/
├── 00_12.2_Distributed_Clocks.md
├── 01_12.2.1_SYNC_LATCH_PIN_MULTIPLEXING.md
├── 02_12.2.2_SYNC_IRQ_MAPPING.md
└── ...
```

This avoids using `index.md` for content that is not actually a directory index.

## Skill

The Copilot skill at `.github/skills/datasheet-post-processing/SKILL.md` describes the full agent workflow: how to inspect raw MinerU Markdown, choose heading rules, localize images, split the tree, validate results, and avoid common mistakes.

## Notes

The example script uses only the Python standard library. It is intended as a practical starting point, not a complete parser for every possible datasheet style. Treat the generated file tree as reproducible output and improve the parser when the structure looks wrong.
