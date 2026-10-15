#!/usr/bin/env bash
# Build and run the suite with gcc or clang, from PowerShell (Git Bash mangles /mnt/c paths):
#   wsl -d Ubuntu bash /mnt/c/.../tww_engine/build_linux.sh
#   CXX=clang++ bash build_linux.sh
# gcc and clang agreeing to the bit is the check that neither contracts.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cxx="${CXX:-g++}"
out="$here/build-linux-$(basename "$cxx")"
cmake -S "$here" -B "$out" -DCMAKE_BUILD_TYPE=RelWithDebInfo -DCMAKE_CXX_COMPILER="$cxx" >/dev/null
cmake --build "$out" -j"$(nproc)" >/dev/null
"$out/tests/tww_engine_tests" "$@"
