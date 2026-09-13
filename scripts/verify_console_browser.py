"""Drive the evidence console in a real browser (Edge/Chrome). HTTP GET is not enough."""

from __future__ import annotations

import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from invariant.hashing import ROOT

CONSOLE = ROOT / "console"
OUT = ROOT / "results" / "demo"


class _QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def _serve() -> ThreadingHTTPServer:
    handler = partial(_QuietHandler, directory=str(CONSOLE))
    server = ThreadingHTTPServer(("127.0.0.1", 8766), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main() -> int:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    server = _serve()
    actions: list[str] = []
    bugs: list[str] = []
    evidence: dict[str, object] = {}
    try:
        with sync_playwright() as p:
            browser = None
            launched = None
            for channel in ("msedge", "chrome", None):
                try:
                    if channel:
                        browser = p.chromium.launch(channel=channel, headless=True)
                    else:
                        browser = p.chromium.launch(headless=True)
                    launched = channel or "bundled"
                    actions.append(f"launched chromium channel={launched}")
                    break
                except Exception as exc:
                    actions.append(f"channel {channel} failed: {type(exc).__name__}: {exc}")
            if browser is None:
                raise RuntimeError("no browser available")
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto("http://127.0.0.1:8766/index.html", wait_until="domcontentloaded")
            page.wait_for_selector("#runs-body tr")
            actions.append("list: loaded run row")
            page.screenshot(path=str(OUT / "01-runs-desktop.png"), full_page=True)

            page.locator("#runs-body tr").first.click()
            page.wait_for_url("**/run.html*")
            actions.append("clicked run row -> detail")
            page.screenshot(path=str(OUT / "02-detail.png"), full_page=True)

            for stage in ("intake", "contract", "generate", "verify", "publish"):
                page.locator(f'.stage[data-stage="{stage}"]').click()
                page.wait_for_timeout(150)
                actions.append(f"selected stage {stage}")
            page.screenshot(path=str(OUT / "03-publish.png"), full_page=True)
            github_hrefs = page.locator("a[href*='github.com']").evaluate_all(
                "els => els.map(e => e.href)"
            )
            evidence["github_hrefs"] = github_hrefs
            actions.append(f"github_links={len(github_hrefs)}")
            if not github_hrefs:
                bugs.append("publish stage missing GitHub evidence links")

            page.locator('.stage[data-stage="verify"]').click()
            page.wait_for_timeout(150)
            chips = page.locator(".strip .chip")
            evidence["status_chips"] = chips.count()
            actions.append(f"status chips={chips.count()}")
            if chips.count() != 4:
                bugs.append(f"expected 4 status chips, got {chips.count()}")
            unknown_as_pass = page.locator(".pip.pass", has_text="!").count()
            unknown_check = page.locator(".chip.ok", has_text="unknown").count()
            evidence["unknown_as_pass_pip"] = unknown_as_pass
            evidence["unknown_outcome_painted_ok"] = unknown_check
            actions.append(f"unknown_as_pass_pip={unknown_as_pass}")
            actions.append(f"unknown_outcome_painted_ok={unknown_check}")
            if unknown_as_pass:
                bugs.append("unknown status pip painted as pass/green")
            if unknown_check:
                bugs.append("unknown application outcome painted as ok/green")

            details = page.locator("details.finding")
            if details.count():
                details.first.locator("summary").click()
                actions.append("expanded first finding")
            else:
                bugs.append("no findings to expand")
            page.screenshot(path=str(OUT / "04-verify.png"), full_page=True)

            page.locator("#refresh").click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_selector("#pipeline .stage")
            actions.append("clicked refresh; stages still present")

            page.set_viewport_size({"width": 900, "height": 800})
            page.goto("http://127.0.0.1:8766/index.html", wait_until="domcontentloaded")
            page.wait_for_timeout(200)
            mode = page.locator(".table-scroll").get_attribute("data-mode")
            evidence["viewport_900_mode"] = mode
            actions.append(f"viewport 900 table mode={mode}")
            if mode != "pane":
                bugs.append(f"900px expected table mode pane, got {mode}")
            page.screenshot(path=str(OUT / "05-narrow-900.png"), full_page=True)

            page.set_viewport_size({"width": 390, "height": 800})
            page.goto("http://127.0.0.1:8766/index.html", wait_until="domcontentloaded")
            page.wait_for_timeout(200)
            cards = page.locator("#run-cards article")
            evidence["viewport_390_cards"] = cards.count()
            actions.append(f"viewport 390 cards={cards.count()}")
            if cards.count() < 1:
                bugs.append("390px expected stacked cards")
            page.screenshot(path=str(OUT / "06-mobile-390.png"), full_page=True)
            if cards.count():
                cards.first.click()
                page.wait_for_url("**/run.html*")
                actions.append("mobile card -> detail")
                stages_vertical = page.evaluate(
                    "() => getComputedStyle(document.querySelector('.pipeline')).flexDirection"
                )
                evidence["mobile_pipeline_flex"] = stages_vertical
                actions.append(f"mobile pipeline flex-direction={stages_vertical}")
                if stages_vertical != "column":
                    bugs.append(f"390px stages expected column, got {stages_vertical}")
                page.screenshot(path=str(OUT / "07-mobile-detail.png"), full_page=True)
            browser.close()
    finally:
        server.shutdown()
    record = {
        "ok": not bugs,
        "actions": actions,
        "bugs": bugs,
        "evidence": evidence,
    }
    (OUT / "browser-log.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record, indent=2))
    return 0 if not bugs else 1


if __name__ == "__main__":
    raise SystemExit(main())
