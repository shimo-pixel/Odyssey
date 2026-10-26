"""Regression tests for selected models, factual events, and owned task lifetimes."""
import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from prds.api.routes import simulations as routes
from prds.config import Settings
from prds.kb.client import LightRAGClient
from prds.kbsim.orchestrator import KbSimOrchestrator
from prds.models.domain import (
    CurrentState, SimulationConfig, SimulationInput, SimulationStatus, TargetGoal, UserEventInput,
)
from prds.simulation.control import get_control
from prds.simulation.errors import SimulationFailure
from prds.simulation.tasks import SimulationTaskManager, gather_owned, get_tasks
from prds.storage.repository import SimulationRepository
from tests.conftest import _payload_of, llm_reply_for
from tests.kbsim_fakes import FakeLightRAG, mock_transport_client


def simulation(**config):
    return SimulationInput(current_state=CurrentState(background="数学 62 分"),
        goal=TargetGoal(description="提高数学成绩"),
        config=SimulationConfig(agent_count=2, max_events=2, **config))


class ScriptedLLM:
    def __init__(self, settings=None, fail=None):
        self.settings = settings or Settings(openai_api_key="test")
        self.analysis_model = self.settings.prds_llm_model_analysis
        self.calls = []
        self.fail = fail

    async def structured_complete(self, system, user, model_class, model=None):
        self.calls.append((model_class.__name__, _payload_of(user), model))
        if model_class.__name__ == self.fail:
            raise RuntimeError("SECRET_KEY provider response must not reach users")
        data = json.loads(llm_reply_for(system, user))
        if model_class.__name__ == 'StatePrediction' and any(
            e['description'] == 'INJECT_LOSS' for e in _payload_of(user).get('events', [])
        ):
            for reading in data['metrics']:
                reading['value'] -= 20
        return model_class.model_validate(data)


@pytest.fixture
async def api(tmp_path, monkeypatch):
    settings = Settings(openai_api_key="legacy", prds_database_url=f"sqlite+aiosqlite:///{tmp_path / 'runs.db'}",
                        prds_logs_dir=str(tmp_path / 'logs'))
    repo = SimulationRepository(settings)
    await repo.init_db()
    monkeypatch.setattr(routes, '_repo', repo)
    monkeypatch.setattr(routes, 'get_settings', lambda: settings)
    monkeypatch.setattr(routes, 'LLMClient', ScriptedLLM)
    created = []
    kb = FakeLightRAG()
    def orchestrator(llm, snapshot):
        orch = KbSimOrchestrator(llm, snapshot)
        orch.kb = kb
        created.append(orch)
        return orch
    monkeypatch.setattr(routes, 'KbSimOrchestrator', orchestrator)
    monkeypatch.setattr(routes, 'LightRAGClient', lambda *a: kb)
    from prds.main import app
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        yield client, repo, settings, created, kb
    await get_tasks().shutdown()
    get_tasks().shutting_down = False
    await repo.engine.dispose()


async def wait_finished(run_id):
    task = get_tasks().tasks.get(run_id)
    if task:
        await asyncio.wait_for(asyncio.shield(task), timeout=3)


async def test_selected_model_is_fixed_for_all_stages_and_parallel_runs(api, monkeypatch):
    client, repo, settings, created, _ = api
    entries = {
        'a': dict(id='a', name='Model A', model='alpha', api_key='key-a', api_base='https://a.example/v1', provider='openai'),
        'b': dict(id='b', name='Model B', model='beta', api_key='key-b', api_base='https://b.example/v1', provider='openai'),
    }
    monkeypatch.setattr(routes, 'get_model_entry', AsyncMock(side_effect=lambda mid, **kw: entries.get(mid)))
    responses = await asyncio.gather(*(client.post('/api/simulations', json=simulation(model_id=mid).model_dump()) for mid in entries))
    ids = [r.json()['simulation_id'] for r in responses]
    settings.prds_llm_model = 'changed-default'
    await asyncio.gather(*(wait_finished(rid) for rid in ids))
    by_model = {orch.llm.settings.prds_llm_model: orch for orch in created}
    for mid, entry in entries.items():
        orch = by_model[entry['model']]
        assert orch.llm.settings.openai_api_key == entry['api_key']
        assert orch.llm.settings.prds_llm_api_base == entry['api_base']
        assert all(model in (None, entry['model']) for _, _, model in orch.llm.calls)
        assert orch.llm.analysis_model == entry['model']
    for rid in ids:
        result = (await client.get(f'/api/simulations/{rid}/result')).json()
        assert result['model_info']['model'] in ('alpha', 'beta')
        assert 'key-a' not in json.dumps(result) and 'key-b' not in json.dumps(result)


