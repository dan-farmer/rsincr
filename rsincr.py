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
import tempfile
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
        backup(server,
               config['rsync'].get('bwlimit', False),
               config['rsync'].get('additional_rsync_opts', False),
               config['backup_jobs'][backup_job_name],
               backup_type)
        if config['schedule'].get('retention_days', False):
            logging.info('Purging backups older than %s days for backup job %s',
                         config['schedule']['retention_days'], backup_job_name)
            purge(server,
                  config['rsync'].get('additional_rsync_opts', False),
                  config['backup_jobs'][backup_job_name],
                  config['schedule']['retention_days'])

def get_backup_type(config):
    """Return the backup type that should be run ('incremental' or 'full')."""

    if int(time.strftime('%w')) in config['schedule'].get('full_backup_week_days', []) or \
            int(time.strftime('%d')) in config['schedule'].get('full_backup_month_days', []):
        logging.info('Performing full backup')
        return 'full'

    logging.info('Performing incremental backup')
    return 'incremental'

def backup(server, bwlimit, additional_rsync_opts, backup_job, backup_type='incremental'):
    """Execute rsync for backup_job.

    Raises RsyncError if rsync exits non-zero
    """
    datetime = time.strftime("%Y%m%dT%H%M%S")
    source_dir, dest_dir = backup_job['source_dir'], backup_job['dest_dir']

    remote_mkdir(server, dest_dir)

    logging.info('Starting rsync of %s to %s:%s',
                 source_dir, server, os.path.join(dest_dir, datetime))

    rsync_options = ['-a',
                     '--delete',
                     '--link-dest=' + os.path.join('..', 'latest')]
    if bwlimit:
        rsync_options.append(f'--bwlimit={bwlimit}')
    if additional_rsync_opts:
        for rsync_opt in additional_rsync_opts:
            rsync_options.append(rsync_opt)
    if backup_type == 'full':
        rsync_options.append('--checksum')
    if backup_job.get('compress'):
        rsync_options.append('-z')
    if backup_job.get('exclude'):
        for exclusion in backup_job['exclude']:
            rsync_options.append(f'--exclude={exclusion}')

    sysrsync.run(source=os.path.expanduser(source_dir),
                 destination_ssh=server,
                 destination=os.path.join(dest_dir, datetime),
                 options=rsync_options)

    logging.info('Updating mtime of %s:%s', server, os.path.join(dest_dir, datetime))
    logging.debug('Executing \'ssh %s touch %s\'', server, os.path.join(dest_dir, datetime))
    subprocess.run(["ssh", server, "touch", os.path.join(dest_dir, datetime)], check=True)

    remote_link(datetime, server, dest_dir)

def remote_mkdir(server, dest_dir):
    """Create directory on server if it does not exist."""
    exists_check = subprocess.run(["ssh", server, "[[", "-d", dest_dir, "]]"], check=False)
    if not exists_check.returncode == 0:
        logging.warning('Destination directory \'%s\' does not exist on server \'%s\'; Creating it',
                        dest_dir, server)
        subprocess.run(["ssh", server, "mkdir", "-p", dest_dir], check=True)

def purge(server, additional_rsync_opts, backup_job, retention_days):
    """Purge any backup subdirectories in server:dest_dir that are older than retention_days."""
    dest_dir = backup_job['dest_dir']

    expired_backups = get_expired_backups(server, dest_dir, retention_days)

    if not expired_backups:
        logging.info('No expired backups found in destination directory %s on server %s',
                     dest_dir, server)
        return

    rsync_options = ['-r', '--delete']
    if additional_rsync_opts:
        for rsync_opt in additional_rsync_opts:
            rsync_options.append(rsync_opt)

    for expired_backup in expired_backups:
        logging.info('Purging expired backup %s on server %s', expired_backup, server)
        with tempfile.TemporaryDirectory() as tmp_empty_dir:
            sysrsync.run(source=tmp_empty_dir,
                         destination_ssh=server,
                         destination=expired_backup,
                         options=rsync_options)
        subprocess.run(['ssh', server, 'rmdir', expired_backup], check=True)

def get_expired_backups(server, dest_dir, retention_days):
    """Return subdirectories of server:dest_dir that are (retention_days + 1) old, or older."""
    find_process = subprocess.run(['ssh', server,
                                   'find', '-H', dest_dir,
                                   '-mindepth', '1', '-maxdepth', '1', '-type', 'd',
                                   '-mtime', f'+{retention_days}'],
                                  capture_output=True, check=True)

    if find_process.stdout in [None, b'']:
        return False

    # find_process.stdout is a byte-string of line-separated directory names
    # Return this as a list of utf8-converted strings
    return list(map(lambda x: str(x, 'utf-8'), find_process.stdout.splitlines()))

def remote_link(datetime, server, dest_dir):
    """Symlink 'latest' to a datetime-stamped backup directory.

    Raises CalledProcessError on failure
    """
    logging.info('Symlinking \'latest\' to \'%s\'', datetime)
    subprocess.run(["ssh", server, "ln", "-sfn", datetime, os.path.join(dest_dir, 'latest')],
                   check=True)

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
        'rsync': {
            Optional('bwlimit'): str,
            Optional('additional_rsync_opts'): Or([str], [])
        },
        'destination': {
            'server': str
        },
        'schedule': {
            Optional('full_backup_week_days'): Or([int], []),
            Optional('full_backup_month_days'): Or([int], []),
            Optional('retention_days'): int
        },
        'backup_jobs': {
            str: {
                'source_dir': str,
                'dest_dir': str,
                Optional('compress'): bool,
                Optional('exclude'): Or([str], [])
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
