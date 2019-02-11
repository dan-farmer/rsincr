#!/bin/bash
#
# rsincr.sh
# (RSync INCRemental backup)
#
# Wrapper around rsync (https://rsync.samba.org/) to perform incremental backups
# with --link-dest. Each backup is a full backup and may be treated
# independently (deleted etc), but duplicate files from previous backup are
# hard-linked, so only use incremental disk space.
#
# Author: Dan Farmer
# URL: https://github.com/reedbug/rsincr.sh/
# Version: 0.6.2
# Licence: GPLv3+
#
# Copyright (C) 2016 Dan Farmer
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see https://www.gnu.org/licenses/.
#
#
# TODO: Coding style, e.g. https://google.github.io/styleguide/shell.xml
# TODO: Comments, comments, comments!

function main {
  handle_args "$@"       # Handle arguments, print help, exit if invalid
  set_times              # Establish datetime, set related variables
  log INFO "$0 starting at $DATE_PRETTY"
  load_config            # Find and source config file for this backup job
  validate_config        # Validate the imported config
  lock                   # Lock on lockfile specific to this backup job
  if [[ $? -ne 0 ]]; then
    log ERR "Couldn't acquire lock on $LOCKFILE"; finish 3
  fi
  checks                 # Basic checks on source, dest path, remote host
  determine_backup_type  # Full or incremental backup?
  backup                 # Run backup with rsync
  link_latest            # Point 'latest' symlink at backup we just completed
  purge                  # Purge backups older than set number of days
  finish 0               # Log end of run and exit with success
}

