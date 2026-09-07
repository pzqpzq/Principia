from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from fastapi.testclient import TestClient

from principia import Principia
from principia.api import create_app
from principia.data_discovery.law_ast import ast_digest, evaluate
from principia.data_discovery.scientific_programs import (
    ScientificProgramBundle,
    _FittedModel,
    _model_equation,
    _select_parsimonious_candidate,
)
from principia.domain import (
    DataFinding,
    DataHypothesis,
    EquationNode,
    ScientificLawFamily,
    ScientificProgram,
)


@pytest.fixture
def product(tmp_path, monkeypatch):
    app = Principia.open(working_directory=tmp_path / 'workspace', cloud_root=tmp_path / 'cloud')
    for name in ('first', 'second'):
        source = tmp_path / name
        source.mkdir()
        app.repository.register_source('src:' + name, source, 'fixture://' + name, name)
    # Exercise real submission/persistence without provider or background work.
    monkeypatch.setattr(app.data_discovery, '_run', lambda *args: None)
    asgi = create_app(app, test_mode=True)
    client = TestClient(asgi, headers={'X-Principia-Session': asgi.state.session_token})
    yield app, client
    app.close()


def test_new_attempts_are_independent_and_replace_updates_inputs_without_reviving_old_success(product):
    app, client = product
    request = {'source_ids': ['src:first'], 'project_mode': 'new', 'provider': '', 'objective': 'First objective'}
    first = client.post('/api/v1/data-discoveries', json=request).json()
    second = client.post('/api/v1/data-discoveries', json={**request, 'session_id': first['session_id']}).json()
    assert first['session_id'] != second['session_id']
    app.research_sessions.consolidate_data_sessions()
    assert len(app.research_sessions.sessions()) == 2
    sid = first['session_id']
    with app.repository.connect() as conn:
        conn.execute("UPDATE data_studies SET state='succeeded' WHERE study_id=?", (first['study_id'],))
    revision = app.research_sessions.detail(sid, synchronize=False)['revision']
    replacement = client.post('/api/v1/data-discoveries', json={**request, 'project_mode': 'replace', 'session_id': sid, 'source_ids': ['src:second'], 'objective': 'Changed target', 'reasoning_model': 'changed-model', 'expected_session_revision': revision})
    assert replacement.status_code == 202, replacement.text
    study = replacement.json()
    assert study['session_id'] == sid
    assert study['request']['objective'] == 'Changed target'
    assert study['request']['reasoning_model'] == 'changed-model'
    assert app.research_sessions.detail(sid, synchronize=False)['source_ids'] == ['src:second']
    with app.repository.connect() as conn:
        conn.execute("UPDATE data_studies SET state='failed' WHERE study_id=?", (study['study_id'],))
    assert app.repository.latest_data_study_for_session(sid)['study_id'] == study['study_id']
    assert app.research_sessions.detail(sid, synchronize=False)['active_data_study']['study_id'] == study['study_id']
    assert next(s for s in app.research_sessions.sessions() if s['session_id'] == sid)['state'] == 'failed'
    assert len(app.repository.data_discovery_runs(sid)) == 2


def test_concurrent_replacement_has_one_owner_and_no_orphan_job(product):
    app, _ = product
    home = app.research_sessions.create_data_discovery_home(source_ids=['src:first'], title='Concurrency', provider_profile_id='', model='')
    def submit(_):
        try:
            return app.data_discovery.create(source_ids=['src:first'], provider='', session_id=home['session_id'], project_mode='replace')['study_id']
        except ValueError:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert results.count('conflict') == 1
    with app.repository.connect() as conn:
        assert conn.execute('SELECT count(*) FROM v14_jobs').fetchone()[0] == 1
        assert conn.execute('SELECT count(*) FROM data_studies').fetchone()[0] == 1


