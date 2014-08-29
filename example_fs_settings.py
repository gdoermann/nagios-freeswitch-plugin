import commands
ETH1 = commands.getoutput("""IPS=`ip addr show | grep scope | grep -v -e inet6 -e 127. | sed -e 's/\s*inet//' -e 's/\/.*global//'` && IP_REGEX='[[:digit:]]{1,3}\.[[:digit:]]{1,3}\.[[:digit:]]{1,3}\.[[:digit:]]{1,3}' && ETH1=$(echo $IPS | egrep -Ei "${IP_REGEX}" | grep -oEi "${IP_REGEX}" | grep 10.10) && echo ${ETH1}""")
__author__ = 'gdoermann'

# Example for if FS CLI binds on ETH1
FS_SETTINGS = {
    'fs_cli': '/usr/bin/fs_cli',
    'host': ETH1,
    'port': None,
    'password': 'secret',
}

# Example for if FS CLI binds on localhost
FS_SETTINGS = {
    'fs_cli': '/usr/bin/fs_cli',
    'host': '127.0.0.1',
    'port': None,
    'password': 'secret',
}