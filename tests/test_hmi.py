"""Real browser acceptance test; owns and closes its server, pages and browser."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def owned_processes(owner):
    """Record only this test's descendants, without command arguments or profiles."""
    rows = []
    output = subprocess.check_output(["ps", "-eo", "pid,ppid,lstart,comm"], text=True)
    for line in output.splitlines()[1:]:
        fields = line.split(None, 7)
        if len(fields) == 8:
            rows.append({"pid": int(fields[0]), "ppid": int(fields[1]),
                         "start": " ".join(fields[2:7]), "executable": fields[7]})
    parents = {owner}
    result = []
    while True:
        children = [r for r in rows if r["ppid"] in parents and r["pid"] not in parents
                    and Path(r["executable"]).name != "ps"]
        if not children:
            return result
        result.extend(children)
        parents.update(r["pid"] for r in children)


class HMITests(unittest.TestCase):
    def test_operator_fault_recovery_batch_and_maintenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            url = f"http://127.0.0.1:{port}"
            proc = subprocess.Popen([sys.executable, "-m", "fillingline.server", "--port", str(port),
                                     "--db", str(Path(tmp) / "maintenance.sqlite3")], cwd=ROOT,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            artifacts = ROOT / "artifacts"
            artifacts.mkdir(exist_ok=True)
            (artifacts / "resources.json").write_text(json.dumps({"owner": "tests/test_hmi.py", "pid": proc.pid,
                "started_at": time.time(), "port": port, "cleanup": f"SIGTERM owned PID {proc.pid}; wait; verify port closed"}, indent=2))
            try:
                for _ in range(100):
                    if proc.poll() is not None:
                        self.fail(proc.communicate()[0][-2000:])
                    try:
                        with urlopen(url + "/api/state", timeout=.2) as response:
                            if response.status == 200:
                                break
                    except OSError:
                        time.sleep(.05)
                else:
                    self.fail("Owned HMI server did not become ready")
                for path, headers, payload, status in [
                    ("/api/command", {"Origin": "https://example.com"}, {"action": "start"}, 403),
                    ("/api/command", {}, {"action": "fault", "name": "TankOK", "value": "false"}, 400),
                    ("/../../LICENSE", {}, None, 404),
                ]:
                    request = Request(url + path, data=json.dumps(payload).encode() if payload else None,
                                      headers={"Content-Type": "application/json", **headers})
                    with self.assertRaises(HTTPError) as raised:
                        urlopen(request, timeout=2)
                    self.assertEqual(raised.exception.code, status)
                    raised.exception.close()
                with sync_playwright() as p:
                    browser = context = page = None
                    try:
                        browser = p.chromium.launch(channel=os.environ.get("PLC_BROWSER_CHANNEL"))
                        context = browser.new_context(viewport={"width": 1440, "height": 1100})
                        page = context.new_page()
                        (artifacts / "browser-processes.json").write_text(json.dumps({
                            "owner": "tests/test_hmi.py", "cleanup": "page.close; context.close; browser.close; sync_playwright exit",
                            "processes": owned_processes(os.getpid())}, indent=2))
                        errors = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.goto(url)
                        expect(page.locator("#connection")).to_have_text("Controller connected")
                        page.get_by_role("button", name="Start line", exact=True).click()
                        expect(page.locator("#status")).to_have_text("Running")
                        page.get_by_label("Emergency stop pressed").check()
                        expect(page.locator("#status")).to_have_text("Tripped — reset required")
                        expect(page.locator("#orders")).to_contain_text("EStopOK")
                        page.get_by_label("Emergency stop pressed").uncheck()
                        page.get_by_role("button", name="Reset batch / discard bottle").click()
                        expect(page.locator("#status")).to_have_text("Stopped")
                        order = page.locator("#orders tr").first
                        order.get_by_role("textbox").fill("Released simulated stop; verified reset and restart")
                        order.get_by_role("button", name="Close order").click()
                        expect(order).to_contain_text("Closed")
                        page.reload()
                        expect(page.locator("#orders")).to_contain_text("Released simulated stop")
                        page.get_by_role("button", name="Start line", exact=True).click()
                        expect(page.locator("#status")).to_have_text("Batch complete", timeout=22000)
                        expect(page.locator("#count")).to_have_text("5 / 5")
                        page.screenshot(path=str(artifacts / "hmi-desktop.png"), full_page=True)
                        # A public screenshot contains only these fictional test records.
                        if os.environ.get("UPDATE_SCREENSHOTS") == "1":
                            page.screenshot(path=str(ROOT / "docs/hmi.png"), full_page=True)
                        page.locator('[name="issue"]').fill("<img src=x onerror=alert(1)> inspect alignment")
                        page.get_by_role("button", name="Add work order").click()
                        expect(page.locator("#orders")).to_contain_text("<img src=x onerror=alert(1)>")
                        self.assertEqual(page.locator("#orders img").count(), 0)
                        for width in (1440, 390):
                            page.set_viewport_size({"width": width, "height": 900})
                            page.screenshot(path=str(artifacts / f"hmi-{width}.png"), full_page=True)
                            self.assertTrue(page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Overflow at {width}px")
                            self.assertTrue(page.get_by_role("button", name="Start line", exact=True).is_visible())
                        page.screenshot(path=str(artifacts / "hmi-mobile.png"), full_page=True)
                        self.assertEqual(errors, [])
                    finally:
                        if page:
                            page.close()
                        if context:
                            context.close()
                        if browser:
                            browser.close()
            finally:
                proc.terminate()
                try:
                    output, _ = proc.communicate(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()  # This exact process is owned by this test.
                    output, _ = proc.communicate(timeout=5)
                if proc.returncode != 0:
                    print("HMI server output:", output[-2000:])
                with socket.socket() as check:
                    self.assertNotEqual(check.connect_ex(("127.0.0.1", port)), 0, "Owned server port still open")
                self.assertIsNotNone(proc.poll())
                self.assertEqual(owned_processes(os.getpid()), [], "Owned child process remains after cleanup")
                (artifacts / "cleanup.json").write_text(json.dumps({"server_pid": proc.pid, "port": port,
                    "server_exited": True, "port_closed": True, "owned_descendants_remaining": []}, indent=2))
                print(f"Cleaned owned HMI PID {proc.pid}; port {port} closed; browser and page closed")
