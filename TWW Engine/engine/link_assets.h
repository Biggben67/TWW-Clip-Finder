// link_assets.h - Link's model and animations, handed in as the disc's bytes.
//
// The engine ships no game data and reads no file. The skeleton is the INF1 and JNT1 blocks of
// `cl.bdl` in `res/Object/Link.arc`; the animations are the ANK1 blocks of the `.bck` files in
// `res/Object/LkAnm.arc`. The caller reads those files and hands over the bytes.
//
// The parsed tables are process-wide, read through static lookups as the game reads its loaded
// archive. Install once, before the first Session, and never while one is alive.

#ifndef TWW_ENGINE_LINK_ASSETS_H
#define TWW_ENGINE_LINK_ASSETS_H

#include <map>
#include <string>
#include <vector>

#include "dolphin/types.h"
#include "JSystem/J3DGraphAnimator/J3DModelData.h"
#include "JSystem/J3DGraphLoader/J3DJointFactory.h"

struct daPy_portAnmMeta;
struct daPy_portAnmTrack;

namespace tww_engine {

/// Where the files are on the disc, for a consumer that reads them from one.
extern const char* const kLinkModelArchive;      // "res/Object/Link.arc"
extern const char* const kLinkModelFile;         // "cl.bdl"
extern const char* const kLinkAnimationArchive;  // "res/Object/LkAnm.arc"

/// The animation files the engine uses, by file name within `kLinkAnimationArchive`.
std::vector<std::string> linkAnimationFiles();
const char* linkAnimationName(u16 bckIdx);

struct LinkAssets {
    std::vector<u8> model;                                 ///< cl.bdl, decompressed
    std::map<std::string, std::vector<u8>> animations;     ///< "walk.bck" -> its bytes, decompressed
};

/// Parse and install. False, with `why` set and nothing installed, when a file is missing or its
/// bytes are not what the loader expects. A second call replaces the first.
bool installLinkAssets(const LinkAssets& assets, std::string* why);

/// True once `installLinkAssets` has succeeded.
bool linkAssetsInstalled();

/// Link's joint count. The engine is built for his 42 and refuses a model with another.
static const int kLinkJointNum = 42;

/// The installed skeleton, read by engine/link_model.cpp.
struct LinkSkeleton {
    std::vector<J3DModelHierarchy> hierarchy;   ///< INF1's node stream, terminator dropped
    std::vector<J3DJointInitData> joints;       ///< JNT1's rows
    std::vector<u16> index;                     ///< JNT1's index table
    std::vector<u16> visit;                     ///< joints in the order the hierarchy lists them
};
const LinkSkeleton& linkSkeleton();

/// The installed animation for a `dRes_INDEX_LKANM_BCK_*` index, or NULL.
const daPy_portAnmMeta* linkAnimationMeta(u16 bckIdx);
const daPy_portAnmTrack* linkAnimationTrack(u16 bckIdx);
size_t linkAnimationCount();
const daPy_portAnmTrack* linkAnimationTrackAt(size_t i);

}  // namespace tww_engine

#endif  // TWW_ENGINE_LINK_ASSETS_H
