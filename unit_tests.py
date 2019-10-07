#!/usr/bin/env pytest-3
#
# Author: Dan Farmer
# SPDX-License-Identifier: GPL-3.0-only

"""Unit tests for rsincr."""

from unittest import mock
from freezegun import freeze_time
import rsincr

# Mock time to 2019-01-01 00:00:00 UTC (Tuesday)
@freeze_time('2019-01-01')
def test_get_backup_type():
    """Assert get_backup_type() returns correct backup type when called with config combinations."""
    assert rsincr.get_backup_type({}) == 'incremental'
    assert rsincr.get_backup_type({'schedule': {}}) == 'incremental'
    assert rsincr.get_backup_type({'schedule': {'full_backup_week_days': []}}) == 'incremental'
    assert rsincr.get_backup_type({'schedule': {'full_backup_month_days': []}}) == 'incremental'
    assert rsincr.get_backup_type({'schedule': {'full_backup_week_days': [1]}}) == 'incremental'
    assert rsincr.get_backup_type({'schedule': {'full_backup_week_days': [2]}}) == 'full'
    assert rsincr.get_backup_type({'schedule': {'full_backup_month_days': [1]}}) == 'full'
    assert rsincr.get_backup_type({'schedule': {'full_backup_month_days': [2]}}) == 'incremental'
    assert rsincr.get_backup_type({'schedule': {'full_backup_week_days': [1],
                                                'full_backup_month_days': [2]}}) == 'incremental'
    assert rsincr.get_backup_type({'schedule': {'full_backup_week_days': [2],
                                                'full_backup_month_days': [1]}}) == 'full'
    assert rsincr.get_backup_type({'schedule': {'full_backup_week_days': [1],
                                                'full_backup_month_days': [1]}}) == 'full'
    assert rsincr.get_backup_type({'schedule': {'full_backup_week_days': [2],
                                                'full_backup_month_days': [2]}}) == 'full'

def test_parse_args():
    """Assert parse_args() returns expected namespace when called with argument combinations."""

    empty_args = rsincr.parse_args(argv='')
    assert empty_args.loglevel is None
    assert empty_args.config_file.name == 'rsincr.toml'
    assert empty_args.force_full_backup is False

    set_args = rsincr.parse_args(argv=['-lDEBUG',
                                       '-crsincr_example_config.toml',
                                       '-fTrue'])
    assert set_args.loglevel == 'DEBUG'
    assert set_args.config_file.name == 'rsincr_example_config.toml'
    assert set_args.force_full_backup is True

def test_remove_lockfile():
    """Assert remove_lockfile calls os.remove on lockfile."""
    with mock.patch('rsincr.os.remove') as mocked_remove:
        rsincr.remove_lockfile('test_lockfile_name')
        mocked_remove.assert_called_with('test_lockfile_name')
