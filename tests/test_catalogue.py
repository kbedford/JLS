import copy
import pytest
from jls.catalogue import validate, match, read_catalogue


def test_matching_and_normalisation(catalogue):
    compiled = validate(catalogue)
    assert len(match('TESTCHIP(7):\xa0parity error\u200b',compiled)[0]) == 1
    assert not match('TESTCHIP(7): parity corrected',compiled)[0]


@pytest.mark.parametrize('pattern', ['[','.*',''])
def test_bad_regex_rejected(catalogue, pattern):
    catalogue['rules'][0]['pattern'] = pattern
    with pytest.raises(ValueError): validate(catalogue)


def test_duplicate_id_rejected(catalogue):
    catalogue['rules'].append(copy.deepcopy(catalogue['rules'][0]))
    with pytest.raises(ValueError): validate(catalogue)


def test_failed_examples_rejected(catalogue):
    catalogue['rules'][0]['positive_examples'] = ['unrelated']
    with pytest.raises(ValueError): validate(catalogue)


def test_empty_active_catalogue_rejected(catalogue):
    catalogue['rules'][0]['enabled'] = False
    with pytest.raises(ValueError): validate(catalogue)


def test_regex_timeout_isolated():
    import regex
    hits, errors = match('a'*65530+'!', [({'id':'slow'},regex.compile('(a+)+$')), ({'id':'good'},regex.compile('!'))])
    assert hits == [{'id':'good'}]
    assert errors == [{'rule_id':'slow','error':'regex_timeout'}]


def test_private_catalogue_if_supplied():
    import os
    path = os.getenv('JLS_CATALOGUE_TEST_PATH')
    if not path: pytest.skip('Private catalogue not provided')
    c = read_catalogue(path)
    assert all(r['enabled'] for r in c['rules'])
    for r in c['rules']:
        assert r['sources']