async def test_invalid_model_and_conflicting_legacy_fields_rejected_before_task(api, monkeypatch):
    client, repo, *_ = api
    monkeypatch.setattr(routes, 'get_model_entry', AsyncMock(return_value=None))
    bad = await client.post('/api/simulations', json=simulation(model_id='missing').model_dump())
    assert bad.status_code == 422
    payload = simulation(model_id='a').model_dump()
    payload['config']['llm_model'] = 'override'
    assert (await client.post('/api/simulations', json=payload)).status_code == 422
    assert await repo.list_runs() == []


async def test_injected_event_reaches_prediction_snapshot_and_synthesis_once():
    llm, kb = ScriptedLLM(), FakeLightRAG(context='')
    orch = KbSimOrchestrator(llm, llm.settings)
    orch.kb = kb
    async def on_event(index, alive, total):
        if index == 1:
            get_control().request_pause('injection')
    async def paused():
        get_control().add_user_event('injection', UserEventInput(description='INJECT_LOSS', impact=-1, severity=1))
        get_control().resume('injection')
    result = await orch.run('injection', simulation(), on_event=on_event, on_pause=paused)
    prediction_calls = [payload for schema, payload, _ in llm.calls if schema == 'StatePrediction']
    assert all(len(p['events']) == 1 for p in prediction_calls[:2])
    assert all(len(p['events']) == 2 for p in prediction_calls[2:])
    assert len(result.event_comparisons[1].event_summaries) == 2
    assert result.event_comparisons[1].event_summaries[1].event_id.startswith('user_')
    assert result.state_trace[2].state.metrics[0].value < result.state_trace[0].state.metrics[0].value
    assert all('INJECT_LOSS' in docs['prds_branch_state.md'] for docs in kb.documents.values())
    synthesis = next(p for schema, p, _ in llm.calls if schema == 'SynthesisDraft')
    assert 'INJECT_LOSS' in json.dumps(synthesis)
    assert not get_control().list_pending_user_events('injection')
    get_control().cleanup('injection')


@pytest.mark.parametrize('schema', ['IntakeBrief', 'EventPlan', 'StrategyBatch', 'StatePrediction'])
async def test_core_failure_never_becomes_success(api, monkeypatch, schema):
    client, repo, _, created, _ = api
    monkeypatch.setattr(routes, 'LLMClient', lambda settings: ScriptedLLM(settings, fail=schema))
    response = await client.post('/api/simulations', json=simulation().model_dump())
    rid = response.json()['simulation_id']
    await wait_finished(rid)
    progress = (await client.get(f'/api/simulations/{rid}')).json()
    assert progress['status'] == 'failed'
    assert progress['failure']['stage']
    assert 'SECRET_KEY' not in json.dumps(progress)
    assert (await client.get(f'/api/simulations/{rid}/result')).status_code == 409
    assert await repo.get_result(rid) is None


async def test_synthesis_failure_preserves_results_with_warning(api, monkeypatch):
    client, *_ = api
    monkeypatch.setattr(routes, 'LLMClient', lambda settings: ScriptedLLM(settings, fail='SynthesisDraft'))
    rid = (await client.post('/api/simulations', json=simulation().model_dump())).json()['simulation_id']
    await wait_finished(rid)
    result = (await client.get(f'/api/simulations/{rid}/result')).json()
    assert result['branches'] and not result['synthesis']['recommended_roadmap']
    assert any(w['code'] == 'synthesis_failed' for w in result['warnings'])
    assert (await client.get(f'/api/simulations/{rid}')).json()['warnings'] == result['warnings']


