# Copyright (C) 2021  Lukas Karas
# Copyright (C) 2010  David Hugh Malcolm
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

import gdb
import re
import sys

from du import fmt_size, fmt_addr, \
    hexdump_as_bytes


class Hexdump(gdb.Command):
    'Print a hexdump, starting at the specific region of memory'
    def __init__(self):
        gdb.Command.__init__ (self,
                              "hexdump",
                              gdb.COMMAND_DATA)

    def invoke(self, args, from_tty):
        print(repr(args))
        arg_list = gdb.string_to_argv(args)

        chars_only = True

        if len(arg_list) == 2:
            addr_arg = arg_list[0]
            chars_only = True if args[1] == '-c' else False
        else:
            addr_arg = args

        if addr_arg.startswith('0x'):
            addr = int(addr_arg, 16)
        else:
            addr = int(addr_arg)

        # assume that paging will cut in and the user will quit at some point:
        size = 32
        while True:
            hd = hexdump_as_bytes(addr, size, chars_only=chars_only)
            print ('%s -> %s %s' % (fmt_addr(addr), fmt_addr(addr + size -1), hd))
            addr += size


class Du(gdb.Command):
    'Print a hexdump, starting at the specific region of memory'
    def __init__(self):
        gdb.Command.__init__ (self,
                              "du",
                              gdb.COMMAND_DATA)

    def invoke(self, args, from_tty):
        # print(repr(args))
        arg_list = gdb.string_to_argv(args)

        if len(arg_list) < 1:
            print("Too few arguments")


def register_commands():
   Hexdump()
   Du()
