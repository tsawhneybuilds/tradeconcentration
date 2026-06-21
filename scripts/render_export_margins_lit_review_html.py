#!/usr/bin/env python3
"""Render the detailed export-margins project notes as a notes-first HTML file."""

from __future__ import annotations

import html
import re
from pathlib import Path

from markdown_it import MarkdownIt


ROOT = Path(__file__).resolve().parents[1]
GUIDE_PATH = ROOT / "literature" / "export_margins" / "detailed_project_notes.md"
COMPACT_GUIDE_PATH = ROOT / "literature" / "export_margins" / "project_study_guide.md"
SOURCE_REGISTRY_PATH = ROOT / "literature" / "export_margins" / "source_registry.md"
WIKI_DIR = ROOT / "literature" / "export_margins" / "wiki"
PAPER_DIR = WIKI_DIR / "papers"
OUTPUT_DIR = WIKI_DIR / "html"
OUTPUT_FILE = OUTPUT_DIR / "export_margins_lit_review.html"
URL_RE = re.compile(r"https?://[^\s|]+")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug or "section"


def extract_source_links() -> dict[str, str]:
    """Return the primary source URL for each normalized PDF in the registry."""
    if not SOURCE_REGISTRY_PATH.exists():
        return {}

    links: dict[str, str] = {}
    for line in SOURCE_REGISTRY_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|---"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 4 or not cells[0].isdigit():
            continue

        source_pdf = cells[1].strip("`")
        urls = URL_RE.findall(cells[3])
        if source_pdf and urls:
            links[source_pdf] = urls[0]
    return links


