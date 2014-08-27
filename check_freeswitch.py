#!/usr/bin/env python
import traceback
import subprocess
import re

__author__ = 'gdoermann'


######################################################
#   Constants and Lib
######################################################

# Modify this to the location of your fs_cli
FS_SETTINGS = {
    'fs_cli': '/usr/bin/fs_cli',
    'host': None,
    'port': None,
    'password': None,
}

try:
    # You can create a file named "fs_settings.py" on your python path with the above variable FS_SETTINGS
    from fs_settings import *
except ImportError:
    traceback.print_exc()


class NAGIOS_CODE:
    OK = 0
    WARNING = 1
    CRITICAL = 2
    UNKNOWN = 3


def clean_text(value):
    import unicodedata

    value = unicodedata.normalize('NFKD', unicode(value)).encode('ascii', 'ignore').strip()
    value = unicode(re.sub('[^\w\s-]', '', value))
    return re.sub('[-\s]+', '-', value.strip())


######################################################
#   Base command class
######################################################
class BaseCommand(object):
    COMMAND = ''

    def __init__(self, cmd_args):
        self.args = cmd_args
        self.verbosity = cmd_args.verbosity
        self.output_dict = None
        self.profile = self.args.profile
        self.full_fs_command = self.COMMAND

    def at_warning_level(self, n):
        return self.args.warning and n and n > self.args.warning

    def at_critical_level(self, n):
        return self.args.critical and n and n > self.args.critical

    def code_for_number(self, n):
        if self.at_critical_level(n):
            code = NAGIOS_CODE.CRITICAL
        elif self.at_warning_level(n):
            code = NAGIOS_CODE.WARNING
        else:
            code = NAGIOS_CODE.OK
        return code

    def run(self):
        verbosity = self.args.verbosity
        self.log('Args: {}'.format(self.args), 3)
        code, output, errors = self.run_command()
        self.log('Command output: code: {}\n stdout: {}\n stderr: {}'.format(code, output, errors), 3)
        if code != 0:
            print 'ERROR: Command failed with code {}: {}'.format(code, errors)
            exit(NAGIOS_CODE.UNKNOWN)

        num = self.parse(output)
        code = self.code_for_number(num)

        msg = 'FreeSWITCH OK: {} ({}) = {}'.format(self.__class__.__name__, self.full_fs_command, num)
        if self.args.warning:
            msg += ';{}'.format(self.args.warning)
        if self.args.critical:
            msg += ';{}'.format(self.args.critical)
        self.log('Exit Code: {}'.format(code), 1)
        self.log('Message Length: {}'.format(len(msg)), 3)
        print msg
        exit(code)

    @property
    def cmd_args(self):
        c = ['{fs_cli}'.format(**FS_SETTINGS)]
        if FS_SETTINGS.get('host', None):
            c += ['--host', FS_SETTINGS.get('host', None)]
        if FS_SETTINGS.get('port', None):
            c += ['--port', FS_SETTINGS.get('port', None)]
        if FS_SETTINGS.get('password', None):
            c += ['--password', FS_SETTINGS.get('password', None)]

        fs_cmd = self.COMMAND
        profile = ''
        if self.profile:
            profile = clean_text(self.profile)  # remove anything but [A-Za-z9-0]
        self.full_fs_command = fs_cmd.format(profile=profile)
        c += ['-x', self.full_fs_command]

        self.log('Command: {}'.format(' '.join(c)), 2)
        return c

    def log(self, msg, verbosity):
        if self.verbosity >= verbosity:
            print msg

    def run_command(self):
        cmd = self.cmd_args
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            proc.wait()
            return proc.returncode, proc.stdout.read(), proc.stderr.read()
        except OSError, e:
            return 1, "", '{}: {}'.format(e.args[1], cmd[0])

    def parse(self, output):
        output_dict = {}
        for line in output.split('\n'):
            line = line.strip()
            match = KEY_VALUE_REGEX.match(line)
            totals = [i for i in COUNT_TOTAL.findall(line) if i]
            if match:
                self.log('Match line: {}'.format(line), 2)
                k, v = match.groups()
                if k:
                    output_dict[k.replace('-', '_').lower()] = v

            elif totals:
                for total in totals:
                    if total:
                        self.log('Total line: {}'.format(line), 2)
                        total_count = int(total)
                        output_dict['total_calls'] = total_count
        self.log('Parsed output: {}'.format(output_dict), 2)

        self.output_dict = output_dict
        return self.process(output_dict)

    def process(self, d):
        return -1


######################################################
#   Actual command class definitions
######################################################

class ShowCallsCount(BaseCommand):
    COMMAND = 'show calls count'

    def process(self, d):
        return d.get('total_calls', 0)


class SofiaStatus(BaseCommand):
    COMMAND = 'sofia status profile {profile}'

    def process(self, d):
        return int(d.get('calls_in', 0)) + int(d.get('calls_out', 0))


class FailedCallsIn(BaseCommand):
    COMMAND = 'sofia status profile {profile}'

    def process(self, d):
        return int(d.get('failed_calls_in', 0))


class FailedCallsOut(BaseCommand):
    COMMAND = 'sofia status profile {profile}'

    def process(self, d):
        return int(d.get('failed_calls_out', 0))


######################################################
#   Put together the actual functions
######################################################

FS_CHECKS = {
    "show-calls-count": ShowCallsCount,
    "sofia-status": SofiaStatus,
    "failed-calls-in": FailedCallsIn,
    "failed-calls-out": FailedCallsOut,
}

KEY_VALUE_REGEX = re.compile('([\w-]*)\s{3,100}(.*)')
COUNT_TOTAL = re.compile('([\d]*)\s*total')


def main(main_args):
    # The only thing main should do is look up the associated class and run it!
    klass = FS_CHECKS.get(main_args.query)(main_args)
    klass.run()


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
    program_args = parser.parse_args()
    if 'sofia' in program_args.query and not program_args.profile:
        print 'No sofia profile specified'
        exit(NAGIOS_CODE.UNKNOWN)
    try:
        main(program_args)
    except Exception:
        print 'Command Failed: {}'.format(traceback.format_exc(1))
        exit(NAGIOS_CODE.UNKNOWN)