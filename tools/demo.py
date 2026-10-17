#!/usr/bin/env python3
"""Run safe, offline dummy Junos logs through the production parser and matcher."""
import argparse
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'junos-fpc-errors'))
from jls.catalogue import read_catalogue, validate, match, digest
from jls.parser import parse


def run():
    catalogue = read_catalogue(ROOT / 'catalogue/catalogue.json')
    compiled = validate(catalogue)
    results = []
    for case in json.loads((ROOT / 'examples/junos-demo.json').read_text()):
        parsed = parse(case['event'])
        hits, errors = match(parsed['message'], compiled)
        ids = sorted(r['id'] for r in hits)
        passed = (ids == sorted(case['expected_rule_ids']) and not errors
                  and parsed['device'] == case['expected_device'] and parsed['fpc'] == case['expected_fpc'])
        results.append(dict(id=case['id'], name=case['name'], passed=passed,
                            expected_rule_ids=case['expected_rule_ids'], actual_rule_ids=ids,
                            device=parsed['device'], fpc=parsed['fpc'], pfe=parsed['pfe'], asic=parsed['asic'],
                            timestamp_source=parsed['timestamp_source'], evaluation_errors=errors))
    return dict(catalogue_version=catalogue['version'], catalogue_digest=digest(catalogue),
                active_rules=len(compiled), passed=sum(r['passed'] for r in results), total=len(results), results=results)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Optional JSON results path')
    args = parser.parse_args()
    report = run()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    for r in report['results']:
        print(f"{r['id']} {'PASS' if r['passed'] else 'FAIL'} {r['name']}: {', '.join(r['actual_rule_ids']) or 'no catalogue match'}")
    print(f"{report['passed']}/{report['total']} passed; {report['active_rules']} active rules")
    sys.exit(0 if report['passed'] == report['total'] else 1)
