"""Offline Chromium acceptance: python frontend/scripts/check-simulation-ui.py.
Requires the optional playwright package and its Chromium browser.
"""
import json
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


class StaticHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(StaticHandler, directory=str(ROOT)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = f'http://127.0.0.1:{server.server_port}'
    state = {'status': 'running', 'phase': 'branch_sim', 'can_pause': True, 'progress_pct': 30,
             'simulation_id': 'run1', 'current_event_index': 1, 'total_events': 4,
             'total_agents': 2, 'alive_agents': 2, 'model_info': {'model_id': 'b', 'model': 'beta'}}
    queued, captured, errors = [], [], []
    offline = False
    held_models = []
    hold_models = False

    def api(route):
        request = route.request
        path = urlparse(request.url).path
        method = request.method
        body, status = {}, 200
        if path == '/api/health': body = {'status': 'ok', 'llm_configured': True}
        elif path == '/api/kb/status': body = {'lightrag_ok': True}
        elif path == '/api/config': body = {'llm_configured': True, 'max_steps': 200}
        elif path == '/api/kb/categories': body = []
        elif path == '/api/llm-models':
            if hold_models:
                held_models.append(route)
                return
            body = {'default_model_id': 'a', 'models': [
                {'id': 'a', 'name': 'Model A', 'model': 'alpha', 'provider': 'openai'},
                {'id': 'b', 'name': 'Model B', 'model': 'beta', 'provider': 'openai'}]}
        elif path == '/api/simulations' and method == 'POST':
            captured.append(('create', request.post_data_json))
            body = {'simulation_id': 'run1', 'status': 'pending'}
        elif method == 'DELETE' and path.startswith('/api/simulations/'):
            captured.append(('delete-simulation', path))
        elif method == 'DELETE' and path.startswith('/api/chat/sessions/'):
            captured.append(('delete-chat', path))
        elif path == '/api/simulations': body = {'simulations': [
            {'id': 'saved-run', 'simulation_id': 'saved-run', 'goal': 'Saved run',
             'target_goal': {'description': 'Saved run'}, 'status': 'completed'}]}
        elif path == '/api/chat/sessions': body = {'sessions': [
            {'id': 'saved-chat', 'title': 'Saved chat'}]}
        elif path.endswith('/pause'):
            state.update(status='paused', can_pause=False)
        elif path.endswith('/resume'):
            state.update(status='running', can_pause=True)
        elif path.endswith('/cancel'):
            state.update(status='cancelled', can_pause=False)
            body = {'simulation_id': 'run1', 'status': 'cancelled'}
        elif path.endswith('/events'):
            if method == 'POST': queued.append(request.post_data_json)
            elif method == 'DELETE': queued.clear()
            body = {'events': queued}
        elif path.endswith('/retry'):
            captured.append(('retry', request.post_data_json))
            state.update(status='running', can_pause=True)
            body = {'simulation_id': 'rerun2', 'status': 'pending'}
        elif path.endswith('/result'):
            body = {'simulation_id': 'run1', 'model_info': {'model': 'beta'}, 'agent_count': 2,
                    'events_simulated': 4, 'branches': [], 'agent_paths': [], 'event_comparisons': [{
                        'event_index': 1, 'events': ['exam_change'],
                        'event_summaries': [{'event_type': 'exam_change', 'description': '考试题型发生变化'}],
                        'agents': [{'agent_id': 'a1', 'rank': 1, 'decision': '调整复习计划',
                                    'outcome': '复习覆盖范围扩大', 'goal_status': {
                                        'progress': 0.75, 'distance': 0.25, 'metric_gaps': {'数学成绩': 8}},
                                    'metrics': [{'name': '数学成绩', 'previous': 62, 'value': 70}]}]}],
                    'warnings': [{'code': 'synthesis_failed', 'stage': 'synthesis'}]}
        elif path.endswith('/decisions'): body = {'paths': [], 'event_comparisons': []}
        elif path.startswith('/api/simulations/'):
            if path.endswith('/missing'):
                status, body = 404, {'detail': 'not found'}
            elif offline:
                status, body = 503, {'detail': 'offline'}
            else:
                body = state.copy()
                if path.endswith('/interrupted'):
                    body.update(status='interrupted', can_pause=False,
                                model_info={'model_id': 'deleted', 'model': 'removed-model'})
        route.fulfill(status=status, json=body)

    try:
        expect.set_options(timeout=15000)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width': 1366, 'height': 900})
            page.on('pageerror', lambda exc: errors.append(str(exc)))
            page.route('**/api/**', api)
            page.add_init_script("window.PRDS_API_BASE = location.origin + '/api';")
            page.goto(origin + '/#simulate')
            expect(page.locator('#sim-model-label')).to_have_text('Model A')
            # Keep sidebar, history rows and their scroll while switching entry pages.
            page.evaluate("""() => {
                window.originalSidebar = document.querySelector('.app-sidebar');
                window.originalHistory = document.querySelector('#sb-history-list');
                window.sidebarMutations = [];
                new MutationObserver(records => {
                    window.sidebarMutations.push(...records.map(r => r.type));
                }).observe(window.originalHistory, {childList: true, subtree: true});
            }""")
            hold_models = True
            for _ in range(3):
                page.locator('.sb-new-run[href="#chat"]').click()
                expect(page.locator('#chat-form.is-empty')).to_be_visible()
                expect(page.locator('#sim-model-label')).to_have_text('Model A')
                page.locator('.sb-new-run[href="#simulate"]').click()
                expect(page.locator('#sim-form')).to_be_visible()
                expect(page.locator('.simulate-hero')).to_have_css('opacity', '1')
                expect(page.locator('#sim-model-label')).to_have_text('Model A')
                assert page.evaluate("originalSidebar === document.querySelector('.app-sidebar')")
                assert page.evaluate("originalHistory === document.querySelector('#sb-history-list')")
            hold_models = False
            for held in held_models:
                held.fulfill(json={'default_model_id': 'a', 'models': [
                    {'id': 'a', 'name': 'Model A', 'model': 'alpha', 'provider': 'openai'},
                    {'id': 'b', 'name': 'Model B', 'model': 'beta', 'provider': 'openai'}]})
            expect(page.locator('#sim-model-menu [data-model-id="b"]')).to_have_count(1)
            assert page.evaluate('sidebarMutations.length') == 0
            # A stale chat mount must not register listeners on the new page.
            page.locator('#goal').fill('切换测试')
            expect(page.locator('#start-btn')).to_be_enabled()
            page.locator('#sim-model-btn').click()
            page.locator('[data-model-id="b"]').click()
            page.locator('#goal').fill('一年内提高数学成绩')
            page.locator('#start-btn').click()
            expect(page.locator('#run-model')).to_contain_text('beta')
            assert captured[0][1]['config']['model_id'] == 'b'
            expect(page.locator('#run-pause')).to_be_visible()
            page.locator('#run-pause').click()
            expect(page.locator('#run-injection')).to_be_visible()
            page.locator('#run-event-description').fill('新增每周辅导时间')
            # Keep draft and focus across polling refreshes.
            page.wait_for_timeout(1700)
            expect(page.locator('#run-event-description')).to_have_value('新增每周辅导时间')
            page.locator('#run-add-event').click()
            expect(page.locator('#run-event-list')).to_contain_text('新增每周辅导时间')
            assert queued[0]['description'] == '新增每周辅导时间'
            output = ROOT.parent / 'backend/data/reports'
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output / 'simulation-paused.png'), full_page=True)
            page.locator('#run-resume').click()
            expect(page.locator('#run-pause')).to_be_visible()
            page.locator('#run-cancel').click()
            expect(page.locator('#run-retry')).to_be_visible()
            page.locator('#run-retry').click()
            page.wait_for_url('**/#simulate/rerun2')
            expect(page.locator('#run-model')).to_contain_text('beta')
            page.goto(origin + '/#simulate/interrupted')
            expect(page.locator('#run-description')).to_contain_text('服务中断')
            page.locator('#run-retry-model').select_option('b')
            page.locator('#run-retry').click()
            page.wait_for_url('**/#simulate/rerun2')
            assert captured[-1] == ('retry', {'model_id': 'b'})
            # Only the current route can update the page.
            page.goto(origin + '/#simulate/missing')
            expect(page.locator('#run-title')).to_have_text('记录不存在')
            expect(page.locator('#run-cancel')).to_be_hidden()
            offline = True
            page.goto(origin + '/#simulate/offline')
            expect(page.locator('#run-connection')).to_contain_text('连接异常')
            offline = False
            page.locator('#run-reconnect').click()
            expect(page.locator('#run-connection')).to_contain_text('最后更新')
            # The running page transitions to results without leaving a composer behind.
            state.update(status='completed')
            expect(page.locator('#results-root')).to_contain_text('结果已生成，总结生成失败')
            expect(page.locator('#results-root')).to_contain_text('beta')
            expect(page.locator('.sim-composer')).to_have_count(0)
            expect(page.locator('#goal')).to_have_count(0)
            expect(page.locator('#event-list')).to_contain_text('考试题型发生变化')
            expect(page.locator('#event-detail')).to_contain_text('调整复习计划')
            expect(page.locator('#event-detail')).to_contain_text('75%')
            expect(page.locator('#results-root')).not_to_contain_text('距目标')
            expect(page.locator('#results-root')).not_to_contain_text('指标缺口')
            # A direct visit to a completed run has the same behavior.
            page.goto(origin + '/#simulate/completed')
            expect(page.locator('#results-root')).to_contain_text('75%')
            expect(page.locator('.sim-composer')).to_have_count(0)
            page.screenshot(path=str(output / 'simulation-result-warning.png'), full_page=True)
            # Inspect the same controls in English as well (portable without CJK fonts).
            page.evaluate("localStorage.setItem('prds_prefs', JSON.stringify({locale:'en'}))")
            state.update(status='paused', can_pause=False)
            page.goto(origin + '/#simulate/run1')
            expect(page.locator('#run-injection')).to_be_visible()
            expect(page.locator('#run-injection')).to_contain_text('Inject an event')
            page.screenshot(path=str(output / 'simulation-paused.png'), full_page=True)
            state.update(status='completed')
            page.goto(origin + '/#simulate/completed')
            expect(page.locator('#results-root')).to_contain_text('Results generated; summary generation failed.')
            page.screenshot(path=str(output / 'simulation-result-warning.png'), full_page=True)
            # Record close buttons use the app dialog, never window.confirm.
            page.add_init_script("window.confirm = () => { throw new Error('Unexpected browser confirmation'); };")
            page.evaluate("() => { window.confirm = () => { throw new Error('Unexpected browser confirmation'); }; }")
            dialog = page.locator('dialog.confirm-dialog')
            delete_run = page.locator('.sb-hist-delete[data-sim-id="saved-run"]')
            delete_run.click()
            expect(dialog).to_be_visible()
            expect(dialog.locator('[value="cancel"]')).to_be_focused()
            page.keyboard.press('Tab')
            expect(dialog.locator('[value="confirm"]')).to_be_focused()
            page.keyboard.press('Tab')
            expect(dialog.locator('[value="cancel"]')).to_be_focused()
            dialog.locator('[value="cancel"]').click()
            expect(dialog).to_have_count(0)
            expect(delete_run).to_be_focused()
            assert not any(item[0] == 'delete-simulation' for item in captured)
            delete_run.click()
            page.keyboard.press('Escape')
            expect(dialog).to_have_count(0)
            delete_run.click()
            page.mouse.click(5, 5)
            expect(dialog).to_have_count(0)
            delete_run.click()
            dialog.locator('[value="confirm"]').click()
            expect(dialog).to_have_count(0)
            page.wait_for_timeout(200)
            assert ('delete-simulation', '/api/simulations/saved-run') in captured
            page.locator('.sb-chat-delete[data-chat-id="saved-chat"]').click()
            expect(dialog).to_contain_text('Delete chat')
            dialog.locator('[value="confirm"]').click()
            page.wait_for_timeout(200)
            assert ('delete-chat', '/api/chat/sessions/saved-chat') in captured
            state.update(status='cancelled')
            page.goto(origin + '/#simulate/run1')
            page.locator('#run-delete').click()
            expect(dialog).to_be_visible()
            dialog.locator('[value="cancel"]').click()
            page.locator('#run-delete').click()
            dialog.locator('[value="confirm"]').click()
            page.wait_for_url('**/#simulate')
            assert ('delete-simulation', '/api/simulations/run1') in captured
            assert not errors, errors
            browser.close()
            print('Browser acceptance passed: model selection, pause, injection, resume, cancel, retry, interruption, missing record, reconnection, result warnings; no page errors.')
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
