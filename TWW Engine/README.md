# tww_engine

Link's player physics from The Legend of Zelda: The Wind Waker, in C++. The code is ported from
the [zeldaret/tww](https://github.com/zeldaret/tww) decompilation.

## Using it

    add_subdirectory(tww_engine)
    target_link_libraries(your_target PRIVATE tww_engine_port)

`find_package(tww_engine)` works too, after `cmake --install`.

```cpp
#include "engine/link_assets.h"
#include "engine/session.h"

tww_engine::LinkAssets assets = read_from_disc();   // yours
std::string why;
if (!tww_engine::installLinkAssets(assets, &why)) return fail(why);

tww_engine::Init init;
init.pos = {100.0f, 0.0f, -250.0f};
init.shape_angle_y = 0x4000;

tww_engine::RoomDzb room = read_room();              // yours
tww_engine::Session session(init, &room);

tww_engine::Pad pad;
pad.target_angle = 0x4000;
pad.stick_distance = 1.0f;
for (int frame = 0; frame < 30; ++frame) session.step(pad);

const cXyz& where = session.state().current.pos;
```

Install the assets once, before the first `Session`. A `Session` must not be copied or moved; to
branch, build another from the same `Init`.

## The floating-point contract

The game's arithmetic is single precision, fused only where the game's own code fuses. A compiler
that contracts a multiply and an add into one instruction changes the result without a warning,
so the build sets `/fp:precise` (MSVC) or `-ffp-contract=off` (gcc, clang). It passes the same flag
to code that links the library, because the positions you hand it must be computed the same way.
Any other compiler is refused at configure time.

## Building and tests

    build.bat              # Windows, Visual Studio 2022
    ./build_linux.sh       # Linux, gcc or clang (CXX=clang++)

Both configure, build and run the suite. The tests read a disc image from the path in
`tests/iso.txt`. They compare against recorded results that are not published, so on a fresh clone
the suite reports that it skipped.

## Layout

| Folder | What it is |
|---|---|
| `src/`, `include/` | Code copied from the decompilation, at its own paths |
| `generated/` | Tables extracted from the decompilation, and constants from the game's executable |
| `engine/` | This library's own code: `Session`, the room, the asset loader, the Gekko float helpers |
| `boundary/` | Stand-ins for the parts of the game outside the player |
| `tests/` | The suite |

## License

MIT; see [LICENSE](LICENSE). Derived from the zeldaret/tww decompilation (CC0); see
[NOTICE](NOTICE).
