# rsincr
RSync INCRemental backup: Simple, fast, incremental backups with rsync.

## Description
Wrapper around [rsync](https://rsync.samba.org/) to perform incremental backups by hard-linking unchanged files on the filesystem (a.k.a. `rsync --link-dest`). Each dated backup directory is a full backup and may be treated independently (deleted etc), but duplicate files from previous backup are hard-linked on the filesystem, so only use incremental disk space.

### Advantages
1. Backed up directories and files are accessible on the destination server filesystem (no special tools needed to examine, list, or partially/fully-restore a backup)
1. After the initial backup, unchanged files never need to be transferred or stored again, even for a 'full' backup
   * A 'full' backup simply forces rsync to read the full file contents on both filesystems (source and destination) and compare them by checksum. If the file is unchanged on the destination filesystem, a new hard-link is made to it in the dated backup. If the file is changed or new, it will be created as a new file.
   * This makes rsincr extremely well-suited to situations where full transfers or stores of the backup data are costly or time-consuming, e.g. Large backup sets at sites with limited upload bandwidth

### Disadvantages
1. By design, backups are not encrypted, de-duplicated, compressed, or signed/sealed
   * Compression on-disk may be accomplished at the filesystem or volume level if required
   * Encryption on-disk may be accomplished at the volume level
     * Be aware that data is accessible while the backup filesystem is mounted and would be compromised in the event of malicious access to the destination server
     * Potential future enhancement: Mount/unmount an encrypted volume on the destination server using a passphrase or key saved on the source host config
1. File metadata (owner, in particular) may not be faithfully reproduced if the owner does not exist on the remote backup host

## Requirements
* Local system (backup source):
  * Python 3.6+
  * Python modules from [requirements.txt](requirements.txt)
  * rsync (any version in recent history, but 3.0+ (2008) recommended)
* Backup destination server:
  * rsync (any version in recent history, but 3.0+ (2008) recommended)
  * GNU `find`
  * Filesystem must support hard links

## Usage

### Installation
```
git clone https://github.com/reedbug/rsincr.git   # Or git@github.com:reedbug/rsincr.git
cd rsincr/
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Scheduling
* The [example config file](rsincr_example_config.toml) demonstrates most configuration options, or see [configuration reference](#configuration-reference) below. Minimum configuration items needed to perform a backup:
  * Server
  * At least one backup job, with:
    * Source path
    * Destination path
* Once a configuration file has been setup, `rsincr.py` is suitable for execution from a cron job / systemd timer, e.g. on a weekly/nightly/6-hourly basis, etc:
  ```
  source venv/bin/activate && ./rsincr.py
  ```
* Failures or other errors will be output as normal and the process will exit with a failure, so it is advisable to configure the cron job / system to email failure outputs to a real person

### Command Line Arguments
```
./rsincr.py [-h] [-l {DEBUG,INFO,WARNING,ERROR,CRITICAL}]
                 [-c CONFIG_FILE] [-f FORCE_FULL_BACKUP]

optional arguments:
  -h, --help            show this help message and exit
  -l {DEBUG,INFO,WARNING,ERROR,CRITICAL}, --loglevel {DEBUG,INFO,WARNING,ERROR,CRITICAL}
                        Logging/output verbosity
  -c CONFIG_FILE, --config-file CONFIG_FILE
                        Config file (default: rsincr.toml)
  -f FORCE_FULL_BACKUP, --force-full-backup FORCE_FULL_BACKUP
                        Force a 'full' backup (compare checksums of files on
                        both sides), regardless of schedule
```

### Configuration Reference

#### \[global\]
| Config key | Type | Required | Default | Description |
| ---------- | ---- | -------- | ------- | ----------- |
| lockfile | String | No | `.rsincr.lock` | Lockfile used to ensure only one instance is running |

#### \[rsync\]
| Config key | Type | Required | Default | Description |
| ---------- | ---- | -------- | ------- | ----------- |
| bwlimit | String | No | None | Bandwidth limit for rsync; Any string that is interpretable by rsync - see `man 1 rsync` |
| additional\_rsync\_opts | List of string | No | None | Arbitrary additional options to pass to rsync - see `man 1 rsync` |

#### \[destination\]
| Config key | Type | Required | Default | Description |
| ---------- | ---- | -------- | ------- | ----------- |
| server | String | **Yes** | None | Backup destination server in the form of 'hostname' or 'user@hostname' |

#### \[schedule\]
| Config key | Type | Required | Default | Description |
| ---------- | ---- | -------- | ------- | ----------- |
| full\_backup\_week\_days | List of integer | No | None | List of week days (0=Sunday) on which to perform a 'full' backup |
| full\_backup\_month\_days | List of integer | No | None | List of days of the month on which to perform a 'full' backup |
| retention\_days | Integer | No | None | Retain backups up to this number of days, and purge older backups |

#### \[backup\_jobs.\*\]
Backup jobs (i.e. source/destination pairings) to backup. At least one backup job must exist.

| Config key | Type | Required | Default | Description |
| ---------- | ---- | -------- | ------- | ----------- |
| source\_dir | String | **Yes** | None | Source directory on local host |
| dest\_dir | String | **Yes** | None | Destination directory on backup server (*Note that files will be backed up to a separate timestamped subdirectory per backup*) |
| compress | Boolean | No | false | Compress files in transfer (`rsync -z`) |
| exclude | List of string | No | None | Files or path patterns to exclude - see `man 1 rsync` for pattern rules |

## Legacy Shell Version
A legacy version of rsincr written in shell (bash) can be found in [legacy\_shell/](legacy_shell/). It is unmaintained, and should not be used unless the python version cannot be used (e.g. due to dependencies).
