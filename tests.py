#!/usr/bin/env pytest-3
#
# Author: Dan Farmer
# SPDX-License-Identifier: GPL-3.0-only

"""Tests for rsincr."""

import os
import time
import copy
from unittest import mock
from argparse import Namespace
import pytest
from freezegun import freeze_time
import rsincr

TEST_CONFIG = {'global': {'lockfile': 'lockfile01'},
               'destination': {'server': 'server01'},
               'schedule': {'full_backup_week_days': [0, 3],
                            'full_backup_month_days': [14, 28]},
               'backup_jobs': {'job01': {'source_dir': 'source01',
                                         'dest_dir': 'dest01',
                                         'compress': True,
                                         'exclude': ['exclusion01']}}}

# Mock time to 2019-01-01 00:00:00 UTC (Tuesday)
@freeze_time('2019-01-01')
def test_main():
    """Assert main() calls backup() with expected arguments, given command line args and config."""
    with mock.patch('rsincr.parse_args') as mocked_parse_args, \
         mock.patch('rsincr.toml.load') as mocked_toml_load, \
         mock.patch('builtins.open'), \
         mock.patch('rsincr.fcntl.lockf') as mocked_fcntl_lockf, \
         pytest.raises(OSError) as pytest_wrapped_e_oserror, \
         mock.patch('rsincr.atexit.register'), \
         mock.patch('rsincr.backup') as mocked_backup:

        mocked_parse_args.return_value = Namespace(
            config_file=mock.Mock(name='test_config_file'), force_full_backup=False, loglevel=None)
        mocked_toml_load.return_value = TEST_CONFIG
        rsincr.main()
        mocked_backup.assert_called_with(TEST_CONFIG['destination']['server'],
                                         TEST_CONFIG['backup_jobs']['job01'],
                                         'incremental')

        mocked_parse_args.return_value = Namespace(
            config_file=mock.Mock(name='test_config_file'), force_full_backup=True, loglevel=None)
        rsincr.main()
        mocked_backup.assert_called_with(TEST_CONFIG['destination']['server'],
                                         TEST_CONFIG['backup_jobs']['job01'],
                                         'full')

        mocked_fcntl_lockf.side_effect = OSError
        rsincr.main()
        assert pytest_wrapped_e_oserror.type == OSError

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
    with mock.patch('rsincr.sysrsync.run') as mocked_sysrsync_run, \
         mock.patch('rsincr.remote_mkdir') as mocked_remote_mkdir, \
         mock.patch('rsincr.remote_link') as mocked_remote_link:
        rsincr.backup(TEST_CONFIG['destination']['server'],
                      TEST_CONFIG['backup_jobs']['job01'],
                      'full')
    exclusion = next(iter(TEST_CONFIG["backup_jobs"]["job01"]["exclude"]))
    mocked_sysrsync_run.assert_called_with(
        source=TEST_CONFIG['backup_jobs']['job01']['source_dir'],
        destination_ssh=TEST_CONFIG['destination']['server'],
        destination=os.path.join(TEST_CONFIG['backup_jobs']['job01']['dest_dir'], datetime),
        options=['-a',
                 '--delete',
                 '--link-dest=' + os.path.join('..', 'latest'),
                 '--checksum',
                 '-z',
                 f'--exclude={exclusion}'])
    mocked_remote_mkdir.assert_called_with(TEST_CONFIG['destination']['server'],
                                           TEST_CONFIG['backup_jobs']['job01']['dest_dir'])
    mocked_remote_link.assert_called_with(datetime,
                                          TEST_CONFIG['destination']['server'],
                                          TEST_CONFIG['backup_jobs']['job01']['dest_dir'])

