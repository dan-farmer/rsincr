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
    logging.debug('Configuration dump: %s', config)
    validate_config(config)

    server = config['destination']['server']
    if args.force_full_backup:
        logging.debug('Full backup forced by command line argument')
        print('Backup type: Full - forcing rsync to read full files on source and dest and '
              'compare checksums')
        backup_type = 'full'
    else:
        backup_type = get_backup_type(config)

    lockfile = config['global'].get('lockfile', '.rsincr.lock')
    logging.debug('Attempting to lock lockfile %s to ensure we have only one instance running',
                  lockfile)
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
        print(f'Starting backup job {backup_job_name}')
        backup(server,
               config['rsync'].get('bwlimit', False),
               config['rsync'].get('additional_rsync_opts', False),
               config['backup_jobs'][backup_job_name],
               backup_type)
        if config['schedule'].get('retention_days', False):
            print(f'Purging backups older than {config["schedule"]["retention_days"]} days for '
                  f'backup job {backup_job_name}')
            purge(server,
                  config['rsync'].get('additional_rsync_opts', False),
                  config['backup_jobs'][backup_job_name],
                  config['schedule']['retention_days'])

def get_backup_type(config):
    """Return the backup type that should be run ('incremental' or 'full')."""

    if int(time.strftime('%w')) in config['schedule'].get('full_backup_week_days', []) or \
            int(time.strftime('%d')) in config['schedule'].get('full_backup_month_days', []):
        print('Backup type: Full - forcing rsync to read full files on source and dest and compare '
              'checksums')
        return 'full'

    print('Backup type: Incremental')
    return 'incremental'

def backup(server, bwlimit, additional_rsync_opts, backup_job, backup_type='incremental'):
    """Execute rsync for backup_job.

    Raises RsyncError if rsync exits non-zero
    """
    datetime = time.strftime("%Y%m%dT%H%M%S")
    logging.debug('Datetime: %s', datetime)
    source_dir, dest_dir = backup_job['source_dir'], backup_job['dest_dir']
    logging.debug('Source: %s', source_dir)
    logging.debug('Destination: %s:%s', server, dest_dir)

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

    logging.debug('Executing \'rsync %s %s %s:%s\'',
                  ' '.join(rsync_options), os.path.expanduser(source_dir),
                  server, os.path.join(dest_dir, datetime))
    sysrsync.run(source=os.path.expanduser(source_dir),
                 destination_ssh=server,
                 destination=os.path.join(dest_dir, datetime),
                 options=rsync_options)

    logging.info('Updating mtime of %s:%s', server, os.path.join(dest_dir, datetime))
    logging.debug('Executing \'ssh %s touch "%s"\'', server, os.path.join(dest_dir, datetime))
    subprocess.run(["ssh", server, "touch", os.path.join(dest_dir, datetime)], check=True)

    remote_link(datetime, server, dest_dir)

def remote_mkdir(server, dest_dir):
    """Create directory on server if it does not exist."""
    logging.info('Checking if destination directory \'%s\' exists on server \'%s\'',
                 server, dest_dir)
    logging.debug('Executing \'ssh %s [[ -d "%s" ]]\'', server, dest_dir)
    exists_check = subprocess.run(["ssh", server, "[[", "-d", dest_dir, "]]"], check=False,
                                  capture_output=True)
    if not exists_check.returncode == 0:
        if exists_check.stdout or exists_check.stderr:
            # Bash '[[ -d ]]' test should output nothing even if the directory does not exist.
            # If we have output, something went wrong (e.g. we couldn't SSH to server).
            logging.error(
                'Unexpected output checking for existence of directory \'%s\' on server \'%s\'',
                dest_dir, server)
            logging.error('stdout: %s', str(exists_check.stdout, 'utf-8'))
            logging.error('stderr: %s', str(exists_check.stderr, 'utf-8'))
            raise Exception('Unexpected output checking for existence of remote directory')
        logging.warning('Destination directory \'%s\' does not exist on server \'%s\'; Creating it',
                        dest_dir, server)
        logging.debug('Executing \'ssh %s mkdir -p "%s"\'', server, dest_dir)
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
        print(f'Purging expired backup {expired_backup} on server {server}')
        with tempfile.TemporaryDirectory() as tmp_empty_dir:
            logging.debug('Executing \'rsync %s %s %s:%s\'',
                          ' '.join(rsync_options), tmp_empty_dir, server, expired_backup)
            sysrsync.run(source=tmp_empty_dir,
                         destination_ssh=server,
                         destination=expired_backup,
                         options=rsync_options)
        logging.debug('Executing \'ssh %s rmdir "%s"\'', server, expired_backup)
        subprocess.run(['ssh', server, 'rmdir', expired_backup], check=True)

def get_expired_backups(server, dest_dir, retention_days):
    """Return subdirectories of server:dest_dir that are (retention_days + 1) old, or older."""
    logging.debug('Executing \'ssh %s find -H "%s" -mindepth +%s\'',
                  server, dest_dir, retention_days)
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
    logging.debug('Executing \'ssh %s ln -sfn %s %s\'',
                  server, datetime, os.path.join(dest_dir, 'latest'))
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
        logging.error('Could not validate config')
        sys.exit(exception.code)

def remove_lockfile(lockfile):
    """Cleanup function to remove lockfile when we exit."""
    logging.debug('Cleaning up (removing) lockfile %s', lockfile)
    os.remove(lockfile)

if __name__ == '__main__':
    main()
