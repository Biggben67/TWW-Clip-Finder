// jma_console_table.cpp - written, not copied: installs the console's sine table.
//
// The game builds it at boot with JMANewSinTable(12) (m_Do_machine.cpp:614) from libm. Compiled
// here, that builder disagrees with console RAM on 2,964 of the 4,096 cosine entries, so the
// table dumped from a running console is installed bit for bit instead. JMANewSinTable stays
// ported, called only by the test that reports the disagreement.

#include <cstring>

#include "JSystem/JMath/JMATrigonometric.h"
#include "JSystem/JMath/jma_sin_table.inc"

static f32 s_console_sin_table[sizeof(jma_console_sin_bits) / sizeof(jma_console_sin_bits[0])];

/// Stands in for JMANewSinTable(12): sets jmaSinShift (`16 - numBits`), jmaSinTable and
/// jmaCosTable as it would.
void JMA_useConsoleSinTable() {
    const int n = (int)(sizeof(jma_console_sin_bits) / sizeof(jma_console_sin_bits[0]));
    for (int i = 0; i < n; i++) {
        std::memcpy(&s_console_sin_table[i], &jma_console_sin_bits[i], 4);
    }
    jmaSinShift = 16 - 12;                      // JMANewSinTable(12), m_Do_machine.cpp:614
    jmaSinTable = s_console_sin_table;
    jmaCosTable = s_console_sin_table + (4096 / 4);   // JMath.cpp:36, the quarter-turn view
}
