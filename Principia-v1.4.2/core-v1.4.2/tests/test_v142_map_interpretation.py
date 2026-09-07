from copy import deepcopy

from principia.application.facade import Principia
from principia.data_discovery.interpretation import explain_finding, explain_rule
from principia.data_discovery.rule_presentation import present_rules


def test_new_data_project_has_no_fabricated_camera(tmp_path):
    app = Principia.open(working_directory=tmp_path / 'working', cloud_root=tmp_path / 'cloud')
    try:
        home = app.research_sessions.create_data_discovery_home(source_ids=[], title='Blank', provider_profile_id='', model='')
        assert app.research_sessions.graph(home['session_id'])['viewport'] == {}
    finally:
        app.close()


def test_explanation_is_bound_to_active_terms_and_original_errors():
    rule = {'title': 'Short-horizon stellar flux response', 'target': 'stellar flux(t+1)',
            'equation_ast': {'op': 'add', 'children': [{'op':'variable','symbol':'x_0'}, {'op':'variable','symbol':'x_1'}]},
            'test': {'passed':True,'normalized_rmse':.8}, 'baseline_comparison':{'model':'persistence','test_nrmse':1},
            'interpretation': 'Technical response', 'sample_definition':'One acquisition'}
    before=deepcopy(rule)
    explained=present_rules([rule],[])[0]['plain_language_interpretation']
    assert 'recent history' in explained['summary']
    assert '20%' in explained['implication']
    assert 'repeating the latest reading' in explained['implication']
    assert 'not evidence of a causal mechanism' in ' '.join(explained['boundaries'])
    assert rule==before
    rule['test']['normalized_rmse']=1.2
    assert 'higher' in explain_rule(rule)['implication']


def test_spatial_explanation_omits_unused_features_and_retains_whole_field_scope():
    rule={'title':'Spatial response','executor_id':'spatial_event_law',
          'equation_ast':{'op':'variable','symbol':'x_0'},
          'variable_bindings':[{'symbol':'x_0','transform':'r^2'},{'symbol':'x_1','transform':'nonlocal_kernel[0.1]'}],
          'test':{'mean_map_mape_percent':1.26801234,'worst_map_mape_percent':2.4208,'passed':True}}
    result=explain_rule(rule)
    assert 'distance from the field center' in result['explanation']
    assert 'neighboring input' not in result['explanation']
    assert '1.27%' in result['implication'] and '2.42%' in result['implication']
    assert 'complete field objects' in ' '.join(result['boundaries'])


def test_observation_context_preserves_alternatives_and_falsifier():
    finding={'claim':'Signal covaries with pupil size.', 'interpretation':'Motion alone does not explain the association.',
             'mechanism':'Both measurements may share an arousal input.', 'practical_value':'Condition comparisons on movement.',
             'confounders':['Shared arousal could drive both.'], 'limits':['One acquisition.','One acquisition.'],
             'next_validation':'Vary arousal while holding motion fixed.'}
    before=deepcopy(finding)
    result=explain_finding(finding)
    assert result['explanation_label']=='Possible explanation'
    assert result['next_check']==finding['next_validation']
    assert len(result['boundaries'])==2
    assert finding==before


def test_live_model_catalog_filters_nonchat_models_without_writing_credentials(tmp_path, monkeypatch):
    import httpx

    app = Principia.open(working_directory=tmp_path / 'working', cloud_root=tmp_path / 'cloud')
    try:
        app.local.save_provider_credential('siliconflow', 'private-test-key')
        before=app.local.credentials.path.read_bytes()
        def catalog(url, **kwargs):
            assert kwargs['follow_redirects'] is False
            return httpx.Response(200, request=httpx.Request('GET',url), json={'data':[
                {'id':'Qwen/Qwen3-VL-8B-Instruct'}, {'id':'Qwen/Qwen3-VL-Embedding-8B'},
                {'id':'Qwen/Qwen3-VL-Reranker-8B'}, {'id':'deepseek-ai/DeepSeek-V4-Flash'},
                {'id':'https://untrusted.invalid'}, {'unexpected':'record'},
            ]})
        monkeypatch.setattr('principia.local.service.httpx.get',catalog)
        result=app.local.provider_model_catalog('siliconflow')
        assert result['available'] is True
        assert result['vision_models']==['Qwen/Qwen3-VL-8B-Instruct']
        assert 'https://untrusted.invalid' not in result['models']
        assert app.local.credentials.path.read_bytes()==before
        assert 'private-test-key' not in str(result)
    finally:
        app.close()
