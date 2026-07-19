import sys
from unittest.mock import patch, MagicMock
import pytest
from dkkd.cli import main

@patch('dkkd.cli.cmd_audit_tax')
def test_cli_audit_tax_registration(mock_cmd):
    with patch.object(sys, 'argv', ['dkkd.py', 'audit-tax', '--brand', 'gs25']):
        main()
        mock_cmd.assert_called_once()
