// link_disc.h - the suite's reader for Link's files, off a GameCube disc image.
//
// The engine reads no file (engine/link_assets.h); this is where the suite does. The image's path
// is the first line of the gitignored `tests/iso.txt`. Without it the suite does not run.

#ifndef TWW_ENGINE_TESTS_LINK_DISC_H
#define TWW_ENGINE_TESTS_LINK_DISC_H

#include <string>

#include "engine/link_assets.h"

namespace tww_engine {
namespace testing {

/// Where the suite looks for the image's path.
std::string iso_path_file();

/// Read `tests/iso.txt`, open the image it names and fill `out`. False, with `why`, otherwise.
bool read_link_assets(LinkAssets* out, std::string* why);

}  // namespace testing
}  // namespace tww_engine

#endif  // TWW_ENGINE_TESTS_LINK_DISC_H
