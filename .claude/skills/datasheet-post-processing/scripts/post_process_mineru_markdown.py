from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse
from urllib.request import urlopen


IMAGE_PATTERN = re.compile(
    r'!\[(?P<alt>[^\]]*)\]\((?P<url>[^)\n]+?)(?:\s+"(?P<title>[^"]*)")?\)'
)
HTML_IMAGE_PATTERN = re.compile(
    r'(?P<prefix><img\b[^>]*?\bsrc=")(?P<url>[^"]+)(?P<suffix>"[^>]*>)',
    re.IGNORECASE,
)
HEADING_PATTERN = re.compile(r"^(?P<marks>#{1,6})\s+(?P<title>.+?)\s*$")
NUMBERED_HEADING_PATTERN = re.compile(
    r"^(?P<number>\d+\.\d+(?:\.\d+)*)\s+(?P<title>.+?)\s*$"
)
TOC_LINE_PATTERN = re.compile(r"^\d+(?:\.\d+)*\s+.+?(?:\.{1,}|\s{2,})\s*\d{1,4}\s*$")
INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
DEFAULT_SOURCE_SEPARATOR = "\n\n<!-- Source split: {name} -->\n\n"
MAX_SECTION_STEM_LENGTH = 42


@dataclass
class Section:
    title: str
    level: int
    order_key: tuple[int, ...]
    source_file: str
    source_line: int
    children: list["Section"] = field(default_factory=list)
    content_lines: list[str] = field(default_factory=list)
    parent: "Section | None" = None

    def add_child(self, child: "Section") -> None:
        child.parent = self
        self.children.append(child)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sample script for splitting raw MinerU Markdown into a datasheet file tree."
    )
    parser.add_argument(
        "inputs",
        type=Path,
        nargs="+",
        help="Raw MinerU Markdown files in document order.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output directory for the processed manual tree.",
    )
    parser.add_argument(
        "--raw-name",
        default="00_full_manual.md",
        help="Merged and localized full Markdown file name.",
    )
    parser.add_argument(
        "--front-name",
        default="00_front_matter_and_toc.md",
        help="Front matter and original table-of-contents file name.",
    )
    parser.add_argument(
        "--images-dir",
        default="assets/images",
        help="Image directory under the output root.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Image download timeout in seconds.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove the output directory before writing.",
    )
    parser.add_argument(
        "--keep-remote-images",
        action="store_true",
        help="Do not download images; only split Markdown.",
    )
    return parser.parse_args()


def read_sources(input_paths: list[Path]) -> tuple[str, list[tuple[str, int, Path]]]:
    parts: list[str] = []
    source_map: list[tuple[str, int, Path]] = []

    for index, input_path in enumerate(input_paths):
        text = input_path.read_text(encoding="utf-8").rstrip()
        if index:
            separator = DEFAULT_SOURCE_SEPARATOR.format(name=input_path.name).rstrip("\n")
            parts.append(separator)
            source_map.extend([("generated", 0, Path.cwd())] * len(separator.splitlines()))
        parts.append(text)
        source_map.extend(
            (input_path.name, line_number, input_path.parent)
            for line_number, _ in enumerate(text.splitlines(), start=1)
        )

    merged = "\n".join(parts).rstrip() + "\n"
    return merged, source_map


