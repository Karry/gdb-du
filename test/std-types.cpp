// Copyright (C) 2021  Lukas Karas
//
// This library is free software; you can redistribute it and/or
// modify it under the terms of the GNU Lesser General Public
// License as published by the Free Software Foundation; either
// version 2.1 of the License, or (at your option) any later version.
//
// This library is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
// Lesser General Public License for more details.
//
// You should have received a copy of the GNU Lesser General Public
// License along with this library; if not, write to the Free Software
// Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

#include <optional>
#include <string>
#include <vector>
#include <set>
#include <map>
#include <iostream>

#ifdef __GNUC__
#include <malloc.h>
#endif

struct Dummy {
  std::optional<long> opt;
  std::string str;
  std::set<long> set;
  std::map<std::string, std::string> stringMap;
  Dummy *ptr = nullptr;
};

void stat() {
#ifdef __GNUC__
  auto info = mallinfo();
  std::cout << "allocated: " << info.uordblks << std::endl;
#endif
}

int main() {
  std::vector<Dummy> vec;

  for (size_t i=0; i<10; i++){
    stat();

    vec.emplace_back();
    vec.back().opt = 42;
    vec.back().str = i % 2 == 0 ? "some text" : "some text that cannot be stored locally";
    vec.back().set = {1,2,3,4,5,6,7,8,9,10};
    vec.back().stringMap["key1"] = "value1";
    vec.back().stringMap["key2"] = "value2";
    if (i>0) {
      // avoid future re-allocations
      vec.reserve(10);
      // store pointer to previous entry
      vec.back().ptr = &vec[i-1];
    }

    stat();
  }
  return 0;
}