def test_remote_mkdir():
    """Assert remote_mkdir() calls subprocess.run for checks and directory creation."""
    with mock.patch('rsincr.subprocess.run') as mocked_subprocess_run:

        # If directory check succeeds, subprocess.run should only be called once
        mocked_subprocess_run.return_value.returncode = 0
        rsincr.remote_mkdir(TEST_CONFIG['destination']['server'],
                            TEST_CONFIG['backup_jobs']['job01']['dest_dir'])
        mocked_subprocess_run.assert_called_once_with(
            ['ssh', TEST_CONFIG['destination']['server'],
             '[[', '-d', TEST_CONFIG['backup_jobs']['job01']['dest_dir'], ']]'],
            check=False)

        # If directory check fails, subprocess.run will be called a second time to mkdir
        mocked_subprocess_run.return_value.returncode = [1, 0]
        rsincr.remote_mkdir(TEST_CONFIG['destination']['server'],
                            TEST_CONFIG['backup_jobs']['job01']['dest_dir'])
        mocked_subprocess_run.assert_called_with(
            ['ssh', TEST_CONFIG['destination']['server'],
             'mkdir', '-p', TEST_CONFIG['backup_jobs']['job01']['dest_dir']],
            check=True)

# Mock time to 2019-01-01 00:00:00 UTC (Tuesday)
@freeze_time('2019-01-01')
def test_remote_link():
    """Assert remote_link() calls subprocess.run with expected options."""
    datetime = time.strftime("%Y%m%dT%H%M%S")
    with mock.patch('rsincr.subprocess.run') as mocked_subprocess_run:
        rsincr.remote_link(datetime,
                           TEST_CONFIG['destination']['server'],
                           TEST_CONFIG['backup_jobs']['job01']['dest_dir'])
    mocked_subprocess_run.assert_called_with(
        ['ssh', TEST_CONFIG['destination']['server'],
         'ln', '-sfn',
         datetime, os.path.join(TEST_CONFIG['backup_jobs']['job01']['dest_dir'], 'latest')],
        check=True)

def test_parse_args():
    """Assert parse_args() returns expected namespace when called with argument combinations."""
    with mock.patch('builtins.open') as mocked_open:

        type(mocked_open.return_value).name = mock.PropertyMock(return_value='rsincr.toml')
        empty_args = rsincr.parse_args(argv='')
        assert empty_args.loglevel is None
        assert empty_args.config_file.name == 'rsincr.toml'
        assert empty_args.force_full_backup is False

        type(mocked_open.return_value).name = mock.PropertyMock(return_value='config01.toml')
        set_args = rsincr.parse_args(argv=['-lDEBUG', '-cconfig01.toml', '-fTrue'])
        assert set_args.loglevel == 'DEBUG'
        assert empty_args.config_file.name == 'config01.toml'
        assert set_args.force_full_backup is True

def test_validate_config():
    """Assert validate_config() passes with valid config and calls sys.exit with invalid config."""
    assert rsincr.validate_config(TEST_CONFIG) is None

    config_minimal = copy.deepcopy(TEST_CONFIG)
    del config_minimal['global']['lockfile']
    del config_minimal['schedule']
    del config_minimal['backup_jobs']['job01']['compress']
    assert rsincr.validate_config(config_minimal) is None

    config_missing_section = copy.deepcopy(TEST_CONFIG)
    del config_missing_section['global']
    with pytest.raises(SystemExit) as pytest_wrapped_e_missing_section:
        rsincr.validate_config(config_missing_section)
    assert pytest_wrapped_e_missing_section.type == SystemExit
    assert pytest_wrapped_e_missing_section.value.code == "Missing key: 'global'"

    config_missing_item = copy.deepcopy(TEST_CONFIG)
    del config_missing_item['destination']['server']
    with pytest.raises(SystemExit) as pytest_wrapped_e_missing_item:
        rsincr.validate_config(config_missing_item)
    assert pytest_wrapped_e_missing_item.type == SystemExit
    assert pytest_wrapped_e_missing_item.value.code == \
        "Key 'destination' error:\nMissing key: 'server'"

def test_remove_lockfile():
    """Assert remove_lockfile calls os.remove on lockfile."""
    with mock.patch('rsincr.os.remove') as mocked_remove:
        rsincr.remove_lockfile('lockfile01')
    mocked_remove.assert_called_with('lockfile01')
