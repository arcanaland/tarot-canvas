#!/usr/bin/env python3
"""Print the dependencies a pyproject.toml pins to one version (`name==X`)."""

import re
import sys
import tomllib


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: pinned-deps.py FILE")
    with open(sys.argv[1], "rb") as f:
        deps = tomllib.load(f)["project"]["dependencies"]
    pinned = set()
    for dep in deps:
        spec = dep.split(";")[0]
        if "==" in spec:
            pinned.add(re.sub(r"[_.]", "-", spec.split("==")[0].strip().lower()))
    for name in sorted(pinned):
        print(name)


if __name__ == "__main__":
    main()