def normalize_title(text: str) -> str:
    text = text.replace("\u3000", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text.rstrip(". ")


def parse_numbered_heading(raw_title: str) -> tuple[int, tuple[int, ...], str] | None:
    raw_toc_title = raw_title.replace("\u3000", " ").strip()
    if TOC_LINE_PATTERN.match(raw_toc_title):
        return None

    title = normalize_title(raw_title)
    if TOC_LINE_PATTERN.match(title):
        return None

    match = NUMBERED_HEADING_PATTERN.match(title)
    if not match:
        return None

    number_text = match.group("number")
    raw_parts = tuple(int(part) for part in number_text.split("."))
    if not raw_parts:
        return None

    tail = match.group("title").strip()
    if len(raw_parts) == 2 and raw_parts[1] == 0:
        parts = (raw_parts[0],)
        normalized_number = f"{raw_parts[0]}.0"
    else:
        parts = raw_parts
        normalized_number = ".".join(str(part) for part in raw_parts)

    return len(parts), parts, f"{normalized_number} {tail}"


def build_sections(lines: list[str], source_map: list[tuple[str, int, Path]]) -> tuple[list[str], list[Section]]:
    preface_lines: list[str] = []
    roots: list[Section] = []
    stack: list[Section] = []
    current: Section | None = None

    for index, line in enumerate(lines):
        source_file, source_line, _ = source_map[index] if index < len(source_map) else ("generated", 0, Path.cwd())
        heading_match = HEADING_PATTERN.match(line)
        if heading_match:
            heading_info = parse_numbered_heading(heading_match.group("title"))
            if heading_info is not None:
                level, order_key, title = heading_info
                section = Section(
                    title=title,
                    level=level,
                    order_key=order_key,
                    source_file=source_file,
                    source_line=source_line,
                )
                while stack and stack[-1].level >= section.level:
                    stack.pop()
                if stack:
                    stack[-1].add_child(section)
                else:
                    roots.append(section)
                stack.append(section)
                current = section
                continue

        if current is None:
            preface_lines.append(line)
        else:
            current.content_lines.append(line)

    return preface_lines, roots


def sanitize_filename(text: str) -> str:
    text = normalize_title(text)
    text = text.replace("#", "")
    text = INVALID_PATH_CHARS.sub("_", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._ ")
    return text or "untitled"


def shorten_filename_stem(text: str, limit: int = 72) -> str:
    if len(text) <= limit:
        return text
    shortened = text[:limit].rstrip("_")
    return shortened or text[:limit]


def section_path_stem(section: Section, limit: int = MAX_SECTION_STEM_LENGTH) -> str:
    number = ".".join(str(part) for part in section.order_key)
    if len(section.order_key) == 1:
        number = f"{number}.0"
    title_tail = section.title.removeprefix(number).strip()
    safe_tail = sanitize_filename(title_tail)
    safe_number = sanitize_filename(number)
    base = safe_number if not safe_tail else f"{safe_number}_{safe_tail}"
    if len(base) <= limit:
        return base
    digest = hashlib.sha1(section.title.encode("utf-8")).hexdigest()[:6]
    reserved = len(safe_number) + len(digest) + 2
    tail_limit = max(8, limit - reserved)
    short_tail = shorten_filename_stem(safe_tail, tail_limit)
    return f"{safe_number}_{short_tail}_{digest}"


def trim_blank_lines(lines: Iterable[str]) -> list[str]:
    values = list(lines)
    while values and not values[0].strip():
        values.pop(0)
    while values and not values[-1].strip():
        values.pop()
    return values


def clean_context_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^#+\s*", "", text)
    text = re.sub(r"^[\-\*•●]\s*", "", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_context_label(line: str) -> str | None:
    stripped = line.strip()
    if not stripped:
        return None
    if IMAGE_PATTERN.search(stripped):
        return None
    if stripped.startswith("|") or stripped.startswith("<table") or stripped.startswith("</table"):
        return None
    if stripped in {"---", "***"}:
        return None

    text = clean_context_text(stripped)
    if not text or "http://" in text or "https://" in text:
        return None
    if len(text) > 72 and not text.startswith(("FIGURE", "Figure", "TABLE", "Table")):
        return None
    return text


def choose_image_label(current_heading: str | None, recent_context: str | None) -> str:
    if recent_context and (recent_context.startswith(("FIGURE", "Figure", "TABLE", "Table")) or len(recent_context) <= 48):
        return recent_context
    if current_heading:
        return current_heading
    if recent_context:
        return recent_context
    return "image"


def extract_extension(source: str, fallback: str = ".bin") -> str:
    parsed = urlparse(source)
    suffix = Path(unquote(parsed.path)).suffix.lower()
    if suffix and len(suffix) <= 8:
        return suffix
    return fallback


def localize_images(
    markdown: str,
    images_dir: Path,
    timeout: float,
    source_map: list[tuple[str, int, Path]],
) -> tuple[str, dict[str, Path]]:
    images_dir.mkdir(parents=True, exist_ok=True)
    localized: dict[str, Path] = {}
    rewritten_lines: list[str] = []
    current_heading = "front-matter"
    recent_context: str | None = None
    image_index = 0

    for line_index, line in enumerate(markdown.splitlines()):
        source_dir = source_map[line_index][2] if line_index < len(source_map) else Path.cwd()
        heading_match = HEADING_PATTERN.match(line)
        if heading_match:
            current_heading = normalize_title(heading_match.group("title")) or current_heading

        def markdown_image_replacer(match: re.Match[str]) -> str:
            nonlocal image_index
            image_index += 1
            url = match.group("url")
            alt = match.group("alt")
            label = choose_image_label(current_heading, recent_context)
            target = ensure_local_image(url, images_dir, timeout, localized, label, image_index, source_dir)
            return f"![{alt}]({target.as_posix()})"

        def html_image_replacer(match: re.Match[str]) -> str:
            nonlocal image_index
            image_index += 1
            url = match.group("url")
            label = choose_image_label(current_heading, recent_context)
            target = ensure_local_image(url, images_dir, timeout, localized, label, image_index, source_dir)
            return f"{match.group('prefix')}{target.as_posix()}{match.group('suffix')}"

        line = IMAGE_PATTERN.sub(markdown_image_replacer, line)
        rewritten_lines.append(HTML_IMAGE_PATTERN.sub(html_image_replacer, line))

        context_label = extract_context_label(line)
        if context_label:
            recent_context = context_label

    return "\n".join(rewritten_lines), localized


def ensure_local_image(
    source: str,
    images_dir: Path,
    timeout: float,
    localized: dict[str, Path],
    label: str,
    image_index: int,
    source_dir: Path,
) -> Path:
    if source in localized:
        return localized[source]

    extension = extract_extension(source)
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
    stem = shorten_filename_stem(sanitize_filename(label), limit=56)
    target_name = f"{image_index:04d}_{stem}_{digest}{extension}"
    target_path = images_dir / target_name

    parsed = urlparse(source)
    if parsed.scheme in {"http", "https"}:
        if not target_path.exists():
            with urlopen(source, timeout=timeout) as response:
                target_path.write_bytes(response.read())
    elif parsed.scheme == "file":
        local_path = Path(unquote(parsed.path))
        if os.name == "nt" and local_path.parts and local_path.parts[0] == "/":
            local_path = Path(local_path.as_posix().lstrip("/"))
        if not target_path.exists():
            shutil.copyfile(local_path, target_path)
    else:
        local_path = Path(source)
        if not local_path.is_absolute():
            local_path = (source_dir / local_path).resolve()
        if not target_path.exists():
            shutil.copyfile(local_path, target_path)

    localized[source] = target_path
    return target_path


def rewrite_image_paths(markdown: str, from_dir: Path) -> str:
    def replacer(match: re.Match[str]) -> str:
        alt = match.group("alt")
        url = match.group("url")
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"}:
            return match.group(0)
        target = Path(url)
        relative = os.path.relpath(target, from_dir)
        return f"![{alt}]({Path(relative).as_posix()})"

    markdown = IMAGE_PATTERN.sub(replacer, markdown)

    def html_replacer(match: re.Match[str]) -> str:
        url = match.group("url")
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"}:
            return match.group(0)
        target = Path(url)
        relative = os.path.relpath(target, from_dir)
        return f"{match.group('prefix')}{Path(relative).as_posix()}{match.group('suffix')}"

    return HTML_IMAGE_PATTERN.sub(html_replacer, markdown)


def render_section_markdown(section: Section) -> str:
    parts = [f"# {section.title}", ""]
    body = trim_blank_lines(section.content_lines)
    if body:
        parts.extend(body)
        if body[-1].strip():
            parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def section_sort_key(section: Section) -> tuple[int, ...]:
    return section.order_key


def write_section_tree(sections: list[Section], output_root: Path) -> int:
    count = 0
    for index, section in enumerate(sorted(sections, key=section_sort_key), start=1):
        count += write_section(section, output_root, index)
    return count


def write_section(section: Section, parent_dir: Path, sibling_index: int) -> int:
    folder_stem = section_path_stem(section)
    node_name = f"{sibling_index:02d}_{folder_stem}"

    if section.children:
        section_dir = parent_dir / node_name
        section_dir.mkdir(parents=True, exist_ok=True)
        if trim_blank_lines(section.content_lines):
            content = rewrite_image_paths(render_section_markdown(section), section_dir)
            intro_name = f"00_{folder_stem}.md"
            (section_dir / intro_name).write_text(content, encoding="utf-8")
            written = 1
        else:
            written = 0
        for child_index, child in enumerate(sorted(section.children, key=section_sort_key), start=1):
            written += write_section(child, section_dir, child_index)
        return written

    file_path = parent_dir / f"{node_name}.md"
    content = rewrite_image_paths(render_section_markdown(section), parent_dir)
    file_path.write_text(content, encoding="utf-8")
    return 1


def build_readme(
    output_root: Path,
    input_paths: list[Path],
    raw_name: str,
    front_name: str,
    sections: list[Section],
    image_count: int,
    keep_remote_images: bool,
) -> str:
    source_names = ", ".join(path.name for path in input_paths)
    image_line = "Remote images kept" if keep_remote_images else f"Localized images: {image_count}"
    lines = [
        f"# {output_root.name}",
        "",
        f"- Source files: {source_names}",
        f"- Full processed manual: {raw_name}",
        f"- Front matter and original TOC: {front_name}",
        f"- {image_line}",
        "",
        "## Section Tree",
        "",
    ]
    lines.extend(render_tree_lines(sections))
    lines.append("")
    return "\n".join(lines)


def render_tree_lines(sections: list[Section], depth: int = 0) -> list[str]:
    lines: list[str] = []
    for section in sorted(sections, key=section_sort_key):
        indent = "  " * depth
        location = f" ({section.source_file}:{section.source_line})" if section.source_line else ""
        lines.append(f"{indent}- {section.title}{location}")
        if section.children:
            lines.extend(render_tree_lines(section.children, depth + 1))
    return lines


def handle_remove_readonly(function, path: str, error: BaseException) -> None:
    if not isinstance(error, PermissionError):
        raise error

    target = Path(path)
    target.chmod(stat.S_IWRITE | stat.S_IREAD)
    function(path)


def prepare_output_dir(output_root: Path, clean: bool) -> None:
    if clean and output_root.exists():
        shutil.rmtree(output_root, onexc=handle_remove_readonly)
    output_root.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = parse_args()
    input_paths = [path.resolve() for path in args.inputs]
    output_root = args.output.resolve()
    prepare_output_dir(output_root, args.clean)

    merged_text, source_map = read_sources(input_paths)
    if args.keep_remote_images:
        processed_text = merged_text
        localized_images: dict[str, Path] = {}
    else:
        images_dir = output_root / args.images_dir
        processed_text, localized_images = localize_images(merged_text, images_dir, args.timeout, source_map)

    raw_path = output_root / args.raw_name
    raw_path.write_text(processed_text.rstrip() + "\n", encoding="utf-8")

    lines = processed_text.splitlines()
    preface_lines, sections = build_sections(lines, source_map)

    front_path = output_root / args.front_name
    front_content = "\n".join(trim_blank_lines(preface_lines)).rstrip() + "\n"
    front_path.write_text(rewrite_image_paths(front_content, output_root), encoding="utf-8")

    section_file_count = write_section_tree(sections, output_root)

    readme_path = output_root / "README.md"
    readme_path.write_text(
        build_readme(
            output_root,
            input_paths,
            args.raw_name,
            args.front_name,
            sections,
            len(localized_images),
            args.keep_remote_images,
        ),
        encoding="utf-8",
    )

    print(f"Input files: {', '.join(str(path) for path in input_paths)}")
    print(f"Output directory: {output_root}")
    print(f"Top-level sections: {len(sections)}")
    print(f"Section files: {section_file_count}")
    print(f"Localized images: {len(localized_images)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
