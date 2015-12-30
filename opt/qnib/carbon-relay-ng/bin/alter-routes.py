#! /usr/bin/env python
# -*- coding: utf-8 -*-

"""

Usage:
    cli.py [options] view
    cli.py [options] (enable|disable) <dest>
    cli.py [options] add <dest> <ip> <port>
    cli.py (-h | --help)
    cli.py --version

The <dest> will be created as a RouteKey and one destination. New destinations are added as new routes.
If a destination vanishes the prefex is set to a nevermatching one.

Subcommands:
    add     Ensures <dest> is present and enabled
    del     Not possible (yet)
    disable Sets "NOWAYTHISMATCHES" as prefix, which should disable the route

Options:
    --host <str>            Host to connect to [default: 127.0.0.1]
    --port <int>            Port to connect to [default: 2004]
    --bufsize <int>         Buffer size to receive [default: 8192]

General Options:
    -h --help               Show this screen.
    --version               Show version.
    --loglevel, -L=<str>    Loglevel [default: WARN]
                            (ERROR, CRITICAL, WARN, INFO, DEBUG)
    --log2stdout, -l        Log to stdout, otherwise to logfile. [default: True]
    --logfile, -f=<path>    Logfile to log to (default: <scriptname>.log)
    --cfg, -c=<path>        Configuration file.

"""

# load librarys
import logging
import os
import re
import codecs
import ast
import sys
import json
import time
from ConfigParser import RawConfigParser, NoOptionError
import socket
from pprint import pprint

try:
    from docopt import docopt
except ImportError:
    HAVE_DOCOPT = False
else:
    HAVE_DOCOPT = True

__author__ = 'Christian Kniep <christian@qnib.org>'
__license__ = """GPL v2 License (http://www.gnu.org/licenses/old-licenses/gpl-2.0.en.html)"""


class QnibConfig(RawConfigParser):
    """ Class to abstract config and options
    """
    specials = {
        'TRUE': True,
        'FALSE': False,
        'NONE': None,
    }

    def __init__(self, opt):
        """ init """
        RawConfigParser.__init__(self)
        self.logformat = '%(asctime)-15s %(levelname)-5s [%(module)s] %(message)s'
        if opt is None:
            self._opt = {
                "--log2stdout": False,
                "--logfile": None,
                "--loglevel": "ERROR",
            }
        else:
            self._opt = opt
            self.loglevel = opt['--loglevel']
            self.logformat = '%(asctime)-15s %(levelname)-5s [%(module)s] %(message)s'
            self.log2stdout = opt['--log2stdout']
            if self.loglevel is None and opt.get('--cfg') is None:
                print "please specify loglevel (-L)"
                sys.exit(0)
            self.eval_cfg()

        self.eval_opt()
        self.set_logging()
        logging.info("SetUp of QnibConfig is done...")

    def do_get(self, section, key, default=None):
        """ Also lent from: https://github.com/jpmens/mqttwarn
            """
        try:
            val = self.get(section, key)
            if val.upper() in self.specials:
                return self.specials[val.upper()]
            return ast.literal_eval(val)
        except NoOptionError:
            return default
        except ValueError:  # e.g. %(xxx)s in string
            return val
        except:
            raise
            return val

    def config(self, section):
        ''' Convert a whole section's options (except the options specified
                explicitly below) into a dict, turning

                    [config:mqtt]
                    host = 'localhost'
                    username = None
                    list = [1, 'aaa', 'bbb', 4]

                into

                    {u'username': None, u'host': 'localhost', u'list': [1, 'aaa', 'bbb', 4]}

                Cannot use config.items() because I want each value to be
                retrieved with g() as above
            SOURCE: https://github.com/jpmens/mqttwarn
            '''

        d = None
        if self.has_section(section):
            d = dict((key, self.do_get(section, key))
                     for (key) in self.options(section) if key not in ['targets'])
        return d

    def eval_cfg(self):
        """ eval configuration which overrules the defaults
            """
        cfg_file = self._opt.get('--cfg')
        if cfg_file is not None:
            fd = codecs.open(cfg_file, 'r', encoding='utf-8')
            self.readfp(fd)
            fd.close()
            self.__dict__.update(self.config('defaults'))

    def eval_opt(self):
        """ Updates cfg according to options """

        def handle_logfile(val):
            """ transforms logfile argument
                """
            if val is None:
                logf = os.path.splitext(os.path.basename(__file__))[0]
                self.logfile = "%s.log" % logf.lower()
            else:
                self.logfile = val

        self._mapping = {
            '--logfile': lambda val: handle_logfile(val),
        }
        for key, val in self._opt.items():
            if key in self._mapping:
                if isinstance(self._mapping[key], str):
                    self.__dict__[self._mapping[key]] = val
                else:
                    self._mapping[key](val)
                break
            else:
                if val is None:
                    continue
                mat = re.match("\-\-(.*)", key)
                if mat:
                    self.__dict__[mat.group(1)] = val
                else:
                    logging.info("Could not find opt<>cfg mapping for '%s'" % key)

    def set_logging(self):
        """ sets the logging """
        self._logger = logging.getLogger()
        self._logger.setLevel(logging.DEBUG)
        if self.log2stdout:
            hdl = logging.StreamHandler()
            hdl.setLevel(self.loglevel)
            formatter = logging.Formatter(self.logformat)
            hdl.setFormatter(formatter)
            self._logger.addHandler(hdl)
        else:
            hdl = logging.FileHandler(self.logfile)
            hdl.setLevel(self.loglevel)
            formatter = logging.Formatter(self.logformat)
            hdl.setFormatter(formatter)
            self._logger.addHandler(hdl)

    def __str__(self):
        """ print human readble """
        ret = []
        for key, val in self.__dict__.items():
            if not re.match("_.*", key):
                ret.append("%-15s: %s" % (key, val))
        return "\n".join(ret)

    def __getitem__(self, item):
        """ return item from opt or __dict__
        :param item: key to lookup
        :return: value of key
        """
        if item in self.__dict__.keys():
            return self.__dict__[item]
        else:
            return self._opt[item]