@pytest.mark.parametrize('operation', ['query_contexts', 'copy_workspace', 'retrieve_context', 'replace_document'])
async def test_required_kb_failure_stops_run(api, operation):
    client, _, _, _, kb = api
    setattr(kb, operation, AsyncMock(side_effect=RuntimeError('private provider details')))
    rid = (await client.post('/api/simulations', json=simulation(kb_category_ids=['source']).model_dump())).json()['simulation_id']
    await wait_finished(rid)
    progress = (await client.get(f'/api/simulations/{rid}')).json()
    assert progress['status'] == 'failed'
    assert 'private provider details' not in json.dumps(progress)


async def test_cancel_paused_task_waits_for_all_children(api):
    client, repo, *_ = api
    rid = await repo.create_run(simulation())
    paused, finished = asyncio.Event(), asyncio.Event()
    async def work():
        try:
            get_control().request_pause(rid)
            async def mark():
                await repo.update_progress(rid, status=SimulationStatus.PAUSED)
                paused.set()
            await get_control().maybe_pause_after_event(rid, mark, lambda: asyncio.sleep(0))
        finally:
            finished.set()
    get_tasks().start(rid, work())
    await paused.wait()
    response = await client.post(f'/api/simulations/{rid}/cancel')
    assert response.json()['status'] == 'cancelled'
    assert finished.is_set()
    assert not get_control().is_paused(rid)


async def test_delete_cancels_before_cleanup_and_retains_record_on_cleanup_failure(api):
    client, repo, _, _, kb = api
    rid = await repo.create_run(simulation())
    started, stopped = asyncio.Event(), asyncio.Event()
    async def work():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
    get_tasks().start(rid, work())
    await started.wait()
    async def broken_list():
        assert stopped.is_set()
        raise RuntimeError('unavailable')
    kb.list_workspaces = broken_list
    assert (await client.delete(f'/api/simulations/{rid}')).status_code == 503
    assert await repo.get_run(rid)
    kb.list_workspaces = AsyncMock(return_value=[])
    assert (await client.delete(f'/api/simulations/{rid}')).status_code == 200
    assert await repo.get_run(rid) is None


async def test_interruption_retains_inputs_retry_creates_new_record_and_checks_model(api, monkeypatch):
    client, repo, *_ = api
    original = simulation(model_id='deleted')
    rid = await repo.create_run(original)
    await repo.interrupt_active_runs()
    assert (await repo.get_progress(rid)).status == SimulationStatus.INTERRUPTED
    monkeypatch.setattr(routes, 'get_model_entry', AsyncMock(return_value=None))
    assert (await client.post(f'/api/simulations/{rid}/retry')).status_code == 422
    entry = dict(id='replacement', model='new-model', api_key='new-key', provider='openai')
    monkeypatch.setattr(routes, 'get_model_entry', AsyncMock(return_value=entry))
    response = await client.post(f'/api/simulations/{rid}/retry', json={'model_id': 'replacement'})
    new_id = response.json()['simulation_id']
    await wait_finished(new_id)
    assert new_id != rid
    assert (await repo.get_input(new_id)).goal == original.goal
    assert (await repo.get_input(rid)).config.model_id == 'deleted'
    assert (await repo.get_progress(rid)).status == SimulationStatus.INTERRUPTED


async def test_failure_or_cancellation_does_not_leave_sibling_tasks():
    child_started, child_stopped = asyncio.Event(), asyncio.Event()
    async def child():
        child_started.set()
        try:
            await asyncio.Event().wait()
        finally:
            child_stopped.set()
    async def boom():
        await child_started.wait()
        raise ValueError('failure')
    with pytest.raises(ValueError):
        await gather_owned(child(), boom())
    assert child_stopped.is_set()


