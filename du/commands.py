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
import argparse


class DuArgs:
    def __init__(self):
        self.print_level_limit = 3
        self.level_limit = 30
        self.follow_static = False


from du import fmt_size, fmt_addr, \
    hexdump_as_bytes


def is_container_type(type):
    c = type.code
    if c == gdb.TYPE_CODE_TYPEDEF:
        return is_container_type(gdb.types.get_basic_type(type))
    return (c == gdb.TYPE_CODE_STRUCT or c == gdb.TYPE_CODE_UNION)


def is_container(v):
    return is_container_type(v.type)


def is_pointer(v):
    return (v.type.strip_typedefs().code == gdb.TYPE_CODE_PTR)


def get_typedef(type, typeName):
    if str(type).startswith(typeName):
        return type
    if type.code == gdb.TYPE_CODE_TYPEDEF:
        return get_typedef(gdb.types.get_basic_type(type), typeName)
    return None


def du_follow_pointer(v, level, du_args, visited_ptrs):
    indent = ' ' * level
    try:
        v1 = v.dereference()
        address = str(v1.address)
        if address == '0x0':
            return 0
        if address in visited_ptrs:
            if level < du_args.print_level_limit:
                gdb.write(' // visited already\n')
            return 0
        visited_ptrs.append(address)
        v1.fetch_lazy()
    except gdb.error as e:
        if level < du_args.print_level_limit:
            gdb.write(', (%s)\n' % e)
        return 0

    if level < du_args.print_level_limit:
        gdb.write(' // sizeof: %d\n' % (v1.type.sizeof))
        gdb.write('%s  -> ' % indent)
    size = v1.type.sizeof
    size += du_follow(v1, level + 1, du_args, visited_ptrs)
    return size


def du_string(s, level, du_args, visited_ptrs):
    indent = ' ' * level

    char_ptr = s['_M_dataplus']['_M_p']
    local_buff_ptr = s['_M_local_buf']
    size=0
    if char_ptr != local_buff_ptr: # see std::string::_M_is_local
        size = s['_M_allocated_capacity']

    if level < du_args.print_level_limit:
        if size==0:
            gdb.write('%s %s // stored locally\n' % (s.type, s))
        else:
            gdb.write('%s %s // sizeof: %d\n' % (s.type, s, size))
    return size


def du_qt_array_data(s, element_type, level, du_args, visited_ptrs):
    indent = ' ' * level
    if level < du_args.print_level_limit:
        gdb.write('%s [' % s.type)

    header_size = s.type.sizeof
    offset = s['offset']
    alloc = s['alloc']
    array_size = s['size']

    # header size is counted already...
    size = offset - header_size + alloc * element_type.sizeof

    char_pt = gdb.lookup_type('char').pointer()
    arr = (s.cast(char_pt) + offset).cast(element_type.pointer())

    if level < du_args.print_level_limit:
        gdb.write(' // %d elements of %s, extra size: %s\n' % (array_size, element_type, size))

    for i in range(0, array_size):
        if level < du_args.print_level_limit:
            gdb.write('%s %d: ' % (indent, i))

        entry = arr[i]
        address = str(entry.address)
        if address in visited_ptrs:
            if level < du_args.print_level_limit:
                gdb.write(' %s // visited already\n' % address)
            size -= entry.type.sizeof
            continue
        # gdb.write('%s ' % (address))
        visited_ptrs.append(address)
        size += du_follow(entry, level+1, du_args, visited_ptrs)


    if level < du_args.print_level_limit:
        gdb.write('%s],\n' % (indent))
    return size


def du_follow_std_vector(s, level, du_args, visited_ptrs):
    indent = ' ' * level
    if level < du_args.print_level_limit:
        gdb.write('%s [' % s.type)

    start = s['_M_impl']['_M_start'].dereference()
    end = s['_M_impl']['_M_finish'].dereference()
    storage_end = s['_M_impl']['_M_end_of_storage'].dereference()

    vec_size = end.address - start.address
    vec_capacity = storage_end.address - start.address
    size = vec_capacity * start.type.sizeof
    if level < du_args.print_level_limit:
        gdb.write('%s // vector size: %d, capacity: %d\n' % (indent, vec_size, vec_capacity))

    for i in range(0, vec_size):
        if level < du_args.print_level_limit:
            gdb.write('%s %d: ' % (indent, i))
        entry = s['_M_impl']['_M_start'][i]
        address = str(entry.address)
        if address in visited_ptrs:
            if level < du_args.print_level_limit:
                gdb.write(' %s // visited already\n' % address)
            size -= entry.type.sizeof
            continue
        # gdb.write('%s ' % (address))
        visited_ptrs.append(address)
        size += du_follow(entry, du_args.print_level_limit, level_limit, level+1, visited_ptrs)

    if level < du_args.print_level_limit:
        gdb.write('%s],\n' % (indent))
    return size


