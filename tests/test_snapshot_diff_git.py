"""TDD tests for dkkd.snapshot_diff's git plumbing and run_diff orchestration."""
import json
from pathlib import Path
from unittest.mock import patch

from dkkd.snapshot_diff import (
    load_snapshot_from_git,
    _commit_date,
    _append_status_transitions,
    run_diff,
)


# --- load_snapshot_from_git ---

@patch('dkkd.snapshot_diff._git')
def test_load_snapshot_from_git_parses_pairs(mock_git):
    mock_git.return_value = json.dumps([
        ['1', {'Id': '1', 'Name': 'A'}],
        ['2', {'Id': '2', 'Name': 'B'}],
    ])
    repo_root = Path('C:/repo')
    checkpoint_path = Path('C:/repo/brands/x/checkpoint.json')
    result = load_snapshot_from_git('abc123', checkpoint_path, repo_root)
    assert result == {'1': {'Id': '1', 'Name': 'A'}, '2': {'Id': '2', 'Name': 'B'}}
    args, kwargs = mock_git.call_args
    assert args == ('show', 'abc123:brands/x/checkpoint.json')
    assert kwargs['cwd'] == repo_root


@patch('dkkd.snapshot_diff._git')
def test_load_snapshot_from_git_missing_path_raises(mock_git):
    mock_git.side_effect = RuntimeError("fatal: path 'brands/x/checkpoint.json' does not exist in 'abc123'")
    repo_root = Path('C:/repo')
    checkpoint_path = Path('C:/repo/brands/x/checkpoint.json')
    try:
        load_snapshot_from_git('abc123', checkpoint_path, repo_root)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert 'abc123' in str(e)


# --- _commit_date ---

@patch('dkkd.snapshot_diff._git')
def test_commit_date_parses_iso_to_date_only(mock_git):
    mock_git.return_value = "2026-06-30T18:08:30+07:00\n"
    assert _commit_date('eda4e7a', Path('C:/repo')) == '2026-06-30'


# --- _append_status_transitions ---

def test_append_status_transitions_accumulates_across_calls(tmp_path):
    out_dir = tmp_path
    _append_status_transitions('brand', {'1': {'old_status': 'Operating', 'new_status': 'Closed',
                                                 'bracket': ['2026-06-01', '2026-06-30']}}, out_dir)
    _append_status_transitions('brand', {'2': {'old_status': 'Operating', 'new_status': 'Closed',
                                                 'bracket': ['2026-07-01', '2026-07-30']}}, out_dir)
    data = json.loads((out_dir / 'brand_status_transitions.json').read_text(encoding='utf-8'))
    assert len(data) == 2
    ids = {e['id'] for e in data}
    assert ids == {'1', '2'}


def test_append_status_transitions_is_idempotent(tmp_path):
    out_dir = tmp_path
    event = {'1': {'old_status': 'Operating', 'new_status': 'Closed',
                    'bracket': ['2026-06-01', '2026-06-30']}}
    _append_status_transitions('brand', event, out_dir)
    _append_status_transitions('brand', event, out_dir)
    data = json.loads((out_dir / 'brand_status_transitions.json').read_text(encoding='utf-8'))
    assert len(data) == 1


# --- run_diff ---

@patch('dkkd.snapshot_diff._commit_date')
@patch('dkkd.snapshot_diff.load_snapshot_from_git')
def test_run_diff_writes_report_and_transitions(mock_load_git, mock_commit_date, tmp_path):
    brand_dir = tmp_path / 'brand'
    out_dir = brand_dir / 'output'
    out_dir.mkdir(parents=True)
    checkpoint_path = brand_dir / 'checkpoint.json'
    checkpoint_path.write_text(json.dumps([
        ['1', {'Id': '1', 'Name': 'Store A', 'Operating_Status': 'Closed', 'Ho_Address': 'Addr'}],
    ]), encoding='utf-8')
    (brand_dir / 'config.yaml').write_text('slug: brand\nname: Brand\nbrand_regex: Brand\n', encoding='utf-8')

    mock_load_git.return_value = {
        '1': {'Id': '1', 'Name': 'Store A', 'Operating_Status': 'Operating', 'Ho_Address': 'Addr'},
    }
    mock_commit_date.return_value = '2026-06-01'

    with patch('dkkd.snapshot_diff.date') as mock_date_module:
        mock_date_module.today.return_value.isoformat.return_value = '2026-07-01'
        result = run_diff('brand', 'abc123', brands_dir=tmp_path)

    assert result['status_changes'] == {
        '1': {'old_status': 'Operating', 'new_status': 'Closed', 'bracket': ['2026-06-01', '2026-07-01']}
    }
    report_path = out_dir / 'brand_snapshot_diff_2026-07-01.md'
    assert report_path.exists()
    assert 'Status changes' in report_path.read_text(encoding='utf-8')
    transitions_path = out_dir / 'brand_status_transitions.json'
    assert transitions_path.exists()
    transitions = json.loads(transitions_path.read_text(encoding='utf-8'))
    assert len(transitions) == 1
