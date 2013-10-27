#!/usr/bin/env python

"""This script automates the process of connecting to /remote_api. It has
default options for connecting to production, and automatically imports some
models so that you can do something useful once you're connected.
"""

import optparse
import os
import struct
import fcntl
import termios
import signal
import sys

try:
    import pexpect
except ImportError, e:
    print """
You need to install pexpect to run this script. Try
pip install pexpect
"""
    print e.message()

parser = optparse.OptionParser()
parser.add_option('--prod', action='store_true',
    help="shortcut to automatically set server and app options to connect to production. Be careful!")
parser.add_option('-s', '--server', default='localhost:8080',
    help="host and port to connect to")
parser.add_option('-a', '--app', default='dev~khan-academy',
    help="App Engine identifier to use")
parser.add_option('-e', '--email', default='test@example.com',
    help="email to autheticate with if required")
parser.add_option('-p', '--password', default=None,
    help="password to authenticate with if required")
parser.add_option('-q', '--quiet', action='store_true', default=False,
    help="Don't print as much")
parser.add_option('--secure', action='store_true', default=False)
options, args = parser.parse_args()

# quickly connect to production
if options.prod:
    options.server = 'khan-academy.appspot.com:80'
    options.app = 's~khan-academy'
    # secure doesn't seem to work
    # options.secure = True
    if options.email == 'test@example.com':
        options.email = None

    print ('\033[31m' + "ACHTUNG! GEFAHR!" + '\033[0m' +
        " You are connecting to the live site. Be careful!")

def prompt_and_send(default=None, prompt=None):
    if default is None:
        default = raw_input(prompt)
    sendline(default)
    return default

def sendline(s):
    if not options.quiet:
        print s
    p.sendline(s)

child_options = ['-s %s' % options.server]
if options.secure:
    child_options.append('--secure')

connect = 'remote_api_shell.py %s %s "/remote_api"' % (' '.join(child_options), options.app)
if not options.quiet:
    print connect
p = pexpect.spawn(connect)

prompt = '%s>' % options.app
index = p.expect(['Email:', prompt])
if index == 0: # we were prompted for email/pass
    options.email = prompt_and_send(default=options.email, prompt='Email:')

    # use default when connecting to dev server
    if options.password is None and options.email == 'test@example.com':
        options.password = ''

    p.expect('Password:')
    prompt_and_send(prompt='Password for %s:' % options.email,
        default=options.password)
    p.expect(prompt)

repdir = os.path.dirname(os.path.abspath(__file__))
pwd = os.getcwd()
if not pwd.startswith(repdir):
    print 'NOTE: Your pwd is not inside the repo path. Imports still come from the repo path.'

# for some reason this does not echo
sendline('sys.path.insert(0, "%s")' % repdir)
# but this does
p.expect(prompt)

# useful imports
p.sendline('from models import *')

# set up initial winsize
rows, cols = map(int, os.popen('stty size', 'r').read().split())
p.setwinsize(rows, cols)

# make sure sigwinch get sent to child
def sigwinch_passthrough(sig, data):
    s = struct.pack("HHHH", 0, 0, 0, 0)
    a = struct.unpack('hhhh', fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, s))
    p.setwinsize(a[0], a[1])
signal.signal(signal.SIGWINCH, sigwinch_passthrough)

# finally, hand off control to user
p.interact()
