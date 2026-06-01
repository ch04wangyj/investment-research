"""Convert markdown research files to styled PDF using the Moutai template.

Usage:
    python scripts/md2pdf.py E:/StockResearch/600519_贵州茅台/reports/600519_investment_report_20260531.md
    python scripts/md2pdf.py E:/StockResearch/NVDA_AI_Sector/fundamentals/NVDA_AI_fundamentals_20260601.md

Pipeline:
    1. md2html.py (same CSS template as 贵州茅台)
    2. Edge headless print-to-pdf (Windows native, no GTK/cairo dependency)

Output: {input_stem}.pdf alongside the .md file (same directory)
"""
from __future__ import annotations

import subprocess
import shutil
import sys
import tempfile
import time
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────
EDGE_PATHS = [
    "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
    "C:/Program Files/Microsoft/Edge/Application/msedge.exe",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MD2HTML_SCRIPT = PROJECT_ROOT / "scripts" / "md2html.py"


def _find_edge() -> str:
    for p in EDGE_PATHS:
        if Path(p).exists():
            return p
    # fallback: try PATH
    for cmd in ("msedge", "chrome", "chromium"):
        try:
            result = subprocess.run(
                ["where", cmd], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                path = result.stdout.strip().split("\n")[0]
                if Path(path).exists():
                    return path
        except Exception:
            pass
    raise FileNotFoundError(
        "No browser found for PDF printing. Install Edge or Chrome."
    )


def md_to_html(md_path: Path) -> Path:
    """Step 1: Convert .md → .html using the Moutai CSS template."""
    html_path = md_path.with_suffix(".html")
    result = subprocess.run(
        [sys.executable, str(MD2HTML_SCRIPT), str(md_path), str(html_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"md2html failed: {result.stderr}")
    return html_path


def html_to_pdf(html_path: Path) -> Path:
    """Step 2: Convert .html → .pdf using Edge headless print."""
    edge = _find_edge()
    pdf_path = html_path.with_suffix(".pdf").resolve()
    if pdf_path.exists():
        pdf_path.unlink()
    abs_url = html_path.resolve().as_uri()  # file:///E:/StockResearch/...
    errors = []
    for attempt in range(2):
        profile_dir = tempfile.mkdtemp(prefix="investment-research-edge-")
        try:
            result = subprocess.run(
                [
                    edge,
                    "--headless",
                    "--disable-gpu",
                    "--no-first-run",
                    f"--user-data-dir={profile_dir}",
                    f"--print-to-pdf={pdf_path}",
                    "--no-pdf-header-footer",
                    abs_url,
                ],
                capture_output=True,
                timeout=90,
            )
            if result.returncode != 0:
                errors.append(f"attempt {attempt + 1}: browser exit code {result.returncode}")
            for _ in range(100):
                if pdf_path.exists() and pdf_path.stat().st_size > 0:
                    return pdf_path
                time.sleep(0.2)
            errors.append(f"attempt {attempt + 1}: browser returned without a PDF")
        except subprocess.TimeoutExpired:
            errors.append(f"attempt {attempt + 1}: browser print timed out")
        finally:
            # Edge Crashpad may briefly retain profile files after print completes.
            # Cleanup is best-effort; the PDF existence check remains authoritative.
            shutil.rmtree(profile_dir, ignore_errors=True)
        if pdf_path.exists():
            pdf_path.unlink()
    raise RuntimeError(
        f"Browser returned success but PDF was not created: {pdf_path}. "
        + "; ".join(errors)
    )


def md_to_pdf(md_path: str | Path) -> Path:
    """Full pipeline: .md → .html (Moutai template) → .pdf (Edge print)."""
    md_path = Path(md_path)
    if not md_path.exists():
        raise FileNotFoundError(f"Markdown file not found: {md_path}")
    html_path = md_to_html(md_path)
    pdf_path = html_to_pdf(html_path)
    return pdf_path


def batch_convert(base_dir: str | Path) -> list[Path]:
    """Convert all .md files under base_dir to .html + .pdf."""
    base = Path(base_dir)
    results = []
    failures = []
    md_files = [
        md_file
        for md_file in sorted(base.rglob("*.md"))
        if "kline" not in str(md_file) and "README" not in md_file.name
    ]
    if not md_files:
        raise RuntimeError(f"No publishable markdown files found under: {base}")
    for md_file in md_files:
        try:
            pdf = md_to_pdf(md_file)
            results.append(pdf)
            print(f"  [OK] {md_file.relative_to(base)} -> {pdf.name}")
        except Exception as e:
            print(f"  [FAIL] {md_file.relative_to(base)}: {e}")
            failures.append(f"{md_file.relative_to(base)}: {e}")
    if failures:
        raise RuntimeError("PDF conversion failed:\n" + "\n".join(failures))
    return results


# ── CLI ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/md2pdf.py <file.md | directory/>")
        print("  Single: python scripts/md2pdf.py report.md")
        print("  Batch:  python scripts/md2pdf.py E:/StockResearch/600519_贵州茅台/")
        sys.exit(1)

    target = Path(sys.argv[1])
    try:
        if target.is_dir():
            pdfs = batch_convert(target)
            print(f"\nDone: {len(pdfs)} PDFs generated")
        else:
            pdf = md_to_pdf(target)
            print(f"PDF generated: {pdf}")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
