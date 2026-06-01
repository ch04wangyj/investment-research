"""Convert markdown research files to styled HTML, then PDF-ready output."""
import sys
from pathlib import Path
import markdown

CSS = """
<style>
  @page { size: A4; margin: 2cm; }
  body {
    font-family: "Microsoft YaHei", "SimSun", sans-serif;
    font-size: 12pt; line-height: 1.8; color: #1a1a1a; max-width: 800px; margin: 0 auto;
  }

  /* ── Headings ── */
  h1 { font-size: 20pt; border-bottom: 3px solid #8B0000; padding-bottom: 8px; color: #8B0000; }
  h2 { font-size: 16pt; border-bottom: 1px solid #ccc; padding-bottom: 4px; color: #333; margin-top: 28px; }
  h3 { font-size: 13pt; color: #555; margin-top: 20px; }
  h4 { font-size: 11pt; color: #666; margin-top: 16px; }

  /* ── Tables ── */
  table { border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 10pt; word-break: normal; }
  th { background: #8B0000; color: white; padding: 6px 10px; text-align: center; vertical-align: middle; }
  td { border: 1px solid #ddd; padding: 5px 10px; vertical-align: top; overflow-wrap: anywhere; }
  table:has(th:nth-child(4)) td:nth-child(2),
  table:has(th:nth-child(4)) td:nth-child(3) { white-space: nowrap; }
  tr:nth-child(even) { background: #f9f9f9; }
  tr:nth-child(odd) { background: #fff; }
  thead th { position: sticky; top: 0; }

  /* ── Lists ── */
  ul, ol { padding-left: 2.5em; margin: 8px 0; }
  li { margin-bottom: 5px; }
  ul ul, ol ol, ul ol, ol ul { margin: 4px 0; }

  /* ── Inline elements ── */
  strong { color: #8B0000; }
  em { color: #555; }
  a { color: #8B0000; text-decoration: underline; }

  /* ── Inline code ── */
  code { font-family: "Consolas", "Courier New", monospace; background: #f0f0f0; padding: 1px 5px; border-radius: 3px; font-size: 10pt; }

  /* ── Code blocks + ASCII art (matrix, pipeline, value chain) ── */
  pre {
    font-family: "Consolas", "Courier New", "Microsoft YaHei", monospace;
    background: #f8f8f8;
    padding: 14px 18px;
    border-radius: 6px;
    border: 1px solid #e0e0e0;
    overflow-x: auto;
    font-size: 10pt;
    line-height: 1.35;
    white-space: pre;
    margin: 12px 0;
  }
  pre code { background: none; padding: 0; border-radius: 0; font-size: inherit; }

  /* ── Blockquotes ── */
  blockquote { border-left: 4px solid #8B0000; padding: 10px 18px; color: #555; background: #fafafa; margin: 14px 0; }
  blockquote p { margin: 4px 0; }

  /* ── Dividers ── */
  hr { border: none; border-top: 1px solid #ddd; margin: 24px 0; }

  /* ── Images ── */
  img { max-width: 100%; height: auto; border-radius: 4px; }

  /* ── Footer ── */
  .footer { text-align: center; color: #999; font-size: 9pt; margin-top: 40px; border-top: 1px solid #eee; padding-top: 12px; }

  /* ── Paragraphs ── */
  p { margin: 8px 0; text-align: justify; }
</style>
"""

def md_to_html(md_path: str, title: str) -> str:
    md_text = Path(md_path).read_text(encoding="utf-8")
    body = markdown.markdown(md_text, extensions=["tables", "fenced_code"])
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{title}</title>{CSS}</head>
<body>{body}<div class="footer">{title} | AI 多智能体研究系统 | {Path(md_path).stem}</div></body>
</html>"""

if __name__ == "__main__":
    md_path = sys.argv[1]
    out_path = sys.argv[2] if len(sys.argv) > 2 else md_path.replace(".md", ".html")
    title = Path(md_path).stem
    html = md_to_html(md_path, title)
    Path(out_path).write_text(html, encoding="utf-8")
    print(f"HTML written: {out_path}")
