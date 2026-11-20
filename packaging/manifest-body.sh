#!/bin/bash
# Print a Flatpak manifest's body

set -euo pipefail

FILE="${1:?usage: manifest-body.sh FILE}"

awk '
  $0 == "    sources:" { n++; done = 1; next }
  !done { body = body $0 "\n" }
  END {
    if (n != 1) {
      printf "manifest-body.sh: expected one \"    sources:\" line, found %d\n", n > "/dev/stderr"
      exit 1
    }
    printf "%s", body
  }
' "${FILE}"
