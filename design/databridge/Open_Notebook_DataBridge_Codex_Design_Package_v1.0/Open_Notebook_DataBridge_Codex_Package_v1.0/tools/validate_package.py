"""Self-check the DataBridge *design package* before handoff.

This does not test the future Open Notebook codebase or live external services.
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = [
    'README.md', 'EXECUTIVE_DESIGN_BRIEF.md', 'CODEX_START_HERE.md',
    *[f'docs/{i:02d}_{name}.md' for i,name in [
        (1,'PRODUCT_SCOPE'),(2,'ARCHITECTURE'),(3,'REQUIREMENTS'),
        (4,'OPEN_DATA_INGESTION'),(5,'MCP_DATABASE_INTEGRATION'),
        (6,'LLM_LITELLM_COSTS'),(7,'SECURITY'),(8,'UI_AND_API'),
        (9,'PROVENANCE_DATA_MODEL'),(10,'DOT_DEMO'),(11,'TEST_PLAN'),
        (12,'ROADMAP'),(13,'ADRS_AND_QUESTIONS'),(14,'REFERENCES')]],
    'spec/openapi.yaml', 'config/.env.example',
    'config/litellm-config.template.yaml', 'config/compose-extension.reference.yaml',
    'diagrams/architecture.mmd', 'diagrams/ingestion_sequence.mmd',
    'fixtures/ntd_synthetic.csv', 'fixtures/census_synthetic.csv',
    'fixtures/noaa_synthetic.csv', 'fixtures/geography_crosswalk_synthetic.csv',
    'tests/test_fixture_baseline.py',
]


def check_openapi_refs(data):
    def follow(pointer):
        cur = data
        for part in pointer.lstrip('#/').split('/'):
            cur = cur[part.replace('~1', '/').replace('~0', '~')]
        return cur
    def traverse(x):
        if isinstance(x, dict):
            if '$ref' in x and x['$ref'].startswith('#/'):
                follow(x['$ref'])
            for value in x.values(): traverse(value)
        elif isinstance(x, list):
            for value in x: traverse(value)
    traverse(data)


def main():
    missing = [f for f in REQUIRED if not (ROOT / f).is_file()]
    if missing: raise AssertionError(f'Missing files: {missing}')
    env = (ROOT / 'config/.env.example').read_text()
    for token in ['LLM_MODEL=gpt-6-astra', 'OPENAI_API_BASE=',
                  'DATAGOV_BASE_URL=', 'DBHUB_MCP_URL=', 'GOOGLE_TOOLBOX_MCP_URL=']:
        assert token in env, token
    for name in ['README.md','CODEX_START_HERE.md','EXECUTIVE_DESIGN_BRIEF.md']:
        text = (ROOT / name).read_text()
        for dest in re.findall(r'\]\(([^)]+)\)', text):
            if dest.startswith(('https://','http://','#')): continue
            assert (ROOT / dest).exists(), f'{name}: missing local link {dest}'
    try:
        import yaml
    except ImportError:
        raise SystemExit('Install PyYAML for full package YAML verification.')
    for name in ['spec/openapi.yaml','config/litellm-config.template.yaml',
                 'config/compose-extension.reference.yaml']:
        data=yaml.safe_load((ROOT / name).read_text())
        assert isinstance(data, dict), name
        if name == 'spec/openapi.yaml':
            assert len(data['paths']) >= 15
            check_openapi_refs(data)
    try:
        import jsonschema
        for file in (ROOT / 'spec/schemas').glob('*.json'):
            schema = json.loads(file.read_text())
            jsonschema.Draft202012Validator.check_schema(schema)
    except ImportError:
        for file in (ROOT / 'spec/schemas').glob('*.json'):
            json.loads(file.read_text())
    subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s',
                    str(ROOT / 'tests'), '-v'], check=True)
    render_file = ROOT/'config/render_litellm_config.py'
    subprocess.run([sys.executable,'-m','py_compile',str(render_file)],check=True)
    all_md = list(ROOT.rglob('*.md'))
    assert all('\u200b' not in p.read_text() for p in all_md), 'Unexpected invisible character'
    print(f'Package validation passed: {len(REQUIRED)} required files, '
          f'{len(all_md)} Markdown documents, {len(list((ROOT/"spec/schemas").glob("*.json")))} JSON schemas, '
          f'{len(data)} keys in last parsed YAML')


if __name__=='__main__':
    main()
