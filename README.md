# rsincr.sh
RSync INCRemental backup: Simple, fast, incremental backups with rsync.

## Description
Wrapper around [rsync](https://rsync.samba.org/) to perform incremental backups with --link-dest. Each dated backup folder is a full backup and may be treated independently (deleted etc), but duplicate files from previous backup are hard-linked, so only use incremental disk space.

There are other (better?) solutions to the same problem - DIY guides, pre-existing wrappers around rsync, and dedicated backup tools. rsincr.sh provides a robust, efficient, simple and fast solution to my own needs, but I encourage you to evaluate and test other solutions in comparison to rsincr.sh to find what best fits your own requirements.

This was mostly written as a technical exercise - i.e. see how functional a shell/bash script I could write, combined with poor experience and NIH fear of other solutions. It may be rewritten in Python in future. I'm currently using it for 6-hourly backups from a home NAS to off-site, as well as a handful of other applications.

## Usage
```
./rsincr.py [-h] [-l {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                 [-c CONFIG_FILE]

optional arguments:
  -h, --help            show this help message and exit
  -l {DEBUG,INFO,WARNING,ERROR,CRITICAL}, --loglevel {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Logging/output verbosity
  -c CONFIG_FILE, --config-file CONFIG_FILE
                        Config file (default: rsincr.toml)
```

## Configuration
The [example config file](rsincr_example_config.toml) demonstrates most configuration options.

### \[global\]
* lockfile: Lockfile used to ensure only one instance is running (*String*) (**Default: '.rsincr.lock'**)

### \[destination\]
* server: Backup destination server in the form of 'hostname' or 'user@hostname' (*String*) (**No default**)

### \[backup\_jobs.\*\]
Backup jobs (i.e. source/destination pairings) to backup
* source\_dir: Source directory on local system (*String*) (**No default**)
* dest\_dir: Destination directory on backup server (*String*) (**No default**)
  * Note that files will be backed up to a separate timestamped subdirectory per backup

## Logical Operations
- A new dated backup folder is created
- Unchanged files are hard-linked to the existing copy from the last backup
- New or changed files are copied in as new files
- A 'latest' symlink is pointed at the completed backup folder
- Optionally, backups older than a configured number of days are purged
  - This is accomplished by rsync-ing an empty folder over the top, as this is faster on spinning media than a simple 'rm'

## Features
- Remote or local backup destination
- Performs basic tests prior to beginning backup, e.g.:
  - Remote host connectivity
  - Existence of source directory
  - Existence of destination directory on remote host
- Optionally purge backups older than X days
- (Somewhat) intelligently handles errors from rsync
- Pretty-ish output/logging
- Define configuration files for independent backup jobs - configuration options:
  - Lockfile
  - rsync options
  - Additional rsync options for interactive and non-interactive execution
  - Remote or local backup destination
  - Remote host, user
  - Source and (local|remote) destination path
  - When to perform a full backup
  - Age of backups to purge
- Different log formatting and additional rsync options for:
  1. Interactive (TTY) execution - e.g. give real-time feedback on progress
  2. Non-interactive (cron) execution - e.g. give a summary and don't spam the logs
- Perform a fresh full backup (write new files and don't hardlink to existing files, attempting to avoid bitrot):
  - Never
  - Every time
  - On certain days of the month
  - On certain days of the week

## Limitations
- File metadata (owner, in particular) may not be faithfully reproduced if the owner does not exist on the remote backup host
  - Backups using tar and other more complex tools are designed to perfectly-preserve file metadata
- By design, backups are not encrypted, de-duplicated, or compressed
  - The intention is for the backup to be a transparent, trivially-restorable copy of the data
  - Compression on the wire may be accomplished with appropriate rsync options (-z)
  - Compression on-disk may be accomplished at the filesystem or volume level if required. For backups of data that is already compressed (e.g. Photographs etc) this would not be necessary or desirable.
  - Encryption on-disk may be accomplished at the volume level
    - Be aware of the limitations here (e.g. data is accessible while the host is online and would be compromised in the event of malicious access to the remote host)
    - In future I may add a feature to mount/unmount an encrypted volume on the remote host using a passphrase or key saved on the source host, which would provide a partial solution to this problem

## Requirements
1. bash (version TBC) (makes moderate to heavy use of bashisms, won't execute with pure POSIX shells)
2. rsync (any version, but default config uses options only found in 3.1+)
3. The destination filesystem should allow hard linking

## Performance
TODO
