#!/usr/bin/env python3
#
# Author: Dan Farmer
# SPDX-License-Identifier: GPL-3.0-only

"""Wrapper around rsync to perform filesystem-level differential backups using hardlinks."""

import argparse
import logging
import toml

def main():
    """Execute rsync using parsed arguments and config."""

    args = parse_args()
    logging.info('Execution starting using config file %s', args.config_file.name)
    config = toml.load(args.config_file)

    server = config['destination']['server']

    for backup_job in config['backup_jobs'].items():
        backup(server, backup_job)

def backup(server, backup_job):
    """Execute rsync for backup_job."""
    logging.info('Starting backup job %s', backup_job[0])
    pass

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

if __name__ == '__main__':
    main()
