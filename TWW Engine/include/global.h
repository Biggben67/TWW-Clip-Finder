// Generated from the zeldaret/tww decomp. Do not hand-edit.
// global.h - ARRAY_SIZE, SQUARE and the VERSION macros (global.h:6, 31, 57-74).
// VERSION is set by the build: 1 = GZLJ01, 2 = GZLE01, 3 = GZLP01.

#ifndef TWW_PORT_GLOBAL_H
#define TWW_PORT_GLOBAL_H

#ifndef VERSION
#error "VERSION is not set. Build with -DVERSION=1 for GZLJ01."
#endif

#define ARRAY_SIZE(o) (sizeof(o) / sizeof(o[0]))

#define SQUARE(x) ((x) * (x))

#define VERSION_DEMO 0
#define VERSION_JPN 1
#define VERSION_USA 2
#define VERSION_PAL 3

#if VERSION == VERSION_DEMO
    #define VERSION_SELECT(DEMO, JPN, USA, PAL) (DEMO)
    #define DEMO_SELECT(DEMO, RETAIL) (DEMO)
#elif VERSION <= VERSION_JPN
    #define VERSION_SELECT(DEMO, JPN, USA, PAL) (JPN)
    #define DEMO_SELECT(DEMO, RETAIL) (RETAIL)
#elif VERSION == VERSION_USA
    #define VERSION_SELECT(DEMO, JPN, USA, PAL) (USA)
    #define DEMO_SELECT(DEMO, RETAIL) (RETAIL)
#elif VERSION == VERSION_PAL
    #define VERSION_SELECT(DEMO, JPN, USA, PAL) (PAL)
    #define DEMO_SELECT(DEMO, RETAIL) (RETAIL)
#endif

#endif
