#!/usr/bin/env python3
#
# Author: Dan Farmer
# SPDX-License-Identifier: GPL-3.0-only

"""Wrapper around rsync to perform filesystem-level differential backups using hardlinks."""

import argparse
import logging
import sys
import toml
from schema import Schema, SchemaError

def main():
    """Execute rsync using parsed arguments and config."""

    args = parse_args()
    logging.info('Execution starting using config file %s', args.config_file.name)
    config = toml.load(args.config_file)
    validate_config(config)

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

def validate_config(config):
    """Validate config against schema.

    Raise exception if config does not validate
    """
    config_schema = Schema({
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

if __name__ == '__main__':
    main()
