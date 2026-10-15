#include "link_disc.h"

#if !defined(_WIN32)
#include <sys/types.h>
#endif

#include <cstdio>
#include <fstream>
#include <vector>

namespace tww_engine {
namespace testing {
namespace {

u32 be32(const u8* p) {
    return (static_cast<u32>(p[0]) << 24) | (static_cast<u32>(p[1]) << 16) |
           (static_cast<u32>(p[2]) << 8) | static_cast<u32>(p[3]);
}

u16 be16(const u8* p) { return static_cast<u16>((p[0] << 8) | p[1]); }

char lower(char c) { return (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : c; }

bool same(const std::string& a, const std::string& b) {
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); i++) {
        if (lower(a[i]) != lower(b[i])) return false;
    }
    return true;
}

bool read_at(std::FILE* f, unsigned long long at, void* dst, size_t n) {
#if defined(_WIN32)
    if (_fseeki64(f, static_cast<long long>(at), SEEK_SET) != 0) return false;
#else
    if (fseeko(f, static_cast<off_t>(at), SEEK_SET) != 0) return false;
#endif
    return std::fread(dst, 1, n, f) == n;
}

/// One file's bytes, by its whole path on the disc. The file system table is walked flat: a
/// directory record carries the index one past its last child.
bool disc_file(std::FILE* f, const std::string& path, std::vector<u8>* out) {
    u8 hdr[8];
    if (!read_at(f, 0x424, hdr, sizeof hdr)) return false;
    const u32 at = be32(hdr), size = be32(hdr + 4);
    if (size < 12 || size > 16u * 1024u * 1024u) return false;
    std::vector<u8> t(size);
    if (!read_at(f, at, t.data(), t.size())) return false;
    const u32 records = be32(&t[8]);
    const size_t strings = static_cast<size_t>(records) * 12;
    if (records == 0 || strings > t.size()) return false;

    std::vector<std::string> dirs;
    std::vector<u32> ends;
    for (u32 i = 1; i < records; i++) {
        while (!ends.empty() && ends.back() <= i) {
            ends.pop_back();
            dirs.pop_back();
        }
        const u8* r = &t[static_cast<size_t>(i) * 12];
        std::string name;
        for (size_t k = strings + (be32(r) & 0xFFFFFF); k < t.size() && t[k] != 0; k++) {
            name.push_back(static_cast<char>(t[k]));
        }
        if (r[0] == 1) {
            dirs.push_back(name);
            ends.push_back(be32(r + 8));
            continue;
        }
        std::string whole;
        for (size_t d = 0; d < dirs.size(); d++) whole += dirs[d] + "/";
        whole += name;
        if (!same(whole, path)) continue;
        out->resize(be32(r + 8));
        return read_at(f, be32(r + 4), out->data(), out->size());
    }
    return false;
}

bool yaz0(const std::vector<u8>& src, std::vector<u8>* dst) {
    if (src.size() < 4 || src[0] != 'Y' || src[1] != 'a' || src[2] != 'z' || src[3] != '0') {
        *dst = src;
        return true;
    }
    if (src.size() < 16) return false;
    const u32 want = be32(&src[4]);
    if (want > 64u * 1024u * 1024u) return false;
    dst->clear();
    dst->reserve(want);
    size_t p = 16;
    while (dst->size() < want) {
        if (p >= src.size()) return false;
        const u8 code = src[p++];
        for (int i = 0; i < 8 && dst->size() < want; i++) {
            if (code & (0x80 >> i)) {
                if (p >= src.size()) return false;
                dst->push_back(src[p++]);
                continue;
            }
            if (p + 1 >= src.size()) return false;
            const u8 b1 = src[p], b2 = src[p + 1];
            p += 2;
            const size_t dist = (static_cast<size_t>(b1 & 0x0F) << 8) | b2;
            size_t count = b1 >> 4;
            if (count == 0) {
                if (p >= src.size()) return false;
                count = static_cast<size_t>(src[p++]) + 0x12;
            } else {
                count += 2;
            }
            if (dist + 1 > dst->size()) return false;
            size_t r = dst->size() - dist - 1;
            for (size_t k = 0; k < count; k++) dst->push_back((*dst)[r++]);
        }
    }
    return true;
}

/// Every file in a RARC, by name and decompressed. Directory entries (index 0xFFFF) are skipped.
bool rarc_files(const std::vector<u8>& packed, std::map<std::string, std::vector<u8> >* out) {
    std::vector<u8> b;
    if (!yaz0(packed, &b) || b.size() < 0x20) return false;
    if (b[0] != 'R' || b[1] != 'A' || b[2] != 'R' || b[3] != 'C') return false;
    const size_t info = be32(&b[0x08]);
    const size_t data = be32(&b[0x0C]);
    if (info + 0x18 > b.size()) return false;
    const u32 files = be32(&b[info + 0x08]);
    const size_t table = info + be32(&b[info + 0x0C]);
    const size_t strings = info + be32(&b[info + 0x14]);
    if (table + static_cast<size_t>(files) * 0x14 > b.size()) return false;
    for (u32 i = 0; i < files; i++) {
        const u8* e = &b[table + static_cast<size_t>(i) * 0x14];
        if (be16(e) == 0xFFFF) continue;
        std::string name;
        for (size_t k = strings + (be32(e + 4) & 0xFFFFFF); k < b.size() && b[k] != 0; k++) {
            name.push_back(static_cast<char>(b[k]));
        }
        const size_t at = 0x20 + data + be32(e + 8);
        const size_t size = be32(e + 12);
        if (at > b.size() || size > b.size() - at) return false;
        // A file inside the archive may be compressed on its own; LkAnm.arc's .bck files are.
        const std::vector<u8> packedFile(b.begin() + static_cast<long long>(at),
                                         b.begin() + static_cast<long long>(at + size));
        if (!yaz0(packedFile, &(*out)[name])) return false;
    }
    return true;
}

}  // namespace

std::string iso_path_file() { return std::string(TWWE_REPO_ROOT) + "/tests/iso.txt"; }

bool read_link_assets(LinkAssets* out, std::string* why) {
    std::ifstream named(iso_path_file().c_str());
    std::string path;
    if (!named || !std::getline(named, path)) {
        *why = "no " + iso_path_file() + " naming a disc image";
        return false;
    }
    while (!path.empty() && (path.back() == '\r' || path.back() == ' ')) path.pop_back();

    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (f == NULL) {
        *why = "could not open " + path;
        return false;
    }
    std::vector<u8> arc;
    std::map<std::string, std::vector<u8> > model, anims;
    const bool ok = disc_file(f, kLinkModelArchive, &arc) &&
                    rarc_files(arc, &model) &&
                    disc_file(f, kLinkAnimationArchive, &arc) &&
                    rarc_files(arc, &anims);
    std::fclose(f);
    if (!ok) {
        *why = path + " has no readable Link.arc and LkAnm.arc";
        return false;
    }
    const std::map<std::string, std::vector<u8> >::const_iterator m = model.find(kLinkModelFile);
    if (m == model.end()) {
        *why = std::string(kLinkModelArchive) + " has no " + kLinkModelFile;
        return false;
    }
    out->model = m->second;
    out->animations.swap(anims);
    return true;
}

}  // namespace testing
}  // namespace tww_engine
