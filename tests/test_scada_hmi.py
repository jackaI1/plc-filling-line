"""Real FUXA, real Modbus TCP and compiled ladder through an operator browser."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.request import urlopen

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def owned_descendants(owner):
    rows = []
    output = subprocess.check_output(['ps', '-eo', 'pid,ppid,lstart,comm'], text=True)
    for line in output.splitlines()[1:]:
        fields = line.split(None, 7)
        if len(fields) == 8:
            rows.append({'pid': int(fields[0]), 'ppid': int(fields[1]),
                         'start': ' '.join(fields[2:7]), 'executable': fields[7]})
    parents = {owner}
    result = []
    while True:
        children = [row for row in rows if row['ppid'] in parents and row['pid'] not in parents
                    and Path(row['executable']).name != 'ps']
        if not children:
            return result
        result.extend(children)
        parents.update(row['pid'] for row in children)


class ScadaHMITests(unittest.TestCase):
    def test_fuxa_tags_alarm_ack_recovery_animation_and_trend(self):
        modbus, web = free_port(), free_port()
        with tempfile.TemporaryDirectory() as tmp:
            processes = []
            browser_processes = []
            evidence = ROOT / 'artifacts'
            evidence.mkdir(exist_ok=True)
            with open(Path(tmp) / 'runtime.log', 'w+') as log:
                try:
                    for command, env, port in [
                        ([sys.executable, '-m', 'fillingline.modbus', '--port', str(modbus)], os.environ.copy(), modbus),
                        (['node', 'scada/launch.cjs'], {**os.environ, 'FUXA_PORT': str(web), 'MODBUS_PORT': str(modbus), 'FUXA_WORK': tmp}, web),
                    ]:
                        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=log)
                        processes.append((process, port))
                    (evidence / 'scada-resources.json').write_text(json.dumps({
                        'owner':'tests/test_scada_hmi.py', 'cleanup':'SIGINT; wait; assert ports closed',
                        'processes':[{'pid':p.pid,'port':port,'start':subprocess.check_output(['ps','-p',str(p.pid),'-o','lstart='],text=True).strip()} for p,port in processes]
                    }, indent=2))
                    url = f'http://127.0.0.1:{web}'
                    for _ in range(200):
                        if any(p.poll() is not None for p,_ in processes):
                            log.seek(0); self.fail(log.read()[-3500:])
                        try:
                            with urlopen(url + '/api/project', timeout=.2) as response:
                                if 'line' in json.load(response).get('devices', {}):
                                    break
                        except (OSError, ValueError):
                            pass
                        time.sleep(.1)
                    else:
                        log.seek(0); self.fail(log.read()[-3500:])
                    with sync_playwright() as playwright:
                        browser = playwright.chromium.launch(channel=os.environ.get('PLC_BROWSER_CHANNEL'))
                        try:
                            browser_processes = [row for row in owned_descendants(os.getpid()) if row['pid'] not in {p.pid for p,_ in processes}]
                            (evidence / 'scada-browser-processes.json').write_text(json.dumps({'owner':'tests/test_scada_hmi.py','cleanup':'page.close; browser.close; sync_playwright exit','processes':browser_processes},indent=2))
                            # CI's POSIX locale is not a BCP 47 browser language tag.
                            page = browser.new_page(viewport={'width':1280,'height':1024}, locale='en-US')
                            try:
                                errors = []
                                page.on('pageerror', lambda error: errors.append(str(error)))
                                page.goto(url + '/resources/operator/index.html')
                                expect(page.locator('#connection')).to_have_text('Controller connected', timeout=15000)
                                initial_bottle = page.locator('#bottle').get_attribute('transform')
                                page.get_by_label('Hold fill sensor on').check()
                                page.get_by_role('button',name='Start line',exact=True).click()
                                expect(page.locator('#valve-state')).to_have_text('Open', timeout=7000)
                                expect(page.locator('#motor-state')).to_have_text('Running')
                                expect(page.locator('#motor')).to_have_class('running')
                                expect(page.locator('#bottle')).not_to_have_attribute('transform',initial_bottle)
                                expect(page.locator('#alarm')).to_contain_text('Fill position did not clear', timeout=12000)
                                expect(page.locator('#alarm')).to_have_attribute('data-state','unacknowledged')
                                expect(page.locator('#motor-state')).to_have_text('Stopped')
                                page.get_by_role('button',name='Acknowledge alarm').click()
                                expect(page.locator('#alarm')).to_have_attribute('data-state','acknowledged')
                                with urlopen(url + '/api/alarms',timeout=2) as response:
                                    native_alarms = json.load(response)
                                self.assertTrue(native_alarms[0]['acktime'])
                                self.assertEqual(page.locator('#tag-FillBlocked').text_content(), '1')
                                page.get_by_role('button',name='Reset batch').click()
                                page.wait_for_timeout(300)
                                self.assertEqual(page.locator('#tag-FillBlocked').text_content(), '1')
                                page.get_by_label('Hold fill sensor on').uncheck()
                                page.get_by_role('button',name='Reset batch').click()
                                expect(page.locator('#tag-FillBlocked')).to_have_text('0')
                                expect(page.locator('#motor-state')).to_have_text('Stopped')
                                page.get_by_role('button',name='Start line',exact=True).click()
                                expect(page.locator('#count')).to_have_text('5',timeout=25000)
                                expect(page.locator('#trend')).to_have_attribute('data-last-count','5')
                                self.assertGreater(len(page.locator('#trend-line').get_attribute('points').split()), 5)
                                page.screenshot(path=str(evidence / 'scada.png'),full_page=True)
                                page.goto(url + '/home/Line%20overview')
                                expect(page.locator('iframe')).to_be_visible(timeout=10000)
                                expect(page.frame_locator('iframe').locator('#connection')).to_have_text('Controller connected',timeout=10000)
                                page.goto(url + '/resources/operator/index.html')
                                expect(page.locator('#connection')).to_have_text('Controller connected')
                                page.set_viewport_size({'width':390,'height':844})
                                self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
                                self.assertEqual(errors, [])
                                processes[0][0].send_signal(signal.SIGINT)
                                processes[0][0].wait(timeout=5)
                                expect(page.locator('#connection')).to_have_text('Controller disconnected',timeout=7000)
                                expect(page.locator('#motor-state')).to_have_text('Unknown')
                                expect(page.get_by_role('button',name='Start line',exact=True)).to_be_disabled()
                            finally:
                                page.close()
                        finally:
                            browser.close()
                finally:
                    for process,_ in reversed(processes):
                        if process.poll() is None:
                            process.send_signal(signal.SIGINT)
                            try:
                                process.wait(timeout=8)
                            except subprocess.TimeoutExpired:
                                process.terminate(); process.wait(timeout=5)
                    for process,port in processes:
                        self.assertIsNotNone(process.poll())
                        with socket.socket() as probe:
                            self.assertNotEqual(probe.connect_ex(('127.0.0.1',port)),0, f'owned port {port} remains open')
                    remaining = {row['pid']:row['start'] for row in owned_descendants(os.getpid())}
                    for row in browser_processes:
                        self.assertNotEqual(remaining.get(row['pid']),row['start'],f'owned browser process {row["pid"]} remains')
