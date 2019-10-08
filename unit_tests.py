#!/usr/bin/env pytest-3
#
# Author: Dan Farmer
# SPDX-License-Identifier: GPL-3.0-only

"""Unit tests for rsincr."""

import os
import time
from unittest import mock
import pytest
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

# Mock time to 2019-01-01 00:00:00 UTC (Tuesday)
@freeze_time('2019-01-01')
def test_backup():
    """Assert backup() calls sysrsync.run and remote_link with expected options."""
    datetime = time.strftime("%Y%m%dT%H%M%S")
    test_backup_job = ('test_backup_job', {'source_dir': 'test_source_dir',
                                           'dest_dir': 'test_dest_dir',
                                           'compress': True})
    with mock.patch('rsincr.sysrsync.run') as mocked_sysrsync_run, \
            mock.patch('rsincr.remote_link') as mocked_remote_link:
        rsincr.backup('test_server', test_backup_job, 'full')
        mocked_sysrsync_run.assert_called_with(
            source='test_source_dir',
            destination_ssh='test_server',
            destination=os.path.join('test_dest_dir', datetime),
            options=['-a',
                     '--delete',
                     '--link-dest=' + os.path.join('..', 'latest'),
                     '--checksum',
                     '-z'])
        mocked_remote_link.assert_called_with(datetime, 'test_server', 'test_dest_dir')

# Mock time to 2019-01-01 00:00:00 UTC (Tuesday)
@freeze_time('2019-01-01')
def test_remote_link():
    """Assert remote_link() calls subprocess.run with expected options."""
    datetime = time.strftime("%Y%m%dT%H%M%S")
    with mock.patch('rsincr.subprocess.run') as mocked_subprocess_run:
        rsincr.remote_link(datetime, 'test_server', 'test_dest_dir')
        mocked_subprocess_run.assert_called_with([
            'ssh', 'test_server', 'ln', '-sfn', datetime, os.path.join('test_dest_dir', 'latest')])

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

def test_validate_config():
    """Assert validate_config() passes with valid config and calls sys.exit with invalid config."""
    config_minimal = {'global': {},
                      'destination': {'server': 'test_server'},
                      'backup_jobs': {'test_backup_job': {'source_dir': 'test_source_dir',
                                                          'dest_dir': 'test_dest_dir'}}}
    config_full = {'global': {'lockfile': 'test_lockfile'},
                   'destination': {'server': 'test_server'},
                   'schedule': {'full_backup_week_days': [0, 3],
                                'full_backup_month_days': [14, 28]},
                   'backup_jobs': {'test_backup_job': {'source_dir': 'test_source_dir',
                                                       'dest_dir': 'test_dest_dir',
                                                       'compress': True}}}
    config_missing_section = {'destination': {'server': 'test_server'},
                              'backup_jobs': {'test_backup_job': {'source_dir': 'test_source_dir',
                                                                  'dest_dir': 'test_dest_dir'}}}
    config_missing_item = {'global': {},
                           'destination': {},
                           'backup_jobs': {'test_backup_job': {'source_dir': 'test_source_dir',
                                                               'dest_dir': 'test_dest_dir'}}}

    assert rsincr.validate_config(config_minimal) is None
    assert rsincr.validate_config(config_full) is None

    with pytest.raises(SystemExit) as pytest_wrapped_e_missing_section:
        rsincr.validate_config(config_missing_section)
    assert pytest_wrapped_e_missing_section.type == SystemExit
    assert pytest_wrapped_e_missing_section.value.code == "Missing key: 'global'"

    with pytest.raises(SystemExit) as pytest_wrapped_e_missing_item:
        rsincr.validate_config(config_missing_item)
    assert pytest_wrapped_e_missing_item.type == SystemExit
    assert pytest_wrapped_e_missing_item.value.code == \
        "Key 'destination' error:\nMissing key: 'server'"

def test_remove_lockfile():
    """Assert remove_lockfile calls os.remove on lockfile."""
    with mock.patch('rsincr.os.remove') as mocked_remove:
        rsincr.remove_lockfile('test_lockfile_name')
        mocked_remove.assert_called_with('test_lockfile_name')
