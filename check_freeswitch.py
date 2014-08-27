#!/usr/bin/env python
import traceback
import subprocess
import re

__author__ = 'gdoermann'

# Modify this to the location of your fs_cli
FS_SETTINGS = {
    'fs_cli': '/usr/bin/fs_cli',
    'host': None,
    'port': None,
    'password': None,
}

FS_CHECKS = {
    "show-calls-count": 'show calls count',
    "sofia-status": 'sofia status profile {profile}',
    "sofia-status-profile-failed-calls-in": "sofia status profile {profile} failed calls in",
    "sofia-status-profile-failed-calls-out": "sofia status profile {profile}  failed calls out"
}

DEFAULT_PROCESSOR = lambda d: int(d.get('calls_in', 0)) + int(d.get('calls_out', 0))

PROCESSORS = {
    "show-calls-count": lambda d: d.get('total_calls', 0),
    "sofia-status": lambda d: int(d.get('calls_in', 0)) + int(d.get('calls_out', 0)),
    "sofia-status-profile-failed-calls-in": lambda d: int(d.get('failed_calls_in', 0)),
    "sofia-status-profile-failed-calls-out": lambda d: int(d.get('failed_calls_out', 0)),
}

KEY_VALUE_REGEX = re.compile('([\w-]*)\s{3,100}(.*)')
COUNT_TOTAL = re.compile('([\d]*)\s*total')

try:
    # You can create a file named "fs_settings.py" on your python path with the above variable FS_SETTINGS and FS_CHECKS
    from fs_settings import *
except ImportError:
    traceback.print_exc()


def clean_text(value):
    import unicodedata

    value = unicodedata.normalize('NFKD', unicode(value)).encode('ascii', 'ignore').strip()
    value = unicode(re.sub('[^\w\s-]', '', value))
    return re.sub('[-\s]+', '-', value.strip())


class CODE:
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


def run_command(cmd):
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.wait()
        return proc.returncode, proc.stdout.read(), proc.stderr.read()
    except OSError, e:
        return 1, "", '{}: {}'.format(e.args[1], cmd[0])


def parse_output(output, verbosity=0):
    output_dict = {}
    for line in output.split('\n'):
        line = line.strip()
        match = KEY_VALUE_REGEX.match(line)
        totals = [i for i in COUNT_TOTAL.findall(line) if i]
        if match:
            if verbosity >= 2:
                print 'Match line: {}'.format(line)
            k, v = match.groups()
            if k:
                output_dict[k.replace('-', '_').lower()] = v

        elif totals:
            for total in totals:
                if total:
                    if verbosity >= 2:
                        print 'Total line: {}'.format(line)
                    total_count = int(total)
                    output_dict['total_calls'] = total_count
    return output_dict


def main(args):
    verbosity = args.verbosity
    if verbosity >= 3:
        print 'Args: {}'.format(args)
    cmd = ['{fs_cli}'.format(**FS_SETTINGS)]
    if FS_SETTINGS.get('host', None):
        cmd += ['--host', FS_SETTINGS.get('host', None)]
    if FS_SETTINGS.get('port', None):
        cmd += ['--port', FS_SETTINGS.get('port', None)]
    if FS_SETTINGS.get('password', None):
        cmd += ['--password', FS_SETTINGS.get('password', None)]
    fs_cmd = FS_CHECKS.get(args.query)
    profile = ''
    if args.profile:
        profile = clean_text(args.profile)  # remove anything but [A-Za-z9-0]
    full_fs_command = fs_cmd.format(profile=profile)
    cmd += ['-x', full_fs_command]
    if verbosity >= 2:
        print 'Command: {}'.format(' '.join(cmd))
    code, output, errors = run_command(cmd)
    if verbosity >= 3:
        print 'Command output: code: {}\n stdout: {}\n stderr: {}'.format(code, output, errors)
    if code != 0:
        print 'ERROR: Command failed with code {}: {}'.format(code, errors)
        exit(CODE.UNKNOWN)

    output_dict = parse_output(output, verbosity=verbosity)
    if verbosity >= 2:
        print 'Parsed output: {}'.format(output_dict)

    processor = PROCESSORS.get(args.query, DEFAULT_PROCESSOR)
    num = processor(output_dict)
    code = CODE.OK
    if num > args.warning:
        code = CODE.WARNING
    if num > args.critical:
        code = CODE.CRITICAL
    msg = 'FreeSWITCH OK: {} = {}'.format(full_fs_command, num)
    if args.warning:
        msg += ';{}'.format(args.warning)
    if args.critical:
        msg += ';{}'.format(args.critical)
    if verbosity >=1:
        print 'Exit Code: {}'.format(code)
    print msg
    exit(code)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Separate CDRs for a set of ANIs (DIDs).')
    parser.add_argument('-v', dest='verbosity', type=int, choices=(0, 1, 2, 3),
                        help='Verbosity level.  See: https://www.monitoring-plugins.org/doc/guidelines.html#PLUGOUTPUT')
    parser.add_argument('-w', dest='warning', type=int, help='Threshold that generates a Nagios warning')
    parser.add_argument('-c', dest='critical', type=int, help='Threshold that generates a Nagios critical warning')
    parser.add_argument('-f', dest='--perfdatatitle', type=str,
                        help="Title for Nagios Performance Data. Note: don't use spaces.")
    parser.add_argument('-q', '--query', dest='query', type=str, choices=FS_CHECKS.keys(), required=True,
                        help="These are mapped to specific fs_cli -x checks e.g. show-calls-count is mapped to "
                             "'show calls count'")
    parser.add_argument('--profile', dest='profile', type=str, help='sofia profile (required for sofia checks)',
                        default=None)
    args = parser.parse_args()
    if 'sofia' in args.query and not args.profile:
        print 'No sofia profile specified'
        exit(CODE.UNKNOWN)
    try:
        main(args)
    except Exception:
        print 'Command Failed: {}'.format(traceback.format_exc(1))
        exit(CODE.UNKNOWN)