def _bundle(study_id):
    program = ScientificProgram(program_id='program:live', study_id=study_id, track='predictive_closure', title='Live formula', scientific_intent='Predict the measured response.', program_digest='a'*64)
    ast = EquationNode(op='variable', symbol='x')
    law = ScientificLawFamily(law_id='law:live', study_id=study_id, program_id=program.program_id, name='Live formula', family_kind='scaling', equation_ast=ast, canonical_ast_digest=ast_digest(ast), expression_latex='y=x', scientific_meaning='Predict the measured response.', target='y', scope='Test measurements', evidence_tier='internal_locked_validation', gate_summary={'passed': True}, test_ids=['test:live'], family_digest='b'*64)
    return ScientificProgramBundle(programs=(program,), laws=(law,))


def test_bundle_publication_is_atomic_and_rolls_back_on_failure(product, monkeypatch):
    app, _ = product
    study = app.data_discovery.create(source_ids=['src:first'], provider='')['study_id']
    bundle = _bundle(study)
    original = app.repository.save_scientific_law_family
    def fail_after_first_record(law):
        # A different connection cannot see half the publication.
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(app.repository.scientific_programs, study).result() == []
        original(law)
        raise RuntimeError('simulated disk failure')
    monkeypatch.setattr(app.repository, 'save_scientific_law_family', fail_after_first_record)
    with pytest.raises(RuntimeError, match='disk failure'):
        app.data_discovery._persist_scientific_program_bundle(bundle)
    assert app.repository.scientific_programs(study) == []
    assert app.repository.scientific_law_families(study) == []
    monkeypatch.setattr(app.repository, 'save_scientific_law_family', original)
    app.data_discovery._persist_scientific_program_bundle(bundle)
    assert len(app.repository.scientific_programs(study)) == 1
    assert len(app.repository.scientific_law_families(study)) == 1


def test_live_rule_can_be_inspected_before_finding_is_published(product):
    app, client = product
    study = app.data_discovery.create(source_ids=['src:first'], provider='')['study_id']
    app.data_discovery._persist_scientific_program_bundle(_bundle(study))
    app.repository.save_data_hypothesis(DataHypothesis(hypothesis_id='hyp:live', study_id=study, claim='A measured response follows the input.', origin='data_driven', expected_relationship='Linear', input_view_ids=['view:live'], falsifier='Fails on new data.'))
    app.repository.save_data_test({'test_id':'test:live','study_id':study,'hypothesis_id':'hyp:live','plan_id':'plan:live','state':'completed','result_digest':'c'*64,'finding_id':'finding:later','estimate':{'r_squared':.9}})
    endpoint = f'/api/v1/data-discoveries/{study}'
    rule = client.get(endpoint + '/rules').json()['items'][0]
    assert rule['finding_id'] == '' and rule['finding_pending'] is True
    detail = client.get(endpoint + '/laws/law:live')
    assert detail.status_code == 200
    assert detail.json()['tests'][0]['estimate']['r_squared'] == .9
    app.repository.save_data_finding(DataFinding(finding_id='finding:later', study_id=study, title='Completed context', claim='A measured response is supported.', interpretation='Measured empirical relationship.', mechanism='Unknown', status='supported_candidate'))
    rule = client.get(endpoint + '/rules').json()['items'][0]
    assert rule['finding_id'] == 'finding:later' and rule['finding_pending'] is False


def test_selection_prefers_compact_law_only_within_independent_development_uncertainty():
    best = dict(spec='complex', selection_score=1., development_standard_error=.1, validation_mape_percent=.9, complexity=24, ridge=.01)
    compact = {**best, 'spec':'compact', 'selection_score':1.06, 'validation_mape_percent':.96, 'complexity':4}
    too_poor = {**compact, 'spec':'underfit', 'selection_score':1.3, 'complexity':2}
    validation_failure = {**compact, 'validation_mape_percent':1.04, 'complexity':1}
    assert _select_parsimonious_candidate([best, compact, too_poor, validation_failure]) is compact
    assert _select_parsimonious_candidate([{**best, 'development_standard_error':0}, compact])['spec'] == 'complex'


