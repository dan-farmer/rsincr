#!/usr/bin/env python3
#
# Author: Dan Farmer
# SPDX-License-Identifier: GPL-3.0-only

"""Wrapper around rsync to perform filesystem-level differential backups using hardlinks."""

import argparse
import logging
import sys
import fcntl
import atexit
import os
import time
import subprocess
import toml
from schema import Schema, SchemaError, Optional, Or
import sysrsync

def main():
    """Execute rsync using parsed arguments and config."""

    args = parse_args()
    logging.info('Execution starting using config file %s', args.config_file.name)
    config = toml.load(args.config_file)
    validate_config(config)

    server = config['destination']['server']
    if args.force_full_backup:
        backup_type = 'full'
    else:
        backup_type = get_backup_type(config)
    #TODO: Config for global rsync options

    # Lock the lockfile before we start backups to ensure we have only one instance running
    lockfile = config['global'].get('lockfile', '.rsincr.lock')
    lockfile_handle = open(lockfile, 'w')
    try:
        fcntl.lockf(lockfile_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exception:
        logging.error('Could not lock lockfile %s. Another instance may already be running.',
                      lockfile)
        raise exception
    # Register a cleanup function to remove lockfile when we exit
    atexit.register(remove_lockfile, lockfile)

    for backup_job_name in config['backup_jobs']:
        logging.info('Starting backup job %s', backup_job_name)
        backup(server, config['backup_jobs'][backup_job_name], backup_type)

    #TODO: Purging

def get_backup_type(config):
    """Return the backup type that should be run ('incremental' or 'full')."""

    try:
        schedule = config['schedule']
    except KeyError:
        logging.warning('No schedule config section defined; Defaulting to incremental backup')
        return 'incremental'

    if int(time.strftime('%w')) in schedule.get('full_backup_week_days', []) or \
            int(time.strftime('%d')) in schedule.get('full_backup_month_days', []):
        logging.info('Performing full backup')
        return 'full'

    logging.info('Performing incremental backup')
    return 'incremental'

def backup(server, backup_job, backup_type='incremental'):
    """Execute rsync for backup_job.

    Raises RsyncError if rsync exits non-zero
    """
    datetime = time.strftime("%Y%m%dT%H%M%S")
    source_dir, dest_dir = backup_job['source_dir'], backup_job['dest_dir']
    #TODO: Config for exclusions

    #TODO: Create destination directory if it doesn't exist?

    logging.info('Starting rsync of %s to %s:%s',
                 source_dir, server, os.path.join(dest_dir, datetime))

    rsync_options = ['-a',
                     '--delete',
                     '--link-dest=' + os.path.join('..', 'latest')]
    if backup_type == 'full':
        rsync_options.append('--checksum')
    if backup_job.get('compress'):
        rsync_options.append('-z')

    sysrsync.run(source=os.path.expanduser(source_dir),
                 destination_ssh=server,
                 destination=os.path.join(dest_dir, datetime),
                 options=rsync_options)

    remote_link(datetime, server, dest_dir)

def remote_link(datetime, server, dest_dir):
    """Symlink 'latest' to a datetime-stamped backup directory.

    Raises CalledProcessError on failure
    """
    logging.info('Symlinking \'latest\' to \'%s\'', datetime)
    symlink_process = subprocess.run(["ssh", server, "ln", "-sfn",
                                      datetime, os.path.join(dest_dir, 'latest')])
    symlink_process.check_returncode()

def parse_args(argv=None):
    """Create arguments and populate variables from args.

    Return args namespace
    """
    parser = argparse.ArgumentParser()

    parser.add_argument('-l', '--loglevel', type=str,
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Logging/output verbosity')
    parser.add_argument('-c', '--config-file', type=argparse.FileType('r'), default='rsincr.toml',
                        help='Config file (default: rsincr.toml)')
    parser.add_argument('-f', '--force-full-backup', type=bool, default=False,
                        help='Force a \'full\' backup (compare checksums of files on both sides), '\
                             'regardless of schedule')

    args = parser.parse_args(argv)

    if args.loglevel:
        logging.basicConfig(level=args.loglevel)

    return args

def validate_config(config):
    """Validate config against schema.

    Raise exception if config does not validate
    """
    config_schema = Schema({
        'global': {
            Optional('lockfile'): str
        },
        'destination': {
            'server': str
        },
        Optional('schedule'): {
            Optional('full_backup_week_days'): Or([int], []),
            Optional('full_backup_month_days'): Or([int], [])
        },
        'backup_jobs': {
            str: {
                'source_dir': str,
                'dest_dir': str,
                Optional('compress'): bool
            }
        }
    })

    try:
        config_schema.validate(config)
    except SchemaError as exception:
        sys.exit(exception.code)

def remove_lockfile(lockfile):
    """Cleanup function to remove lockfile when we exit."""
    os.remove(lockfile)

if __name__ == '__main__':
    main()