async def test_cancelled_result_cannot_be_overwritten_by_late_save(api):
    _, repo, *_ = api
    from prds.models.domain import SimulationResult
    rid = await repo.create_run(simulation())
    await repo.update_progress(rid, status=SimulationStatus.CANCELLED)
    await repo.save_result(rid, SimulationResult(simulation_id=rid))
    assert (await repo.get_progress(rid)).status == SimulationStatus.CANCELLED
    assert await repo.get_result(rid) is None


async def test_final_event_cannot_be_paused(api):
    client, repo, *_ = api
    from prds.models.domain import SimulationPhase
    rid = await repo.create_run(simulation())
    await repo.update_progress(rid, status=SimulationStatus.RUNNING, phase=SimulationPhase.BRANCH_SIM)
    get_control().set_can_pause(rid, False)
    assert (await client.post(f'/api/simulations/{rid}/pause')).status_code == 409
    get_control().cleanup(rid)


async def test_failed_index_is_not_treated_as_processed():
    kb = LightRAGClient()
    kb._client = lambda: mock_transport_client(lambda r: httpx.Response(200, json={'documents': [{'status': 'failed'}]}))
    with pytest.raises(RuntimeError, match='indexing failed'):
        await kb.wait_indexed('track', timeout=0.1)


async def test_old_database_migrates_without_reinterpreting_history(tmp_path):
    import sqlite3
    path = tmp_path / 'old.db'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE simulation_runs (id VARCHAR(64) PRIMARY KEY, status VARCHAR(32), phase VARCHAR(32), current_event_index INTEGER, total_events INTEGER, total_agents INTEGER, alive_agents INTEGER, progress_pct FLOAT, input_json TEXT, result_json TEXT, error VARCHAR(1024), created_at DATETIME, updated_at DATETIME)')
        db.execute('INSERT INTO simulation_runs VALUES (?, ?, ?, 0, 2, 2, 2, 100, ?, ?, NULL, NULL, NULL)',
                   ('old', 'completed', 'completed', simulation().model_dump_json(), '{"simulation_id":"old"}'))
    repo = SimulationRepository(Settings(prds_database_url=f'sqlite+aiosqlite:///{path}'))
    try:
        await repo.init_db()
        assert (await repo.get_progress('old')).model_info is None
        assert (await repo.get_result('old')).warnings == []
    finally:
        await repo.engine.dispose()


async def test_actual_provider_calls_use_request_local_credentials(monkeypatch):
    from types import SimpleNamespace
    from prds.llm.client import LLMClient
    calls = []
    async def completion(**kwargs):
        calls.append(kwargs)
        await asyncio.sleep(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='ok'))])
    monkeypatch.setattr('litellm.acompletion', completion)
    first = LLMClient(Settings(openai_api_key='a-secret', prds_llm_model='a-model', prds_llm_provider='openai', prds_llm_api_base='https://a.example/v1'))
    second = LLMClient(Settings(openai_api_key='b-secret', prds_llm_model='b-model', prds_llm_provider='openai', prds_llm_api_base='https://b.example/v1'))
    await asyncio.gather(first.complete('system', 'one'), second.complete('system', 'two'))
    assert {(c['api_base'], c['api_key'], c['model']) for c in calls} == {
        ('https://a.example/v1', 'a-secret', 'openai/a-model'),
        ('https://b.example/v1', 'b-secret', 'openai/b-model'),
    }


async def test_async_snapshot_delete_finishes_before_insert():
    calls = []
    def handler(request):
        path = request.url.path
        calls.append(path)
        if path == '/documents/delete_document':
            return httpx.Response(200, json={'status': 'deletion_started'})
        if path == '/documents/pipeline_status':
            return httpx.Response(200, json={'busy': False})
        if path == '/documents':
            return httpx.Response(200, json={'statuses': {}})
        if path == '/documents/text':
            return httpx.Response(200, json={'track_id': 'new-track'})
        return httpx.Response(200, json={'documents': [{'status': 'processed'}]})
    kb = LightRAGClient()
    kb._client = lambda: mock_transport_client(handler)
    assert await kb.replace_document('new', 'state.md', workspace='branch', timeout=1)
    assert calls.index('/documents/pipeline_status') < calls.index('/documents/text')
    assert calls.index('/documents') < calls.index('/documents/text')


