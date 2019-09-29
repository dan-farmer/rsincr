#!/usr/bin/env pytest-3
#
# Author: Dan Farmer
# SPDX-License-Identifier: GPL-3.0-only

"""Unit tests for rsincr."""

from freezegun import freeze_time
import rsincr

# Mock time to 2019-01-01 00:00:00 UTC (Tuesday)
@freeze_time('2019-01-01')
def test_get_backup_type():
    """Assert get_backup_type returns correct backup type when called with config combinations."""
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
