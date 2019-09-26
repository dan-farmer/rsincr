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
from schema import Schema, SchemaError, Optional
import sysrsync

def main():
    """Execute rsync using parsed arguments and config."""

    args = parse_args()
    logging.info('Execution starting using config file %s', args.config_file.name)
    config = toml.load(args.config_file)
    validate_config(config)

    server = config['destination']['server']

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

    for backup_job in config['backup_jobs'].items():
        backup(server, backup_job)

def backup(server, backup_job):
    """Execute rsync for backup_job."""
    logging.info('Starting backup job %s', backup_job[0])
    datetime = time.strftime("%Y%m%dT%H%M%S")
    source_dir, dest_dir = backup_job[1]['source_dir'], backup_job[1]['dest_dir']

    #TODO: Create destination directory if it doesn't exist?

    logging.info('Starting rsync of %s to %s:%s',
                 source_dir, server, os.path.join(dest_dir, datetime))
    sysrsync.run(source=os.path.expanduser(source_dir),
                 destination_ssh=server,
                 destination=os.path.join(dest_dir, datetime),
                 options=['-a',
                          '--delete',
                          '--link-dest=' + os.path.join('..', 'latest')])

    logging.info('Symlinking \'latest\' to \'%s\'', datetime)
    symlink_process = subprocess.run(["ssh", server, "ln", "-sfn",
                                      datetime, os.path.join(dest_dir, 'latest')])
    symlink_process.check_returncode()

def parse_args():
    """Create arguments and populate variables from args.

    Return args namespace
    """
    parser = argparse.ArgumentParser()

    parser.add_argument('-l', '--loglevel', type=str,
                        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
                        help='Logging/output verbosity')
    parser.add_argument('-c', '--config-file', type=argparse.FileType('r'), default='rsincr.toml',
                        help='Config file (default: rsincr.toml)')

    args = parser.parse_args()

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
        'backup_jobs': {
            str: {
                'source_dir': str,
                'dest_dir': str
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
