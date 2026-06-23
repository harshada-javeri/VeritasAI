#!/usr/bin/env bash
# Capture a PNG per dashboard workspace locally.
#
# Requires a browser driver for headless capture (Playwright). If it is not
# installed, this script launches the server and prints manual-capture steps.
#
# Screenshots produced (one per workspace), written to ./screenshots/:
#   01-trust-center.png
#   02-cost-efficiency.png
#   03-data-quality-intelligence.png
#   04-human-review.png
#   05-platform-health.png
#   06-ai-judge-performance.png
#   07-event-detail.png
set -euo pipefail

OUT_DIR="${1:-screenshots}"
APP="src/veritas/dashboard/app.py"
PORT="${PORT:-8501}"
mkdir -p "$OUT_DIR"

echo "Starting Streamlit on :$PORT (point DATABASE_URL at a populated DB first)…"
uv run streamlit run "$APP" --server.headless true --server.port "$PORT" &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
sleep 5

if uv run python -c "import playwright" 2>/dev/null; then
  echo "Playwright found — capturing PNGs to $OUT_DIR/ …"
  uv run python - "$OUT_DIR" "$PORT" <<'PY'
import sys, time
from playwright.sync_api import sync_playwright

out, port = sys.argv[1], sys.argv[2]
views = [
    ("01-trust-center", "Trust Center"),
    ("02-cost-efficiency", "Cost & Efficiency"),
    ("03-data-quality-intelligence", "Data Quality Intelligence"),
    ("04-human-review", "Human Review"),
    ("05-platform-health", "Platform Health"),
    ("06-ai-judge-performance", "AI Judge Performance"),
    ("07-event-detail", "Event Detail"),
]
with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1600, "height": 1000})
    page.goto(f"http://localhost:{port}")
    page.wait_for_timeout(4000)
    for filename, label in views:
        page.get_by_text(label, exact=True).first.click()
        page.wait_for_timeout(2500)
        page.screenshot(path=f"{out}/{filename}.png", full_page=True)
        print(f"captured {filename}.png")
    browser.close()
PY
else
  echo "Playwright not installed. Open http://localhost:$PORT and capture each"
  echo "workspace from the left rail manually, or run: uv run playwright install chromium"
  echo "Press Ctrl-C when done."
  wait "$SERVER_PID"
fi