class CarbonRelayNG(object):

    def __init__(self, cfg):
        """ intialize """
        self._cfg = cfg

    def run(self):
        """ do stuff """
        if self._cfg['view']:
            self.view()

        elif self._cfg['add']:
            self.add()
        elif self._cfg['enable']:
            self.enable()
        elif self._cfg['disable']:
            self.disable()

    def cmd(self, cmd):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self._cfg['--host'], int(self._cfg['--port'])))
        s.send(cmd)
        data = s.recv(int(self._cfg['--bufsize']))
        s.shutdown(socket.SHUT_RDWR)
        s.close()

        return data

    def parse(self, data):
        """ Parse output of view """
        cfg = {}
        routes_active = False
        rt_rx = re.compile("^##\s+Routes:")
        routes = {}
        rx_route = re.compile("^>\s+(?P<type>\w+)\s+(?P<routeKey>\w+)\s+(?P<filter>.*)\s+")
        rx_dest = re.compile("\s+(?P<dest>[a-z0-9\.\-]+\:\d+)\s+[\/a-z/0-9\-]+\s+(?P<spool>(true|false))\s+(?P<pickle>(true|false))\s+(?P<online>(true|false))")
        for line in data.split("\n"):
            if not routes_active:
                routes_active = re.match(rt_rx, line)
                #print "- %s" % line
            else:
                is_route = re.match(rx_route, line)
                is_dest = re.match(rx_dest, line)
                if is_route:
                    route = is_route.groupdict()
                    if route['routeKey'] not in routes:
                        routes[route['routeKey']] = route
                        routes[route['routeKey']]['destinations'] = []

                elif is_dest:
                    routes[route['routeKey']]['destinations'].append(is_dest.groupdict())
        return routes

    def add(self):
        data = self.cmd("view")
        for key, val in self.parse(data).items():
            if key == self._cfg['<dest>']:
                print "ERROR: '%s' already existent"
                break
        else:
            cmd = "addRoute sendAllMatch '%(<dest>)s'  %(<ip>)s:%(<port>)s" % self._cfg
            print cmd
            self.cmd(cmd)

    def enable(self):
        data = self.cmd("view")
        for key, val in self.parse(data).items():
            if key == self._cfg['<dest>']:
                self.cmd("modRoute %s prefix=" % (key))

    def disable(self):
        data = self.cmd("view")
        for key, val in self.parse(data).items():
            if key == self._cfg['<dest>']:
                self.cmd("modRoute %(<dest>)s prefix=NOWAYTHISMATCHESANYTHING" % self._cfg)


    def view(self):
        data = self.cmd("view")
        header = True
        for key, val in self.parse(data).items():
            if len(val['destinations']) > 0 and header:
                print "%-20s | %-35s | %-20s %-5s %-5s %-5s" % ("key", "filter", "dest", "spool", "pickle", "online")
                header = False
            for dest in val['destinations']:
                dest['key'] = key
                dest['filter'] = val['filter']
                print "%(key)-20s | %(filter)-35s | %(dest)-20s %(spool)-5s %(pickle)-5s %(online)-5s" % dest


def main():
    """ main function """
    options = None
    if HAVE_DOCOPT:
        options = docopt(__doc__, version='0.0.1')
    else:
        print "No python-docopt found..."
    qcfg = QnibConfig(options)
    crng = CarbonRelayNG(qcfg)
    crng.run()


if __name__ == "__main__":
    main()
