"""Compile paper/bonemap_preprint.html to paper/bonemap_preprint.pdf via headless Chrome."""

from pathlib import Path
from playwright.sync_api import sync_playwright

PAPER_DIR = Path(__file__).resolve().parent
HTML_PATH = PAPER_DIR / "bonemap_preprint.html"
PDF_PATH = PAPER_DIR / "bonemap_preprint.pdf"
CHROME_PATH = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def main() -> None:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME_PATH, headless=True)
        page = browser.new_page()
        page.goto(HTML_PATH.as_uri(), wait_until="networkidle")
        page.pdf(
            path=str(PDF_PATH),
            format="Letter",
            print_background=True,
            display_header_footer=False,
            prefer_css_page_size=True,
        )
        browser.close()
    print(f"Wrote {PDF_PATH} ({PDF_PATH.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
