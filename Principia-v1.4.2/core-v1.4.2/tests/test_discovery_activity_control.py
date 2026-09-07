from __future__ import annotations

import json
import threading
import time
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from principia import Principia
from principia.cancellation import (
    TaskCancelled,
    cancellation_scope,
    check_cancelled,
    current_control,
)
from principia.data_discovery.sandbox import AnalysisSandbox
from principia.domain import JobRecord
from principia.providers import ModelPolicy, OpenAICompatibleProvider


@pytest.mark.parametrize('retry, metadata', [(False, False), (True, False), (False, True)])
def test_stop_closes_real_http_and_retry_wait_without_an_abandoned_worker(retry, metadata):
    entered, release, cancel = threading.Event(), threading.Event(), threading.Event()
    attempts, results = [], []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get('Content-Length', '0')))
            attempts.append(1)
            if retry:
                self.send_response(429)
                self.send_header('Retry-After', '120')
                self.end_headers()
                entered.set()
            else:
                entered.set()
                release.wait(10)
                try:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"choices":[{"message":{"content":"{}"}}]}')
                except (BrokenPipeError, ConnectionResetError):
                    pass

        do_GET = do_POST

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    serving = threading.Thread(target=server.serve_forever, daemon=True)
    serving.start()
    provider = OpenAICompatibleProvider(ModelPolicy(mode='local', provider='local', model='fixture', base_url=f'http://127.0.0.1:{server.server_port}/v1'), api_key='test', timeout=60)

    def work():
        try:
            with cancellation_scope(cancel):
                if metadata:
                    from principia_retrieval.sources import _fetch_bytes
                    results.append(_fetch_bytes(f'http://127.0.0.1:{server.server_port}/metadata', 60, control_token=current_control()))
                else:
                    results.append(provider._request([{'role': 'user', 'content': 'fixture'}]))
        except TaskCancelled:
            results.append('cancelled')

    worker = threading.Thread(target=work)
    worker.start()
    try:
        assert entered.wait(5)
        if retry:
            time.sleep(.2)  # let the client enter Retry-After backoff
        start = time.monotonic()
        cancel.set()
        worker.join(2)
        assert not worker.is_alive(), 'stop must join the HTTP owner, not abandon it'
        assert time.monotonic() - start < 2
        assert results == ['cancelled']
        assert len(attempts) == 1
    finally:
        cancel.set()
        release.set()
        worker.join(5)
        provider.close()
        server.shutdown()
        server.server_close()


def test_cancelled_sandbox_reaps_child_and_writes_cancel_audit(tmp_path, monkeypatch):
    sandbox = AnalysisSandbox(wall_timeout_seconds=60)
    if not sandbox.available:
        pytest.skip('host isolation unavailable')
    import principia.data_discovery.sandbox as module
    popen, children, cancel, outcome = module.subprocess.Popen, [], threading.Event(), []

    def tracked(*args, **kwargs):
        child = popen(*args, **kwargs)
        if kwargs.get('cwd') == tmp_path / 'sandbox':
            children.append(child)
        return child

    monkeypatch.setattr(module.subprocess, 'Popen', tracked)

    def work():
        try:
            with cancellation_scope(cancel):
                sandbox.run(code='while True:\n    pass\nRESULT={}', inputs={}, artifact_root=tmp_path / 'sandbox')
        except TaskCancelled:
            outcome.append('cancelled')

    worker = threading.Thread(target=work)
    worker.start()
    try:
        deadline = time.monotonic() + 5
        while not children and time.monotonic() < deadline:
            time.sleep(.01)
        assert children
        cancel.set()
        worker.join(2)
        assert not worker.is_alive()
        assert outcome == ['cancelled']
        assert children[0].poll() is not None
        audit = json.loads((tmp_path / 'sandbox' / 'sandbox-audit.json').read_text())
        assert 'analysis cancelled' in audit['violations']
    finally:
        cancel.set()
        worker.join(5)


def test_worker_cancellation_is_not_swallowed_by_analysis_fallback(tmp_path, monkeypatch):
    app = Principia.open(working_directory=tmp_path / 'working', cloud_root=tmp_path / 'cloud')
    source = tmp_path / 'source'
    source.mkdir()
    app.repository.register_source('src:test', source, 'fixture://test', 'Test data')
    entered = threading.Event()

    def blocked_inventory(**kwargs):
        entered.set()
        while True:
            try:
                check_cancelled()
            except Exception:
                pytest.fail('cancellation incorrectly entered ordinary fallback')
            time.sleep(.02)

    monkeypatch.setattr(app.data_discovery.inventory_adapter, 'inventory', blocked_inventory)
    try:
        study = app.data_discovery.create(source_ids=['src:test'], provider='', defer=True)
        assert entered.wait(5)
        future = app.data_discovery._futures[study['study_id']]
        requested = app.data_discovery.cancel(study['study_id'])
        assert requested['state'] in {'cancelling', 'cancelled'}
        future.result(timeout=2)
        assert app.data_discovery.cancel(study['study_id'])['state'] == 'cancelled'
        assert app.repository.data_study(study['study_id'])['state'] == 'cancelled'
        assert app.repository.data_study_counts(study['study_id'])['tests'] == 0
        assert study['study_id'] not in app.data_discovery._futures
    finally:
        app.close()


@pytest.mark.parametrize('state', ['succeeded', 'partial', 'failed', 'cancelled', 'interrupted', 'data_insufficient'])
def test_late_stop_preserves_every_terminal_state(tmp_path, state):
    app = Principia.open(working_directory=tmp_path / 'working', cloud_root=tmp_path / 'cloud')
    try:
        app.repository.save_job(JobRecord(job_id='job:done', kind='data_discovery', state='succeeded'))
        app.repository.create_data_study({'study_id': 'study:done', 'job_id': 'job:done', 'state': state, 'phase': 'synthesize'})
        before = app.repository.data_study('study:done')
        assert app.data_discovery.cancel('study:done')['state'] == state
        assert app.repository.data_study('study:done') == before
    finally:
        app.close()


def test_cancel_wins_before_final_publication(tmp_path):
    # Phase changes use the same publication lock and cancellation scope.
    app = Principia.open(working_directory=tmp_path / 'working', cloud_root=tmp_path / 'cloud')
    cancel = threading.Event()
    try:
        app.repository.save_job(JobRecord(job_id='job:race', kind='data_discovery', state='running'))
        app.repository.create_data_study({'study_id': 'study:race', 'job_id': 'job:race', 'state': 'running', 'phase': 'inventory'})
        app.data_discovery._cancel['study:race'] = cancel
        future = Future()
        future.set_running_or_notify_cancel()
        app.data_discovery._futures['study:race'] = future
        app.data_discovery.cancel('study:race')
        with cancellation_scope(cancel), pytest.raises(TaskCancelled):
            app.data_discovery._set_phase('study:race', 'synthesize', .9, 'Too late')
        assert app.repository.data_study('study:race')['state'] == 'cancelling'
    finally:
        app.close()


def test_cancelled_metadata_task_keeps_a_cancelled_receipt(tmp_path):
    from principia.run import RunHandle
    app = Principia.open(working_directory=tmp_path / 'working', cloud_root=tmp_path / 'cloud')
    event = threading.Event()
    try:
        with cancellation_scope(event):
            control = current_control()
            with pytest.raises(TaskCancelled), RunHandle(app.workspace.storage, 'metadata-test', token=control) as run:
                event.set()
                control.check_cancelled()
        assert run.status.status == 'cancelled'
        assert app.workspace.storage.get_run(run.status.run_id).status == 'cancelled'
    finally:
        app.close()