async def test_async_delete_that_left_old_snapshot_cannot_insert_new_one():
    from prds.kb.client import doc_id_for_source
    def handler(request):
        if request.url.path == '/documents/delete_document':
            return httpx.Response(200, json={'status': 'deletion_started'})
        if request.url.path == '/documents/pipeline_status':
            return httpx.Response(200, json={'busy': False})
        if request.url.path == '/documents':
            return httpx.Response(200, json={'statuses': {'processed': [{'id': doc_id_for_source('state.md')}]}})
        pytest.fail('Insertion must not start before the previous revision is removed')
    kb = LightRAGClient()
    kb._client = lambda: mock_transport_client(handler)
    with pytest.raises(RuntimeError, match='not deleted'):
        await kb.replace_document('new', 'state.md', workspace='branch', timeout=1)


async def test_partial_fork_failure_never_drops_a_selected_source():
    from prds.kbsim.branches import BranchManager
    kb = FakeLightRAG()
    original = kb.copy_workspace
    async def copy(source, target, name):
        if source == 'broken':
            raise RuntimeError('unavailable')
        return await original(source, target, name)
    kb.copy_workspace = copy
    manager = BranchManager(kb, Settings(openai_api_key='test'), simulation_id='partial-fork')
    with pytest.raises(SimulationFailure):
        await manager.fork(branch_count=2, source_ids=['healthy', 'broken'], baseline_doc='baseline')


async def test_task_that_has_not_exited_cannot_be_reported_as_cancelled():
    manager = SimulationTaskManager()
    started, release = asyncio.Event(), asyncio.Event()
    async def slow_exit():
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            await release.wait()
    manager.start('slow', slow_exit())
    task = manager.tasks['slow']
    await started.wait()
    try:
        assert not await manager.cancel('slow', timeout=0.01)
        assert not task.done()
    finally:
        release.set()
        await task


async def test_delete_retains_record_when_task_cannot_exit(api, monkeypatch):
    client, repo, *_ = api
    rid = await repo.create_run(simulation())
    monkeypatch.setattr(get_tasks(), 'cancel', AsyncMock(return_value=False))
    assert (await client.delete(f'/api/simulations/{rid}')).status_code == 409
    assert await repo.get_run(rid) is not None


@pytest.mark.parametrize('payload', [{'status': 'error'}, None, 'unavailable'])
async def test_invalid_workspace_listing_is_not_successful_cleanup(payload):
    kb = LightRAGClient()
    kb._client = lambda: mock_transport_client(lambda r: httpx.Response(200, json=payload))
    with pytest.raises((RuntimeError, ValueError)):
        await kb.list_workspaces()


def test_missing_metric_value_cannot_become_a_zero_prediction():
    from pydantic import ValidationError
    from prds.kbsim.state import StatePrediction
    with pytest.raises(ValidationError):
        StatePrediction.model_validate({'narrative': 'Predicted', 'metrics': [{'name': 'score', 'reason': 'fact'}], 'confidence': 0.5, 'success': True})


async def test_startup_marks_all_incomplete_statuses_but_keeps_completed_history(api):
    _, repo, *_ = api
    from prds.models.domain import SimulationResult
    ids = []
    for status in (SimulationStatus.PENDING, SimulationStatus.RUNNING, SimulationStatus.PAUSED):
        rid = await repo.create_run(simulation())
        await repo.update_progress(rid, status=status, current_event_index=1)
        ids.append(rid)
    done = await repo.create_run(simulation())
    await repo.save_result(done, SimulationResult(simulation_id=done))
    await repo.interrupt_active_runs()
    for rid in ids:
        progress = await repo.get_progress(rid)
        assert progress.status == SimulationStatus.INTERRUPTED
        assert progress.current_event_index == 1
    assert (await repo.get_progress(done)).status == SimulationStatus.COMPLETED