function handle_args {
  # Handle command arguments
  if ([[ $1 == "--help" ]] || [[ $1 == "-h" ]]); then
    printhelp
  elif [[ $1 == "--exitcodes" ]]; then
    printexitcodes
  elif [[ $1 == "--write-config-file" ]]; then
    RCFILE=${2:-$PWD/.rsincr.conf}
    writercfile
  elif [[ $# -le 1 ]]; then
    RCFILE=${1:-$PWD/.rsincr.conf}
  else
    log ERR "Bad arguments: $*"
    log INFO "Use -h | --help for usage information"
    # Exit without logging pretty script finish (we didn't log start yet)
    exit 2
  fi
}

function set_times {
  DATE=$(/usr/bin/date "+%FT%T")                          # Canonical datetime
  DATE_PRETTY=$(/usr/bin/date "+%F %T" --date="$DATE")    # For pretty-printing
  DATE_SAFE=$(/usr/bin/date "+%FT%H%m%S" --date="$DATE")  # Safe for filesystem
  MONTH_DAY=$(/usr/bin/date "+%d" --date="$DATE")
  WEEK_DAY=$(/usr/bin/date "+%u" --date="$DATE")
}

function load_config {
  if [[ -e $RCFILE ]]; then
    log INFO "Using config file \"$RCFILE\""
    source $RCFILE
  else
    log ERR "Couldn't find config file \"$RCFILE\""
    log INFO "Use -h | --help for usage information"
    finish 10
  fi
  if [[ -t 1 ]]; then
    # If we are running interactively from a TTY, add extra rsync options for
    # running progress updates
    RSYNC_OPTS="$RSYNC_OPTS $RSYNC_INT_OPTS"
  else
    # Otherwise, add extra rsync options for simple stats summary at end to 
    # avoid making a mess in logs
    RSYNC_OPTS="$RSYNC_OPTS $RSYNC_LOG_OPTS"
  fi
}

function validate_config {
  if ([[ $DEST != "remote" ]] && [[ $DEST != "local" ]]); then
    log ERR "Config error: Backup destination ('DEST') must exist and should be string 'remote' or 'local'"; finish 20
  elif ([[ $DEST == "remote" ]] && [[ -z $HOST ]]); then
    log ERR "Config error: Backup destination ('DEST') is 'remote', but HOST is not set"; finish 21
  elif ([[ $DEST == "remote" ]] && [[ -z $USER ]]); then
    log ERR "Config error: Backup destination ('DEST') is 'remote', but USER is not set"; finish 22
  elif ([[ -n $FULL_BACKUP ]] && [[ $FULL_BACKUP != true ]] && [[ $FULL_BACKUP != false ]]); then
    log ERR "Config error: Force full backup ('FULL_BACKUP') should be 'true' or 'false' or empty"; finish 23
  elif [[ -n $FULL_BACKUP_MONTH_DAYS ]]; then
    # TODO: 0 passes - this should be fixed
    for DAY in $(echo $FULL_BACKUP_MONTH_DAYS); do
      if [[ ! $(seq 1 31) =~ $DAY ]]; then
        log ERR "Config error: FULL_BACKUP_MONTH_DAYS should be space-separated list of integers between 1 and 31 (or omitted)"
        finish 24
      fi
    done
  elif [[ -n $FULL_BACKUP_WEEK_DAYS ]]; then
    for DAY in $(echo $FULL_BACKUP_WEEK_DAYS); do
      if [[ ! $(seq 0 7) =~ $DAY ]]; then
        log ERR "Config error: FULL_BACKUP_WEEK_DAYS should be space-separated list of integers between 0 and 7 (or omitted)"
        finish 25
      fi
    done
  elif ([[ -n $RETENTION_DAYS ]] && [[ ! $RETENTION_DAYS -ge 1 ]]); then
    log ERR "Config error: RETENTION_DAYS should be a positive integer (or omitted)"
    finish 26
  fi
}

function lock {
  exec 200>$LOCKFILE
  flock -n 200 && return 0 || return 1
}

function checks {
  if [[ ! -e "$SOURCE_PATH" ]]; then
    log ERR "Source $SOURCE_PATH doesn't exist"
    finish 30
  elif ([[ $DEST == "local" ]] && [[ ! -e "$DEST_PATH" ]]); then
    log ERR "Local destination path $DEST_PATH doesn't exist"
    finish 31
  elif [[ $DEST == "remote" ]]; then
    remoteexecute "exit"
    SSH_TEST_RETURN=$?
    if [[ SSH_TEST_RETURN -ne 0 ]]; then
      log ERR "Couldn't log into remote host $HOST"; finish 40
    elif (remoteexecute "[[ ! -e \"$DEST_PATH\" ]]"); then
      log ERR "Remote destination path $DEST_PATH doesn't exist"
      finish 32
    fi
  fi
}

function determine_backup_type {
  if $FULL_BACKUP; then
    log INFO "Full backup requested"
  elif [[ $FULL_BACKUP_MONTH_DAYS =~ $MONTH_DAY ]]; then
    log INFO "Month day is $MONTH_DAY, doing full backup"
  elif [[ $FULL_BACKUP_WEEK_DAYS =~ $WEEK_DAY ]]; then
    log INFO "Week day is $WEEK_DAY, doing full backup"
  elif ([[ $DEST == "local" ]] && [ ! -h "$DEST_PATH/latest" ]); then
    log INFO "No 'latest' backup pointer found locally, doing full backup"
  elif ([[ $DEST == "remote" ]] && remoteexecute "[ ! -h \"$DEST_PATH/latest\" ]"); then
    log INFO "No 'latest' backup pointer found remotely, doing full backup"
  else
    log INFO "Doing incremental backup"
    RSYNC_OPTS="$RSYNC_OPTS --delete --link-dest=../latest"
  fi
}

function backup {
  log INFO "Backup source     : $SOURCE_PATH"
  if [[ $DEST == "local" ]]; then
    log INFO "Backup destination: $DEST_PATH"
    log INFO "Starting backup..."
    rsync $RSYNC_OPTS "$SOURCE_PATH/" "$DEST_PATH/back-$DATE_SAFE"
    RSYNC_EXIT_STATUS=$?
    # Update mtime of the backup folder we just created
    # mtime is used later to purge old backups
    touch "$DEST_PATH/back-$DATE_SAFE"
  elif [[ $DEST == "remote" ]]; then
    log INFO "Backup destination: $USER@$HOST:$DEST_PATH"
    log INFO "Starting backup..."
    rsync $RSYNC_OPTS "$SOURCE_PATH/" $USER@$HOST:"$DEST_PATH/back-$DATE_SAFE"
    RSYNC_EXIT_STATUS=$?
    remoteexecute "touch \"$DEST_PATH/back-$DATE_SAFE\""
  fi
  DURATION=$SECONDS
  log INFO "Elapsed time $(($DURATION / 3600))h $(((($DURATION / 60)) % 60))m $(($DURATION % 60))s."
  if ([[ $RSYNC_EXIT_STATUS != 0 ]] && [[ $RSYNC_EXIT_STATUS != 24 ]]); then
    log ERR "Backup unsuccessful. rsync failed with status $RSYNC_EXIT_STATUS."
    log INFO "Exiting and not purging old backups."; finish 50
  fi
  log INFO "Backup successful."
}

function link_latest {
  # Re-point $DEST_PATH/latest at new backup
  if [[ $DEST == "local" ]]; then
    [ -h "$DEST_PATH/latest" ] && rm "$DEST_PATH/latest"
    ln -s "back-$DATE_SAFE" "$DEST_PATH/latest" || log WARN "Couldn't create link to latest backup"
  elif [[ $DEST == "remote" ]]; then
    remoteexecute "[ -h \"$DEST_PATH/latest\" ] && rm \"$DEST_PATH/latest\""
    remoteexecute "ln -s \"back-$DATE_SAFE\" \"$DEST_PATH/latest\"" || log WARN "Couldn't create link to latest backup"
  fi
}

function purge {
  OLDIFS=$IFS
  IFS=$'\n'
  if [[ -z $RETENTION_DAYS ]]; then
    log INFO "Purging disabled, will not look for old backups to purge"
  elif [[ $DEST == "local" ]]; then
    for EXPIRED_BACKUP_DIR in $(find -H "$DEST_PATH" -mindepth 1 -maxdepth 1 -type d -mtime +$(($RETENTION_DAYS-1))); do
      log INFO "Purging $EXPIRED_BACKUP_DIR"
      mkdir $PWD/.empty_dir
      rsync -r --delete --info=progress2 $PWD/.empty_dir/ "$EXPIRED_BACKUP_DIR"
      rmdir $PWD/.empty_dir "$EXPIRED_BACKUP_DIR"
    done
  elif [[ $DEST == "remote" ]]; then
    for EXPIRED_BACKUP_DIR in $(remoteexecute "find -H \"$DEST_PATH\" -mindepth 1 -maxdepth 1 -type d -mtime +$(($RETENTION_DAYS-1))"); do
      log INFO "Purging $EXPIRED_BACKUP_DIR"
      mkdir "$PWD/.empty_dir"
      rsync -r --delete --info=progress2 "$PWD/.empty_dir/" $USER@$HOST:"$EXPIRED_BACKUP_DIR"
      rmdir "$PWD/.empty_dir"
      remoteexecute "rmdir \"$EXPIRED_BACKUP_DIR\""
    done
  fi
  IFS=$OLDIFS	# Reset IFS
  unset -v OLDIFS
}

function remoteexecute {
  ssh $USER@$HOST "$@"
}

function log {
  if [[ -t 1 ]]; then
    # If stdout is a TTY, store control characters for pretty formatting in
    # variables. Otherwise, variables are empty so this won't make parsing logs
    # hard.
    INFO_STDOUT_FMT='\e[1;32m'  # Bold, green
    RESET_STDOUT_FMT='\e[0m'    # Unset formatting ctrl chars
  fi
  if [[ -t 2 ]]; then
    # If stdout is a TTY, store control characters for pretty
    # formatting in variables. Otherwise, variables are empty so
    # this won't make parsing logs hard
    ERR_STDERR_FMT='\e[1;31m'   # Bold, red
    WARN_STDERR_FMT='\e[1;33m'  # Bold, yellow
    RESET_STDERR_FMT='\e[0m'    # Unset formatting ctrl chars
  fi
  LOGTIME=$(/usr/bin/date "+%T" | /usr/bin/tr -d "\n")
  if ([[ $1 == "ERR" ]] && [[ ! -z $2 ]] && [[ ! -t 1 ]]); then
    # If stdout is a TTY, store control characters for pretty formatting in
    # variables. Otherwise, variables are empty so this won't make parsing logs
    # hard.
    echo -e "$LOGTIME ${ERR_STDERR_FMT}ERROR:${RESET_STDERR_FMT} $2" | \
      tee > /dev/stderr
  elif ([[ $1 == "ERR" ]] && [[ ! -z $2 ]]); then
    # If stdout is a terminal, just send our errors to stderr
    echo -e "$LOGTIME ${ERR_STDERR_FMT}ERROR:${RESET_STDERR_FMT} $2" 1>&2
  elif ([[ $1 == "WARN" ]] && [[ ! -z $2 ]] && [[ ! -t 1 ]]); then
    echo -e "$LOGTIME ${WARN_STDERR_FMT}WARN:${RESET_STDERR_FMT} $2" | \
      tee > /dev/stderr
  elif ([[ $1 == "WARN" ]] && [[ ! -z $2 ]]); then
    echo -e "$LOGTIME ${WARN_STDERR_FMT}WARN:${RESET_STDERR_FMT} $2" 1>&2
  elif ([[ $1 == "INFO" ]] && [[ ! -z $2 ]]); then
    echo -e "$LOGTIME ${INFO_STDOUT_FMT}INFO:${RESET_STDOUT_FMT} $2"
  else
    echo -e "$LOGTIME ${ERR_STDERR_FMT}ERROR:${RESET_STDERR_FMT} Logging err" \
      1>&2 && finish 10
  fi
}

function writercfile {
  cat <<EOF > $RCFILE
# Lockfile path
# Allows setting separate locks for separate backup jobs
LOCKFILE="./.rsincr.lock"

# Base rsync options
# Applied for both full and incremental backups
# Applied for both interactive and logged jobs
RSYNC_OPTS="-a"
#RSYNC_OPTS="-az"
#RSYNC_OPTS="-a -e 'ssh -p 2222'"
#RSYNC_OPTS="-a -e 'ssh -c arcfour'"

# Extra rsync options when run from an interactive session (TTY)
RSYNC_INT_OPTS="--info=progress2"

# Extra rsync options when not run from an interactive session
# i.e. redirected to a log
RSYNC_LOG_OPTS="--info=stats1"

# Backup locally or over SSH?
# Should be one of 'remote' or 'local'
# If 'remote', HOST should also be declared
DEST=remote
#DEST=local

# Remote backup host and user
# Ignored if DEST=local
HOST=backup.example.com
USER=backup

# Source and Destination folders
SOURCE_PATH="~/Documents"
DEST_PATH="~/Backups"

# Always do full backup. Default false if omitted.
FULL_BACKUP=false

# Days of month to do fresh full backup
# Space-separated, not zero-padded
# Comment out to disable
#FULL_BACKUP_MONTH_DAYS="1"
#FULL_BACKUP_MONTH_DAYS="1 15"

# Days of week to do fresh full backup
# Space-separated, 1=Mon, 7=Sun, not zero-padded
# Comment out to disable
#FULL_BACKUP_WEEK_DAYS="7"

# Days of backups to keep
# Comment out to disable purging
RETENTION_DAYS=30
EOF

  if [[ $? == 0 ]]; then
    log INFO "Wrote default config file to $RCFILE"; exit 0
  else	
    log ERR "Failed to write config file to $RCFILE"; exit 2
  fi
}

function printhelp {
  echo "rsincr.sh"
  echo "Wrapper around rsync to perform incremental backups."
  echo
  echo "Usage:"
  echo "rsincr.sh [configfile]                      Run backup job in <configfile>"
  echo "rsincr.sh --write-config-file [configfile]  Write default config to <configfile> "
  echo "rsincr.sh -h, --help                        Show this message"
  echo "rsincr.sh --exitcodes                       List exit codes"
  echo
  echo "Config file must exist. Default location if unspecified: ./.rsincr.conf"
  exit 1
}

function printexitcodes {
  echo "rsincr.sh - Exit codes:"
  echo " 0 :: Normal execution"
  echo " 1 :: Generic error"
  echo " 2 :: Bad arguments"
  echo " 3 :: Couldn't acquire lock on lockfile"
  echo "10 :: Couldn't find specified config file"
  echo "20 :: Config error: Backup destination ('DEST') must exist and should be string 'remote' or 'local'"
  echo "21 :: Config error: Backup destination ('DEST') is 'remote', but HOST is not set"
  echo "22 :: Config error: Backup destination ('DEST') is 'remote', but USER is not set"
  echo "23 :: Config error: Force full backup ('FULL_BACKUP') should be 'true' or 'false' or empty"
  echo "24 :: Config error: Days of month to force full backup ('FULL_BACKUP_MONTH_DAYS') should be space-separated list of integers between 1 and 31 (or omitted)"
  echo "25 :: Config error: Days of week to force full backup ('FULL_BACKUP_WEEK_DAYS') should be space-separated list of integers between 0 and 7 (or omitted)"
  echo "26 :: Config error: Days of backups to retain ('RETENTION_DAYS') should be a positive integer (or omitted)"
  echo "30 :: Config error: Source path ('SOURCE_PATH') doesn't exist"
  echo "31 :: Config error: Local destination path ('DEST_PATH') doesn't exist"
  echo "32 :: Config error: Remote destination path ('DEST_PATH') doesn't exist"
  echo "40 :: Couldn't access remote host ('HOST')"
  echo "50 :: Error in backup run. Consult rsync output."
  exit 1
}

function finish {
  log INFO "$0 finishing at $(/usr/bin/date "+%F %T")"
  if [[ -n $1 ]]; then
    exit $1
  else
    exit 1
  fi
}

trap finish SIGHUP SIGINT SIGTERM

main "$@"
