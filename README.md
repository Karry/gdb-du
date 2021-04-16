# gdb-du
Recursive sizeof for gdb, supporting basic C++ containers (some gnu libstdc++ containers, c++17 abi). 

**It is PoC right now, just basic structures, pointers, `std::vector` and `std::string` is supported!**

When pointer structure are not linear, it is easy to count some structure twice,
moreover custom types with dynamic allocations are not supported. 
So, keep in mind that provided values are just estimations.

Inspired by [gdb-heap](https://github.com/rogerhu/gdb-heap) project.

## Example

### Build test program

```bash
make -C test
```

### Sample output

```gdb
./run-gdb-du ./test/std-types
...
(gdb) break std-types.cpp:36
Breakpoint 3 at 0x555555556563: file std-types.cpp, line 36.
(gdb) run
Starting program: /home/karry/Avast/projects/skyline/gdb-du/test/std-types 

Breakpoint 3, main () at std-types.cpp:51
36          vec.back().opt = 42;
(gdb) du /1 vec
// sizeof: 24
std::vector<Dummy, std::allocator<Dummy> > [ // vector size: 1, capacity: 1
 0: Dummy { ... },
],
size: 241
```

## Commands

```gdb
hexdump <addr> [-c] - print a hexdump, starting at the specific region of memory (expose hex characters with -c option)
du [/PRINT_LEVEL_LIMIT] variable - print recursive variable size
```
