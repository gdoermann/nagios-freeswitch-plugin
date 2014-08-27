#!/usr/bin/env python
"""
Examples:

Check channels count.  Greater than 100 warning, greater than 200 is critical
    python check_freeswitch.py -q show-channels-count --profile=cci -w 100 -c 200

Check freeswitch status.  Greater than 70% warning load, greater than 85% warning load
    python check_freeswitch.py -q status --profile=cci -w 0.7 -c 0.85
    python check_freeswitch.py -q status --profile=cci -w 70 -c 85  # Does the same thing as above...

"""
import traceback
import subprocess
import re
import nagiosplugin

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
    KEY_VALUE_REGEX = re.compile('([\w-]*)\s{3,100}(.*)')
    COUNT_TOTAL = re.compile('([\d]*)\s*total')
    DEFAULT_WARNING = None
    DEFAULT_CRITICAL = None


    def __init__(self, cmd_args):
        self.args = cmd_args
        self.verbosity = cmd_args.verbosity
        self.output_dict = None
        self.profile = self.args.profile
        self.full_fs_command = self.COMMAND
        self.warning = self.args.warning or self.DEFAULT_WARNING
        self.critical = self.args.critical or self.DEFAULT_CRITICAL
        self.code = NAGIOS_CODE.OK

    def at_warning_level(self, n):
        return self.warning and n and n > self.warning

    def at_critical_level(self, n):
        return self.critical and n and n > self.critical

    def determine_code(self, n):
        if self.at_critical_level(n):
            self.code = NAGIOS_CODE.CRITICAL
        elif self.at_warning_level(n):
            self.code = NAGIOS_CODE.WARNING
        return self.code

    def run(self):
        self.log('Args: {}'.format(self.args), 3)
        code, output, errors = self.run_command()
        self.log('Command output: code: {}\n stdout: {}\n stderr: {}'.format(code, output, errors), 3)
        if code != 0:
            print 'ERROR: Command failed with code {}: {}'.format(code, errors)
            exit(NAGIOS_CODE.UNKNOWN)

        return self.parse(output)
        # num = self.parse(output)
        # code = self.determine_code(num)
        #
        # msg = 'FreeSWITCH OK: {} ({}) = {}'.format(self.__class__.__name__, self.full_fs_command, num)
        # if self.warning:
        #     msg += ';{}'.format(self.warning)
        # if self.critical:
        #     msg += ';{}'.format(self.critical)
        # self.log('Exit Code: {}'.format(code), 1)
        # self.log('Message Length: {}'.format(len(msg)), 3)
        # print msg
        # exit(code)

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

    def parse_dict(self, output):
        output_dict = {}
        for line in output.split('\n'):
            line = line.strip()
            match = self.KEY_VALUE_REGEX.match(line)
            totals = [i for i in self.COUNT_TOTAL.findall(line) if i]
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
                        output_dict['total'] = total_count
        self.log('Parsed output: {}'.format(output_dict), 2)
        return output_dict

    def parse(self, output):
        output_dict = self.parse_dict(output)
        self.output_dict = output_dict
        return self.process(output_dict)

    def process(self, d):
        yield nagiosplugin.Metric('total', -1, min=-1, context='calls')


######################################################
#   Actual command class definitions
######################################################

class ShowCallsCount(BaseCommand):
    COMMAND = 'show calls count'

    def process(self, d):
        yield nagiosplugin.Metric('total', d.get('total', 0), min=-1, context='calls')


class ShowBridgedCallsCount(BaseCommand):
    COMMAND = 'show bridged_calls count'

    def process(self, d):
        yield nagiosplugin.Metric('total', d.get('total', 0), min=0, context='calls')


class ShowChannelsCount(BaseCommand):
    COMMAND = 'show channels count'

    def process(self, d):
        yield nagiosplugin.Metric('total', d.get('total', 0), min=0, context='calls')


class SofiaStatus(BaseCommand):
    COMMAND = 'sofia status profile {profile}'

    def process(self, d):
        total = int(d.get('calls_in', 0)) + int(d.get('calls_out', 0))
        yield nagiosplugin.Metric('profile_calls', total, min=0, context='calls')


class FailedCallsIn(BaseCommand):
    COMMAND = 'sofia status profile {profile}'

    def process(self, d):
        yield nagiosplugin.Metric('failed_calls_in', int(d.get('failed_calls_in', 0)), min=0, context='calls')


class FailedCallsOut(BaseCommand):
    COMMAND = 'sofia status profile {profile}'

    def process(self, d):
        yield nagiosplugin.Metric('failed_calls_out', int(d.get('failed_calls_out', 0)), min=0, context='calls')