def du_follow(s, level = 0, du_args = DuArgs, visited_ptrs = []):
    indent = ' ' * level

    # TODO: handle s.dynamic_type

    if not is_container(s):
        if level < du_args.print_level_limit:
            gdb.write('%s\n' % s)
        return 0

    if level >= du_args.level_limit:
        gdb.write("!! limit reached\n")
        return 0 # don't go deeper!

    if level == du_args.print_level_limit:
        gdb.write('%s { ... },\n' % s.type) # last level to print

    # known TLS containers
    if get_typedef(s.type, 'std::vector') is not None:
        return du_follow_std_vector(s, level, du_args, visited_ptrs)

    if get_typedef(s.type, 'std::string') is not None:
        return du_string(s, level, du_args, visited_ptrs)

    # Qt classes
    qtTypedArrayData = get_typedef(s.type, 'QTypedArrayData')
    if qtTypedArrayData is not None:
        element_type = qtTypedArrayData.template_argument(0)
        return du_qt_array_data(s, element_type, level, du_args, visited_ptrs)

    qtArrayData = get_typedef(s.type, 'QArrayData')
    if qtArrayData is not None:
        # not sure...
        element_type = gdb.lookup_type('char')
        return du_qt_array_data(s, element_type, level, du_args, visited_ptrs)

    # generic container (struct)
    if level < du_args.print_level_limit:
        gdb.write('%s {\n' % s.type)

    size = 0
    for k in s.type.fields():
        v = s[k]
        if is_pointer(v):
            if level < du_args.print_level_limit:
                gdb.write('%s %s: %s' % (indent, k.name, v))
            size += du_follow_pointer(v, level, du_args, visited_ptrs)
        elif hasattr(k, 'enumval'):
            if level < du_args.print_level_limit:
                gdb.write('%s %s: %s, // enumval\n' % (indent, k.name, v))
        elif not hasattr(k, 'bitpos'): # static
            if level < du_args.print_level_limit:
                gdb.write('%s static %s: %s\n' % (indent, k.name, v))
            if v.address is not None and du_args.follow_static:
                size += du_follow_pointer(v.address, level, du_args, visited_ptrs)
        elif is_container(v):
            if level < du_args.print_level_limit:
                gdb.write('%s %s: ' % (indent, k.name))
            size += du_follow(v, level + 1, du_args, visited_ptrs)
        else:
            if level < du_args.print_level_limit:
                gdb.write('%s %s: %s,\n' % (indent, k.name, v))
    if level < du_args.print_level_limit:
        gdb.write('%s},\n' % (indent))
    return size


class ErrorCatchingArgumentParser(argparse.ArgumentParser):
    def exit(self, status=0, message=None):
        raise Exception('%s' % (message))


# Inspired by:
#   https://stackoverflow.com/questions/16787289/gdb-python-parsing-structures-each-field-and-print-them-with-proper-value-if
# gdb api documentation:
#   https://sourceware.org/gdb/onlinedocs/gdb/gdb_002etypes.html
#   https://sourceware.org/gdb/onlinedocs/gdb/Types-In-Python.html#Types-In-Python
class Du(gdb.Command):
    '''
    du [-d PRINT_LEVEL_LIMIT] STRUCT-VALUE
    '''
    def __init__(self):
        super(Du, self).__init__(
            'du',
            gdb.COMMAND_DATA, gdb.COMPLETE_SYMBOL, False)

    def invoke(self, args, from_tty):
        arg_list = gdb.string_to_argv(args)
        if len(arg_list) < 1:
            gdb.write("Too few arguments\n")

        parser = ErrorCatchingArgumentParser(description='Compute memory size of structure.')

        parser.add_argument('-p', '--print-depth=', dest='print_depth', type=int, default=3,
                            help='print depth (default: 3)')
        parser.add_argument('-c', '--compute-depth=', dest='compute_depth', type=int, default=1024,
                            help='compute depth (default: 1024)')
        parser.add_argument('-s', '--static', dest='follow_static', default=False, action='store_true',
                            help='follow static fields (default is false)')
        parser.add_argument('expression', metavar='expr', type=str, nargs='+',
                            help='gdb expression (variable)')

        try:
            pargs = parser.parse_args(arg_list)
        except Exception:
            return

        for expr in pargs.expression:
            try:
                v = gdb.parse_and_eval(expr)
            except gdb.error as e:
                raise gdb.GdbError(e)

            gdb.write('// sizeof(%s): %d\n' % (expr, v.type.sizeof))
            size = v.type.sizeof

            du_args = DuArgs
            du_args.print_level_limit = pargs.print_depth
            du_args.level_limit = pargs.compute_depth
            du_args.follow_static = pargs.follow_static
            size += du_follow(v, 0, du_args, [])
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
            chars_only = True if args[0] == '-c' else False
            addr_arg = arg_list[1]
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