def test_native_coefficients_remove_redundant_normalization_without_changing_predictions():
    model = _FittedModel('test', .1, ('a','b'), np.array([100.,-.01]), np.array([.003,500.]), np.array([.04,-.8]), 2.)
    x = np.array([[99.998,8.],[100.002,-4.]])
    ast, parameters = _model_equation(model)
    assert set(parameters) == {'T_ref','b','c_0','c_1'}
    prediction = evaluate(ast, {'z_0':x[:,0], 'z_1':x[:,1]}, parameters)
    assert np.allclose(prediction, np.exp(model.intercept+((x-model.means)/model.scales)@model.coefficients), rtol=1e-12)
    # A fixed reference is not counted as an estimated coefficient.
    assert parameters['T_ref'] == 1


def test_sparse_fitting_discards_irrelevant_terms_inside_development(monkeypatch):
    from types import SimpleNamespace

    from principia.data_discovery import scientific_programs as spatial

    rng = np.random.default_rng(29)
    objects = []
    names = tuple(f'input_{i}' for i in range(9))
    for group in range(12):
        design = rng.normal(size=(60, len(names)))
        target = np.exp(2 + .4 * design[:, 0] - .1 * design[:, 1])
        objects.append(SimpleNamespace(object_id=f'unit:{group}', locator={}, design=design, target=target))
    monkeypatch.setattr(spatial, '_features', lambda item, *_: (item.design, names))
    model = spatial._fit(objects, 'sparse_kernel_0.001', (), .001)
    assert np.flatnonzero(model.coefficients).tolist() == [0, 1]
    ast, parameters = _model_equation(model)
    assert set(parameters) == {'T_ref', 'b', 'c_0', 'c_1'}
    held = rng.normal(size=(100, len(names)))
    predicted = evaluate(ast, {f'z_{i}': held[:, i] for i in range(len(names))}, parameters)
    assert np.mean(np.abs(predicted / np.exp(2+.4*held[:,0]-.1*held[:,1])-1)) < .003


def test_rule_inspector_receives_only_its_own_compact_frontier(product):
    from principia.domain import LawCandidate

    app, _ = product
    study = app.data_discovery.create(source_ids=['src:first'], provider='')['study_id']
    bundle = _bundle(study)
    app.data_discovery._persist_scientific_program_bundle(bundle)
    second = bundle.laws[0].model_copy(update={'law_id':'law:other'})
    app.repository.save_scientific_law_family(second)
    for law_id in ('law:live','law:other'):
        app.repository.save_scientific_law_candidate(LawCandidate(candidate_id=law_id+':candidate', study_id=study, program_id='program:live', law_id=law_id, equation_ast=bundle.laws[0].equation_ast, complexity=1, development_score=.2, validation_score=.3, state='champion', candidate_digest='d'*64))
    detail = app.data_discovery.law(study, 'law:live')
    assert len(detail['candidate_frontier']) == 1
    assert detail['candidate_frontier'][0]['law_id'] == 'law:live'
    assert detail['candidate_frontier'][0]['development_score'] == .2
    assert 'equation_ast' not in detail['candidate_frontier'][0]
    assert len(app.data_discovery.program(study, 'program:live')['candidate_frontier']) == 2


def test_sparse_intercept_only_candidates_remain_executable():
    from principia.data_discovery.law_ast import associative_node

    model = _FittedModel('sparse_kernel_0.01', .1, ('unused',), np.array([4.]), np.array([2.]), np.array([0.]), 2.)
    ast, parameters = _model_equation(model)
    assert set(parameters) == {'T_ref', 'b'}
    assert evaluate(ast, {}, parameters) == pytest.approx(np.exp(2.))
    assert evaluate(associative_node('add', []), {}, {}) == 0
    assert evaluate(associative_node('multiply', []), {}, {}) == 1


def test_spatial_display_uses_descriptive_features_and_preserves_transform_identity():
    from principia.data_discovery.rule_presentation import present_rules

    rule = {'title':'Spatial response', 'equation_ast':{'op':'variable','symbol':'z_1'}, 'variable_bindings':[{'symbol':'z_1','transform':'regime[input-regime:aabbcc]'}]}
    displayed = present_rules([rule], [])[0]['display_calibration']['symbols'][0]
    assert displayed['meaning'] == 'Input-defined group 1 indicator'
    assert displayed['transform'] == 'regime[input-regime:aabbcc]'