class FSStatus(BaseCommand):
    COMMAND = 'status'
    DEFAULT_WARNING = 0.75
    DEFAULT_CRITICAL = 0.9

    CHECK_KEYS = None

    def __init__(self, cmd_args):
        super(FSStatus, self).__init__(cmd_args)
        # Warnings and critical levels must be percentages
        if self.warning and self.warning > 1:
            self.warning = float(self.warning) / 100
        if self.critical and self.critical > 1:
            self.critical = float(self.critical) / 100

    def parse_dict(self, output):
        def format_bytes(s):
            return float(s.replace('G', '000000000').replace('K', '000').replace('M', '000000'))

        lines = [l.strip() for l in output.split('\n')]
        total_line = lines[2]
        sessions_line = lines[3]
        sps_line = lines[4]
        max_sessions_line = lines[5]
        cpu_line = lines[6]
        stack_line = lines[7]

        self.log('Total Line: {}'.format(total_line), 3)
        self.log('Sessions Line: {}'.format(sessions_line), 3)
        self.log('Sessions Per Second Line: {}'.format(sps_line), 3)
        self.log('Max sessions Line: {}'.format(max_sessions_line), 3)
        self.log('CPU Line: {}'.format(cpu_line), 3)
        self.log('Stack Line: {}'.format(stack_line), 3)

        cpu_data = cpu_line.split(' ')[-1].split('/')
        stack_data = stack_line.split(' ')[-1].split('/')

        output_dict = {
            'total_sessions': total_line.split(' ')[0],
            'current_sessions': sessions_line.split(' ')[0],
            'last_five_sessions': sessions_line.split(' ')[-1],
            'sessions_per_second': sps_line.split(' ')[-1],
            'max_sessions_per_second': clean_text(sps_line.split('max')[-1].strip().split(' ')[0]),
            'last_five_sps': sps_line.split(' ')[-1],
            'max_sessions': max_sessions_line.split(' ')[0],
            'cpu_current': format_bytes(cpu_data[0]),
            'cpu_max': format_bytes(cpu_data[1]),
            'stack_current': format_bytes(stack_data[0]),
            'stack_max': format_bytes(stack_data[1]),
        }

        self.log('Parsed output: {}'.format(output_dict), 2)
        return output_dict

    def process(self, d):
        current_sessions = float(d.get('current_sessions'))
        last_five_sessions = float(d.get('last_five_sessions'))
        max_sessions = float(d.get('max_sessions'))

        sessions_per_second = float(d.get('sessions_per_second'))
        last_five_sps = float(d.get('last_five_sps'))
        max_sessions_per_second = float(d.get('max_sessions_per_second'))

        cpu_current = float(d.get('cpu_current'))
        cpu_max = float(d.get('cpu_max'))

        stack_current = float(d.get('stack_current'))
        stack_max = float(d.get('stack_max'))

        data = {
            'sessions': current_sessions / max_sessions * 100.0,
            '5min_sessions': last_five_sessions / max_sessions * 100.0,
            'sps': sessions_per_second / max_sessions_per_second * 100.0,
            '5min_sps': last_five_sps / max_sessions_per_second * 100.0,
            'cpu': cpu_current / cpu_max * 100.0,
            'stack': stack_current / stack_max * 100.0,
        }
        for k, v in data.items():
            yield nagiosplugin.Metric(k, v, min=0.0, context='calls')

    def at_warning_level(self, n):
        if not self.warning:
            return False
        for k, v in n.items():
            if self.CHECK_KEYS and k not in self.CHECK_KEYS:
                continue
            if v and v > self.warning:
                return True
        return False

    def at_critical_level(self, n):
        if not self.critical:
            return False
        for k, v in n.items():
            if self.CHECK_KEYS and k not in self.CHECK_KEYS:
                continue
            if v and v > self.critical:
                return True
        return False

    def determine_code(self, n):
        if self.at_critical_level(n):
            self.code = NAGIOS_CODE.CRITICAL
        elif self.at_warning_level(n):
            self.code = NAGIOS_CODE.WARNING
        return self.code


class SessionsPerSecond(FSStatus):
    CHECK_KEYS = ['sps', '5min_sps']


class Sessions(FSStatus):
    CHECK_KEYS = ['sessions', '5min_sessions']


class FSCpu(FSStatus):
    CHECK_KEYS = ['cpu', ]


class FSStack(FSStatus):
    CHECK_KEYS = ['stack', ]

######################################################
#   Put together the actual functions
######################################################

FS_CHECKS = {
    "show-calls-count": ShowCallsCount,
    "show-bridged-calls-count": ShowBridgedCallsCount,
    "show-channels-count": ShowChannelsCount,
    "sofia-status": SofiaStatus,
    "failed-calls-in": FailedCallsIn,
    "failed-calls-out": FailedCallsOut,
    "status": FSStatus,
    'sessions-per-second': SessionsPerSecond,
    'sessions': Sessions,
    'cpu': FSCpu,
    'stack': FSStack,
}


class Freeswitch(nagiosplugin.Resource):
    def __init__(self, args):
        super(Freeswitch, self).__init__()
        self.args = args
        self.klass = FS_CHECKS.get(self.args.query)

    def probe(self):
        inst = self.klass(self.args)
        return inst.run()


@nagiosplugin.guarded
def main(main_args):
    # The only thing main should do is look up the associated class and run it!
    check = nagiosplugin.Check(
        Freeswitch(main_args),
        nagiosplugin.ScalarContext('calls', main_args.warning, main_args.critical))
    check.main(verbose=main_args.verbosity)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='Separate CDRs for a set of ANIs (DIDs).')
    parser.add_argument('-v', dest='verbosity', type=int, choices=(0, 1, 2, 3),
                        help='Verbosity level.  See: https://www.monitoring-plugins.org/doc/guidelines.html#PLUGOUTPUT')
    parser.add_argument('-w', dest='warning', type=float, help='Threshold that generates a Nagios warning')
    parser.add_argument('-c', dest='critical', type=float, help='Threshold that generates a Nagios critical warning')
    parser.add_argument('-f', dest='--perfdatatitle', type=str,
                        help="Title for Nagios Performance Data. Note: don't use spaces.")
    parser.add_argument('-q', '--query', dest='query', type=str, choices=FS_CHECKS.keys(),
                        default='status', help="These are mapped to specific fs_cli -x checks e.g. show-calls-count "
                                               "is mapped to 'show calls count'.  Default=status")
    parser.add_argument('--profile', dest='profile', type=str, help='sofia profile (required for sofia checks)',
                        default=None)
    program_args = parser.parse_args()
    if 'sofia' in program_args.query and not program_args.profile:
        print 'No sofia profile specified'
        exit(NAGIOS_CODE.UNKNOWN)

    main(program_args)
