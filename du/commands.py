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


def is_container_type(type):
    c = type.code
    if c == gdb.TYPE_CODE_TYPEDEF:
        return is_container_type(gdb.types.get_basic_type(type))
    return (c == gdb.TYPE_CODE_STRUCT or c == gdb.TYPE_CODE_UNION)


def is_container(v):
    return is_container_type(v.type)


def is_pointer_type(type):
    if type.code == gdb.TYPE_CODE_TYPEDEF:
        return is_pointer_type(gdb.types.get_basic_type(type))
    return (type.code == gdb.TYPE_CODE_PTR)


def is_pointer(v):
    return is_pointer_type(v.type)


def du_follow_pointer(v, print_level_limit, level_limit, level, visited_ptrs):
    indent = ' ' * level
    try:
        v1 = v.dereference()
        address = str(v1.address)
        if address == '0x0':
            return 0
        if address in visited_ptrs:
            if level < print_level_limit:
                gdb.write(' // visited already\n')
            return 0
        visited_ptrs.append(address)
        v1.fetch_lazy()
    except gdb.error as e:
        if level < print_level_limit:
            gdb.write(', (%s)\n' % e)
        return 0

    if level < print_level_limit:
        gdb.write(' // sizeof: %d\n' % (v1.type.sizeof))
        gdb.write('%s  -> ' % indent)
    size = v1.type.sizeof
    size += du_follow(v1, print_level_limit, level_limit, level + 1, visited_ptrs)
    return size


def du_string(s, print_level_limit, level_limit, level, visited_ptrs):
    indent = ' ' * level

    char_ptr = s['_M_dataplus']['_M_p']
    local_buff_ptr = s['_M_local_buf']
    size=0
    if char_ptr != local_buff_ptr: # see std::string::_M_is_local
        size = s['_M_allocated_capacity']

    if level < print_level_limit:
        if size==0:
            gdb.write('%s %s // stored locally\n' % (s.type, s))
        else:
            gdb.write('%s %s // sizeof: %d\n' % (s.type, s, size))
    return size


def du_follow_std_vector(s, print_level_limit, level_limit, level, visited_ptrs):
    indent = ' ' * level
    if level < print_level_limit:
        gdb.write('%s [' % s.type)

    start = s['_M_impl']['_M_start'].dereference()
    end = s['_M_impl']['_M_finish'].dereference()
    storage_end = s['_M_impl']['_M_end_of_storage'].dereference()

    vec_size = end.address - start.address
    vec_capacity = storage_end.address - start.address
    size = vec_capacity * start.type.sizeof
    if level < print_level_limit:
        gdb.write('%s // vector size: %d, capacity: %d\n' % (indent, vec_size, vec_capacity))

    for i in range(0, vec_size):
        if level < print_level_limit:
            gdb.write('%s %d: ' % (indent, i))
        size += du_follow(s['_M_impl']['_M_start'][i], print_level_limit, level_limit, level+1, visited_ptrs)

    if level < print_level_limit:
        gdb.write('%s],\n' % (indent))
    return size


def du_follow(s, print_level_limit = 3, level_limit = 30, level = 0, visited_ptrs = []):
    indent = ' ' * level

    # TODO: handle s.dynamic_type

    if not is_container(s):
        if level < print_level_limit:
            gdb.write('%s\n' % s)
        return 0

    if level >= level_limit:
        gdb.write("!! limit reached\n")
        return 0 # don't go deeper!

    if level == print_level_limit:
        gdb.write('%s { ... },\n' % s.type) # last level to print

    # known TLS containers
    if str(s.type).startswith('std::vector<'):
        return du_follow_std_vector(s, print_level_limit, level_limit, level, visited_ptrs)

    if str(s.type).startswith('std::string'):
        return du_string(s, print_level_limit, level_limit, level, visited_ptrs)

    # generic container (struct)
    if level < print_level_limit:
        gdb.write('%s {\n' % s.type)

    size = 0
    for k in s.type.fields():
        v = s[k]
        if is_pointer(v):
            if level < print_level_limit:
                gdb.write('%s %s: %s' % (indent, k.name, v))
            size += du_follow_pointer(v, print_level_limit, level_limit, level, visited_ptrs)
        elif is_container(v):
            if level < print_level_limit:
                gdb.write('%s %s: ' % (indent, k.name))
            size += du_follow(v, print_level_limit, level_limit, level + 1, visited_ptrs)
        else:
            if level < print_level_limit:
                gdb.write('%s %s: %s,\n' % (indent, k.name, v))
    if level < print_level_limit:
        gdb.write('%s},\n' % (indent))
    return size


# Inspired by:
#   https://stackoverflow.com/questions/16787289/gdb-python-parsing-structures-each-field-and-print-them-with-proper-value-if
# gdb api documentation:
#   https://sourceware.org/gdb/onlinedocs/gdb/gdb_002etypes.html
#   https://sourceware.org/gdb/onlinedocs/gdb/Types-In-Python.html#Types-In-Python
class Du(gdb.Command):
    '''
    du [/PRINT_LEVEL_LIMIT] STRUCT-VALUE
    '''
    def __init__(self):
        super(Du, self).__init__(
            'du',
            gdb.COMMAND_DATA, gdb.COMPLETE_SYMBOL, False)

    def invoke(self, args, from_tty):
        arg_list = gdb.string_to_argv(args)
        if len(arg_list) < 1:
            gdb.write("Too few arguments\n")
        s = args.find('/')
        if s == -1:
            (expr, limit) = (args, 3)
        else:
            if args[:s].strip():
                (expr, limit) = (args, 3)
            else:
                i = s + 1
                for (i, c) in enumerate(args[s+1:], s + 1):
                    if not c.isdigit():
                        break
                end = i
                digits = args[s+1:end]
                try:
                    limit = int(digits)
                except ValueError:
                    raise gdb.GdbError(Du.__doc__)
                (expr, limit) = (args[end:], limit)
        try:
            v = gdb.parse_and_eval(expr)
        except gdb.error as e:
            raise gdb.GdbError(e)

        gdb.write('// sizeof: %d\n' % (v.type.sizeof))
        size = v.type.sizeof
        size += du_follow(v, limit, max(limit, 64), 0, [])
        gdb.write("size: %s\n" % size)


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


def register_commands():
   Hexdump()
   Du()

