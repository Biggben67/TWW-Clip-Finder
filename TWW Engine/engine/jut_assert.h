// jut_assert.h - JUT_ASSERT(<line>, <condition>) for copied bodies (e.g.
// cBgS_PolyInfo::SetPolyIndex). The console halts on a failure, so this aborts; the decomp's
// line argument is printed in hex. Port runtime, not a copy of the decomp's JUTAssert.h.

#ifndef TWW_PORT_JUT_ASSERT_H
#define TWW_PORT_JUT_ASSERT_H

#include <cstdio>
#include <cstdlib>

#define JUT_ASSERT(line, cond)                                                                  \
    do {                                                                                        \
        if (!(cond)) {                                                                          \
            std::fprintf(stderr, "JUT_ASSERT failed: %s (%s, decomp line %#x)\n",               \
                         #cond, __FILE__, (unsigned)(line));                                    \
            std::abort();                                                                       \
        }                                                                                       \
    } while (0)

#endif