def extract_paper_metadata() -> list[dict[str, str]]:
    source_links = extract_source_links()
    papers: list[dict[str, str]] = []
    for path in sorted(PAPER_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        end = text.find("\n---\n", 4)
        if end == -1:
            continue
        meta: dict[str, str] = {"file": path.name, "path": str(path.relative_to(ROOT))}
        for line in text[4:end].splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip('"').strip("'")
        source_pdf = meta.get("source_pdf", "")
        if source_pdf in source_links:
            meta["source_url"] = source_links[source_pdf]
        papers.append(meta)
    return papers


def paper_title_link(title: str, source_url: str) -> str:
    escaped_title = html.escape(title)
    if not source_url:
        return escaped_title
    escaped_url = html.escape(source_url, quote=True)
    return (
        f'<a class="paper-title-link" href="{escaped_url}" '
        f'target="_blank" rel="noopener noreferrer">{escaped_title}</a>'
    )


def text_tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def author_last_name_token_groups(authors: str) -> list[list[str]]:
    groups: list[list[str]] = []
    for author in re.split(r"\s*;\s*|\s+and\s+", authors, flags=re.IGNORECASE):
        words = re.findall(r"[A-Za-z]+(?:-[A-Za-z]+)?", author)
        if words:
            groups.append(text_tokens(words[-1]))
    return groups


def source_url_for_heading(title: str, papers: list[dict[str, str]]) -> str:
    heading_tokens = set(text_tokens(title))
    for paper in papers:
        source_url = paper.get("source_url", "")
        year = paper.get("year", "")
        author_groups = author_last_name_token_groups(paper.get("authors", ""))
        if not source_url or not author_groups:
            continue
        if year and year not in heading_tokens:
            continue
        if all(all(token in heading_tokens for token in group) for group in author_groups):
            return source_url
    return ""


def add_heading_anchors(
    markdown: str,
    papers: list[dict[str, str]] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    nav: list[dict[str, str]] = []
    used: dict[str, int] = {}
    out_lines: list[str] = []
    for line in markdown.splitlines():
        match = re.match(r"^(#{2,3})\s+(.+?)\s*$", line)
        if not match:
            out_lines.append(line)
            continue
        level = len(match.group(1))
        title = re.sub(r"`([^`]+)`", r"\1", match.group(2)).strip()
        anchor = slugify(title)
        count = used.get(anchor, 0)
        used[anchor] = count + 1
        if count:
            anchor = f"{anchor}-{count + 1}"
        nav.append({"level": str(level), "title": title, "anchor": anchor})
        out_lines.append(f'<span id="{anchor}" class="anchor"></span>')
        source_url = source_url_for_heading(title, papers or []) if level == 2 else ""
        if level == 2 and source_url:
            out_lines.append(f"<h2>{paper_title_link(title, source_url)}</h2>")
        else:
            out_lines.append(line)
    return "\n".join(out_lines), nav


def formula_block_html(kind: str) -> str:
    formulas = {
        "country_year_total": (
            '<div class="formula-block">'
            '<div class="formula-line"><var>X</var><sub>ct</sub> = '
            '<span class="op">&sum;</span><sub>p</sub> <span class="op">&sum;</span><sub>d</sub> '
            '<var>x</var><sub>cpdt</sub></div>'
            "</div>"
        ),
        "relationship_average": (
            '<div class="formula-block">'
            '<div class="formula-line"><span class="text-term">exports</span> = '
            '<span class="text-term">number of active relationships</span> '
            '<span class="op">&times;</span> '
            '<span class="text-term">average value per active relationship</span></div>'
            '<div class="formula-line"><var>X</var><sub>ct</sub> = <var>N</var><sub>ct</sub> '
            '<span class="op">&times;</span> '
            '<span class="func">mean</span>(<var>x</var><sub>cpdt</sub> '
            '<span class="op">&mid;</span> <var>x</var><sub>cpdt</sub> &gt; 0)</div>'
            "</div>"
        ),
        "growth_decomposition": (
            '<div class="formula-block">'
            '<div class="formula-line"><span class="op">&Delta;</span><var>X</var> = '
            '<span class="op">&sum;</span><sub>continuing</sub> '
            '(<var>x</var><sub>t</sub> - <var>x</var><sub>0</sub>)</div>'
            '<div class="formula-line indent">+ '
            '<span class="op">&sum;</span><sub>entries</sub> <var>x</var><sub>t</sub></div>'
            '<div class="formula-line indent">- '
            '<span class="op">&sum;</span><sub>exits</sub> <var>x</var><sub>0</sub></div>'
            "</div>"
        ),
        "survival": (
            '<div class="formula-block">'
            '<div class="formula-line"><span class="func">survival</span><sub>h</sub> = '
            '<strong>1</strong>[<var>x</var><sub>p,d,t+h</sub> &gt; 0 '
            '<span class="op">&mid;</span> <var>x</var><sub>p,d,t</sub> '
            '<span class="text-term">first becomes active</span>]</div>'
            "</div>"
        ),
    }
    return formulas[kind]


def replace_formula_fences(markdown: str) -> str:
    def repl(match: re.Match[str]) -> str:
        block = match.group(1).strip()
        collapsed = re.sub(r"\s+", " ", block)
        if collapsed == "X_ct = sum_p sum_d x_cpdt":
            return formula_block_html("country_year_total")
        if collapsed == "exports = number of active relationships x average value per active relationship X_ct = N_ct * mean(x_cpdt | x_cpdt > 0)":
            return formula_block_html("relationship_average")
        if collapsed == "Delta X = sum_continuing (x_t - x_0) + sum_entries x_t - sum_exits x_0":
            return formula_block_html("growth_decomposition")
        if collapsed == "survival_h = 1[x_{p,d,t+h} > 0 | x_{p,d,t} first becomes active]":
            return formula_block_html("survival")
        return match.group(0)

    return re.sub(r"```text\n(.*?)\n```", repl, markdown, flags=re.DOTALL)


def paper_metadata_table(papers: list[dict[str, str]]) -> str:
    if not papers:
        return ""
    rows = []
    for idx, paper in enumerate(papers, start=1):
        title = paper.get("title", paper.get("file", f"Paper {idx}"))
        authors = paper.get("authors", "")
        year = paper.get("year", "")
        source = paper.get("source_pdf", "")
        source_url = paper.get("source_url", "")
        rows.append(
            "<tr>"
            f"<td>{idx}</td>"
            f"<td>{paper_title_link(title, source_url)}</td>"
            f"<td>{html.escape(authors)}</td>"
            f"<td>{html.escape(year)}</td>"
            f"<td><code>{html.escape(source)}</code></td>"
            "</tr>"
        )
    return (
        '<section class="metadata-panel">'
        '<h2>Paper Metadata</h2>'
        '<p>Compact metadata only. The full extracted paper bodies are not embedded in this HTML.</p>'
        '<div class="table-scroll"><table>'
        '<thead><tr><th>#</th><th>Paper</th><th>Authors</th><th>Year</th><th>Source PDF</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody>"
        "</table></div></section>"
    )


def render() -> Path:
    if not GUIDE_PATH.exists():
        raise FileNotFoundError(GUIDE_PATH)

    papers = extract_paper_metadata()
    guide_markdown = GUIDE_PATH.read_text(encoding="utf-8")
    guide_markdown = replace_formula_fences(guide_markdown)
    guide_markdown, nav = add_heading_anchors(guide_markdown, papers)
    md = MarkdownIt("commonmark", {"html": True, "breaks": False}).enable("table").enable("strikethrough")
    guide_html = md.render(guide_markdown)
    metadata_html = paper_metadata_table(papers)

    nav_items = "\n".join(
        f'<a class="level-{item["level"]}" href="#{item["anchor"]}">{html.escape(item["title"])}</a>'
        for item in nav
    )

    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Detailed Export Margins Notes-First Guide</title>
  <style>
    :root {{
      --ink: #20252a;
      --muted: #5c6670;
      --line: #d9e0e6;
      --sidebar: #f5f7f9;
      --accent: #124d74;
      --accent-soft: #e5f0f6;
      --table-head: #eef3f6;
      --code: #f1f4f6;
    }}
    * {{ box-sizing: border-box; }}
    html {{ scroll-behavior: smooth; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: #fff;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      line-height: 1.55;
    }}
    .layout {{
      display: grid;
      grid-template-columns: minmax(270px, 340px) minmax(0, 1fr);
      min-height: 100vh;
    }}
    aside {{
      position: sticky;
      top: 0;
      height: 100vh;
      overflow: auto;
      padding: 24px 18px;
      background: var(--sidebar);
      border-right: 1px solid var(--line);
    }}
    aside h1 {{
      margin: 0 0 8px;
      font-size: 20px;
      line-height: 1.2;
      letter-spacing: 0;
    }}
    aside p {{
      margin: 0 0 18px;
      color: var(--muted);
      font-size: 13px;
    }}
    nav a {{
      display: block;
      color: var(--ink);
      text-decoration: none;
      border-radius: 6px;
      line-height: 1.25;
    }}
    nav a:hover {{
      color: var(--accent);
      background: var(--accent-soft);
    }}
    nav .level-2 {{
      margin-top: 8px;
      padding: 8px 8px;
      font-size: 13px;
      font-weight: 700;
    }}
    nav .level-3 {{
      padding: 6px 8px 6px 22px;
      color: var(--muted);
      font-size: 12px;
    }}
    main {{
      width: 100%;
      max-width: 980px;
      padding: 34px 42px 80px;
    }}
    .intro {{
      margin-bottom: 28px;
      padding-bottom: 24px;
      border-bottom: 1px solid var(--line);
    }}
    .intro h1 {{
      margin: 0 0 8px;
      font-size: 34px;
      line-height: 1.15;
      letter-spacing: 0;
    }}
    .intro p {{
      margin: 0;
      color: var(--muted);
    }}
    .note {{
      display: inline-block;
      margin-top: 14px;
      padding: 8px 10px;
      border: 1px solid var(--line);
      border-radius: 6px;
      color: var(--muted);
      background: #fbfcfd;
      font-size: 13px;
    }}
    .markdown-body h1 {{
      display: none;
    }}
    .markdown-body h2,
    .metadata-panel h2 {{
      margin: 34px 0 12px;
      padding-top: 4px;
      font-size: 24px;
      line-height: 1.25;
      letter-spacing: 0;
    }}
    .markdown-body h3 {{
      margin: 24px 0 8px;
      padding-top: 6px;
      font-size: 18px;
      line-height: 1.35;
      letter-spacing: 0;
      color: var(--accent);
    }}
    .markdown-body h2 a.paper-title-link,
    .metadata-panel a.paper-title-link {{
      color: inherit;
      text-decoration-color: var(--accent);
      text-decoration-thickness: 1px;
      text-underline-offset: 3px;
    }}
    .markdown-body h2 a.paper-title-link:hover,
    .metadata-panel a.paper-title-link:hover {{
      color: var(--accent);
    }}
    .markdown-body p,
    .markdown-body li,
    .metadata-panel p {{
      font-size: 15px;
    }}
    .markdown-body ul,
    .markdown-body ol {{
      padding-left: 24px;
    }}
    .markdown-body li {{
      margin: 4px 0;
    }}
    .markdown-body code,
    .metadata-panel code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
      font-size: 0.92em;
      background: var(--code);
      padding: 0.12em 0.28em;
      border-radius: 4px;
    }}
    .markdown-body pre {{
      overflow-x: auto;
      margin: 16px 0;
      padding: 14px;
      border-radius: 6px;
      background: var(--code);
    }}
    .markdown-body pre code {{
      padding: 0;
      background: transparent;
    }}
    .formula-block {{
      margin: 18px 0 22px;
      padding: 18px 22px;
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #f8fafb;
      overflow-x: auto;
    }}
    .formula-line {{
      min-width: max-content;
      font-family: "Times New Roman", Georgia, serif;
      font-size: 22px;
      line-height: 1.8;
      white-space: nowrap;
    }}
    .formula-line.indent {{
      padding-left: 42px;
    }}
    .formula-line var {{
      font-style: italic;
    }}
    .formula-line sub {{
      font-size: 0.68em;
      vertical-align: -0.35em;
    }}
    .formula-line .op {{
      display: inline-block;
      padding: 0 0.16em;
    }}
    .formula-line .func {{
      font-style: normal;
      padding-right: 0.06em;
    }}
    .formula-line .text-term {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      font-size: 0.82em;
      font-style: normal;
    }}
    .formula-line .hat,
    .formula-line .overline {{
      text-decoration: overline;
      text-decoration-thickness: 1px;
    }}
    .table-scroll {{
      overflow-x: auto;
    }}
    .markdown-body table,
    .metadata-panel table {{
      width: 100%;
      border-collapse: collapse;
      margin: 18px 0;
      font-size: 13px;
    }}
    .markdown-body th,
    .markdown-body td,
    .metadata-panel th,
    .metadata-panel td {{
      border: 1px solid var(--line);
      padding: 7px 9px;
      vertical-align: top;
    }}
    .markdown-body th,
    .metadata-panel th {{
      background: var(--table-head);
      font-weight: 700;
      text-align: left;
    }}
    .anchor {{
      display: block;
      position: relative;
      top: -18px;
      visibility: hidden;
    }}
    .metadata-panel {{
      margin-top: 38px;
      padding-top: 20px;
      border-top: 1px solid var(--line);
    }}
    @media (max-width: 900px) {{
      .layout {{ display: block; }}
      aside {{
        position: static;
        height: auto;
        border-right: 0;
        border-bottom: 1px solid var(--line);
      }}
      main {{ padding: 24px 18px 60px; }}
    }}
    @media print {{
      aside {{ display: none; }}
      .layout {{ display: block; }}
      main {{ max-width: none; padding: 0; }}
    }}
  </style>
  <script>
    window.MathJax = {{
      tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']] }},
      svg: {{ fontCache: 'global' }}
    }};
  </script>
  <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js"></script>
</head>
<body>
  <div class="layout">
    <aside>
      <h1>Detailed Export Margins Notes</h1>
      <p>Long-form project notes and compact paper metadata. No full paper bodies embedded.</p>
      <nav>{nav_items}</nav>
    </aside>
    <main>
      <section class="intro">
        <h1>Detailed Export Margins Notes-First Guide</h1>
        <p>Project-first long notes for the 10-paper export margins literature set, with the compact guide preserved separately.</p>
        <div class="note">Source: <code>{html.escape(str(GUIDE_PATH.relative_to(ROOT)))}</code>; compact guide: <code>{html.escape(str(COMPACT_GUIDE_PATH.relative_to(ROOT)))}</code></div>
      </section>
      <section class="markdown-body">
        {guide_html}
      </section>
      {metadata_html}
    </main>
  </div>
</body>
</html>
"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(page, encoding="utf-8")
    return OUTPUT_FILE


def main() -> None:
    print(render())


if __name__ == "__main__":
    main()
