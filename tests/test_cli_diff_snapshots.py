"""Tests for the `dkkd diff-snapshots` CLI subcommand."""
import pytest

from dkkd.cli import main


def test_diff_snapshots_since_is_required(monkeypatch):
    called = []
    monkeypatch.setattr('dkkd.cli.cmd_diff_snapshots', lambda args: called.append(args))
    with pytest.raises(SystemExit):
        main(['diff-snapshots', '--brand', 'circle-k'])
    assert called == []


def test_diff_snapshots_dispatches_with_brand_and_since(monkeypatch):
    called = []
    monkeypatch.setattr('dkkd.cli.cmd_diff_snapshots', lambda args: called.append(args))
    main(['diff-snapshots', '--brand', 'circle-k', '--since', 'eda4e7a'])
    assert len(called) == 1
    assert called[0].brand == 'circle-k'
    assert called[0].since == 'eda4e7a'


def test_cmd_diff_snapshots_calls_run_diff_and_prints_summary(monkeypatch, capsys):
    from dkkd import cli as cli_module

    def fake_run_diff(brand, since):
        assert brand == 'circle-k'
        assert since == 'eda4e7a'
        return {
            'new_ids': {'genuinely_new': ['1'], 'newly_discovered': []},
            'vanished_ids': [],
            'relocations': {},
            'status_changes': {'2': {'old_status': 'Operating', 'new_status': 'Closed',
                                       'bracket': ['2026-06-01', '2026-07-01']}},
            'renamed': {},
        }

    monkeypatch.setattr('dkkd.snapshot_diff.run_diff', fake_run_diff)
    args = argparse_namespace(brand='circle-k', since='eda4e7a')
    cli_module.cmd_diff_snapshots(args)
    captured = capsys.readouterr()
    assert 'new=1' in captured.out
    assert 'status_changed=1' in captured.out


def argparse_namespace(**kwargs):
    import argparse
    return argparse.Namespace(**kwargs)
