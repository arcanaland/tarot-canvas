#!/bin/bash
set -euo pipefail

pattern='\b(RFC|ADR|TASK)-[0-9]+'

if [ $# -eq 0 ]; then
  source=()
  set -- '*.py' '*.sh' '*.just' 'justfile'
else
  source=(--cached)
fi

if git grep -nE "${source[@]}" "$pattern" -- "$@"; then
  echo "slop detected"
  exit 1
fi
