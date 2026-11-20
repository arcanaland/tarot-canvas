#!/bin/bash
# The Python distributions a python3-modules.yaml downloads, one per line, sorted.
#
#   ./module-deps.sh FILE                print the set
#   ./module-deps.sh --blocks FILE NAME…   print the module blocks that download NAME…

set -euo pipefail

# Shared by both modes
NAME_OF_URL='
  function dist(line,   u) {
    u = line
    sub(/^[[:space:]]*url:[[:space:]]*/, "", u)
    sub(/[[:space:]].*$/, "", u)
    sub(/.*\//, "", u)
    if (u ~ /\.whl$/) {
      sub(/-.*/, "", u)
    } else {
      sub(/\.(tar\.gz|zip)$/, "", u)
      sub(/-[0-9].*/, "", u)
    }
    u = tolower(u)
    gsub(/[_.]/, "-", u)
    return u
  }
'

if [ "${1:-}" = "--blocks" ]; then
  FILE="${2:?usage: module-deps.sh --blocks FILE NAME...}"
  shift 2
  # A block starts at a module's `  - name:` and runs to the next one
  awk -v wanted="$*" "${NAME_OF_URL}"'
    BEGIN { split(wanted, w, " "); for (i in w) want[w[i]] = 1 }
    function flush() { if (hit) printf "%s", block; block = ""; hit = 0 }
    /^  - name: / { flush() }
    /^[[:space:]]*url:/ && (dist($0) in want) { hit = 1 }
    { block = block $0 "\n" }
    END { flush() }
  ' "${FILE}"
  exit 0
fi

FILE="${1:?usage: module-deps.sh FILE}"

names=$(awk "${NAME_OF_URL}"'
  /^[[:space:]]*url:/ { print dist($0) }
' "${FILE}")
if [ -z "${names}" ]; then
  echo "module-deps.sh: no url: lines in ${FILE}" >&2
  exit 1
fi
printf '%s\n' "${names}" | sort -u
