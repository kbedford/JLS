import json
from pathlib import Path
import yaml
from jls.catalogue import read_catalogue

ROOT=Path(__file__).resolve().parents[1]


def test_deployment_contract():
    c=yaml.safe_load((ROOT/'docker-compose.yml').read_text())
    s=c['services']
    assert 'ports' not in s['postgres'] and 'ports' not in s['scanner']
    assert s['scanner']['read_only']
    assert s['scanner']['depends_on']['postgres']['condition']=='service_healthy'
    assert all('latest' not in v.get('image','') for v in s.values())
    assert all('healthcheck' in v for v in s.values())
    assert '514:5514/udp' in s['logstash']['ports'][0]
    pipeline=(ROOT/'config/logstash/pipeline.conf').read_text()
    assert 'retry_failed => true' in pipeline and 'format => "json"' in pipeline
    assert yaml.safe_load((ROOT/'config/logstash/logstash.yml').read_text())['queue.type']=='persisted'


def test_dashboard_and_example():
    d=json.loads((ROOT/'config/grafana/dashboards/jls.json').read_text())
    assert d['uid']=='jls-operations'
    assert len(d['panels'])>=8
    read_catalogue(ROOT/'examples/catalogue.json')
