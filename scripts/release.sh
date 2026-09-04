#!/usr/bin/env bash
set -e

# Two-phase release.
#
#   ./scripts/release.sh prepare X.Y.Z   bump the version, then stop
#   <hand-author the <release> entry in the appdata XML>
#   ./scripts/release.sh tag             check the notes, commit, tag
#   ./scripts/release.sh push            push branch + tag together
#
# The split exists because release notes are prose: they are written by hand, in
# the branch, and reviewed in the PR diff like everything else. This script never
# authors them -- it only refuses to tag a release that has none.

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

APPDATA="packaging/land.arcana.TarotCanvas.appdata.xml"
VERSION_FILE="tarot_canvas/_version.py"

die() {
  echo -e "${RED}== $1${NC}" >&2
  exit 1
}

usage() {
  cat <<'EOF'
usage: release.sh prepare [X.Y.Z]   bump pyproject.toml + _version.py, then stop
       release.sh tag               validate notes, commit the bump, create the tag
       release.sh push              push the branch and the tag, atomically

Between the two, add a <release> entry for the new version to
packaging/land.arcana.TarotCanvas.appdata.xml. The template is in an XML comment
at the top of the <releases> block.
EOF
}

# Pull the <release> element for a given version out of the appdata file.
release_block() {
  awk -v ver="$1" '
    $0 ~ "<release[^>]*version=\"" ver "\"" { inblock = 1 }
    inblock { print }
    inblock && /<\/release>/ { exit }
  ' "$APPDATA"
}

require_repo_root() {
  [ -f "$APPDATA" ] || die "run this from the repository root ($APPDATA not found)"
}

# The release branch must contain everything on the remote. If it does not, the
# tag we are about to create sits on a commit that will be rewritten by the
# rebase, and a pushed tag would be stranded off origin/main forever.
require_up_to_date() {
  BRANCH=$(git rev-parse --abbrev-ref HEAD)
  [ "$BRANCH" != "HEAD" ] || die "detached HEAD -- check out the release branch first."

  echo "== fetching origin..."
  git fetch --quiet origin || die "could not fetch origin."

  UPSTREAM="origin/$BRANCH"
  if ! git rev-parse --verify --quiet "$UPSTREAM" >/dev/null; then
    echo -e "${YELLOW}== note: no $UPSTREAM yet, nothing to be behind${NC}"
    return
  fi

  BEHIND=$(git rev-list --count "HEAD..$UPSTREAM")
  if [ "$BEHIND" -ne 0 ]; then
    die "$BRANCH is behind $UPSTREAM by $BEHIND commit(s).
   Something landed on the remote since you started this release.
   Rebase onto it and start the release over from 'prepare':

       git rebase $UPSTREAM

   Do not tag or push until this branch contains $UPSTREAM."
  fi
}

# ---------------------------------------------------------------- prepare ----

phase_prepare() {
  require_repo_root

  if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo -e "${YELLOW}== warning: working directory is not clean${NC}"
    git status --short --untracked-files=no
    echo -n "Continue anyway? (y/N): "
    read -r CONTINUE
    if [ "$CONTINUE" != "y" ] && [ "$CONTINUE" != "Y" ]; then
      die "aborted."
    fi
  fi

  CURRENT_VERSION=$(uv version --short)
  echo -e "== current version: ${YELLOW}$CURRENT_VERSION${NC}"

  if [ -z "${1:-}" ]; then
    echo -n "Enter new version (or press Enter to keep current): "
    read -r NEW_VERSION
    if [ -z "$NEW_VERSION" ]; then
      NEW_VERSION=$CURRENT_VERSION
    fi
  else
    NEW_VERSION="$1"
  fi

  echo -e "== target version: ${YELLOW}$NEW_VERSION${NC}"

  if [ "$NEW_VERSION" != "$CURRENT_VERSION" ]; then
    echo "== updating version..."
    uv version "$NEW_VERSION"
    sed -i "s/__version__ = \".*\"/__version__ = \"$NEW_VERSION\"/" "$VERSION_FILE"
    echo -e "${GREEN}== version updated to $NEW_VERSION${NC}"
  else
    echo "== version unchanged"
  fi

  # Deliberately does not touch the appdata XML. See the header comment.
  echo ""
  echo -e "${GREEN}== prepared $NEW_VERSION${NC}"
  echo ""
  echo "Next, write the release notes by hand:"
  echo ""
  echo -e "  1. Add a <release> entry for ${YELLOW}$NEW_VERSION${NC} to $APPDATA"
  echo -e "     Use today's date: ${YELLOW}$(date +%Y-%m-%d)${NC}"
  echo "     The template is the XML comment at the top of <releases>."
  echo "  2. Review the diff, then:"
  echo ""
  echo -e "     ${YELLOW}./scripts/release.sh tag${NC}"
}

# -------------------------------------------------------------------- tag ----

phase_tag() {
  require_repo_root
  require_up_to_date

  VERSION=$(uv version --short)
  echo -e "== releasing version: ${YELLOW}$VERSION${NC}"

  # 1. The three places the version is written must agree.
  if ! grep -q "__version__ = \"$VERSION\"" "$VERSION_FILE"; then
    die "$VERSION_FILE does not declare $VERSION -- did 'release.sh prepare' run?"
  fi

  # 2. A <release> entry for this version must exist. This is the gate: it is
  #    what stops a release shipping with no notes, or with the previous
  #    release's notes still at the top of the file.
  BLOCK=$(release_block "$VERSION")
  if [ -z "$BLOCK" ]; then
    die "no <release version=\"$VERSION\"> entry in $APPDATA.
   Write the release notes first -- see the template comment in <releases>."
  fi

  # 3. That entry must carry a date and some actual prose.
  if ! printf '%s' "$BLOCK" | grep -q 'date="[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'; then
    die "the <release> entry for $VERSION has no valid date=\"YYYY-MM-DD\" attribute."
  fi

  TEXT=$(printf '%s' "$BLOCK" | sed -e 's/<[^>]*>//g' -e 's/[[:space:]]//g')
  if [ -z "$TEXT" ]; then
    die "the <release> entry for $VERSION has an empty description."
  fi
  if printf '%s' "$BLOCK" | grep -qiE 'TODO|FIXME|XXX|PLACEHOLDER'; then
    die "the <release> entry for $VERSION still contains placeholder text."
  fi

  RELEASE_DATE=$(printf '%s' "$BLOCK" | sed -n 's/.*date="\([0-9-]*\).*/\1/p' | head -1)
  if [ "$RELEASE_DATE" != "$(date +%Y-%m-%d)" ]; then
    echo -e "${YELLOW}== note: release entry is dated $RELEASE_DATE, today is $(date +%Y-%m-%d)${NC}"
  fi

  # 4. The XML must actually be valid. A stray '&' in the notes produces a file
  #    that breaks nothing locally and fails on the Flathub buildbot instead.
  echo "== validating AppStream metadata..."
  if command -v appstreamcli >/dev/null 2>&1; then
    appstreamcli validate --explain "$APPDATA" || die "AppStream validation failed."
  elif flatpak info org.flatpak.Builder >/dev/null 2>&1; then
    flatpak run --command=appstreamcli org.flatpak.Builder validate --explain "$APPDATA" \
      || die "AppStream validation failed."
  else
    echo -e "${YELLOW}== warning: no appstreamcli available, skipping validation${NC}"
  fi
  echo -e "${GREEN}== AppStream metadata OK${NC}"

  echo ""
  echo "== release notes for $VERSION:"
  printf '%s\n' "$BLOCK" | sed 's/^/   /'
  echo ""

  TAG_NAME="v$VERSION"

  # A tag already on the remote is not ours to silently recreate: it may be what
  # Flathub built from. Stop and make the operator deal with it explicitly.
  if git ls-remote --tags --exit-code origin "refs/tags/$TAG_NAME" >/dev/null 2>&1; then
    die "$TAG_NAME already exists on origin.
   If that tag is wrong, delete it deliberately before re-releasing:

       git push origin :refs/tags/$TAG_NAME
       git tag -d $TAG_NAME"
  fi

  if git tag -l | grep -q "^$TAG_NAME$"; then
    echo -e "${RED}== tag $TAG_NAME already exists!${NC}"
    echo -n "Delete existing tag and recreate? (y/N): "
    read -r DELETE_TAG
    if [ "$DELETE_TAG" = "y" ] || [ "$DELETE_TAG" = "Y" ]; then
      git tag -d "$TAG_NAME"
      git push origin ":refs/tags/$TAG_NAME" 2>/dev/null || true
    else
      die "aborted."
    fi
  fi

  echo -n "Commit the bump and create $TAG_NAME? (y/N): "
  read -r CONFIRM
  if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    die "aborted."
  fi

  # uv.lock is here because 'uv version' rewrites it and CI runs
  # 'uv sync --locked' -- omitting it lands a red main. See TASK-011.
  if [ -n "$(git status --porcelain -- pyproject.toml "$VERSION_FILE" "$APPDATA" uv.lock)" ]; then
    echo "== committing version changes..."
    git add pyproject.toml "$VERSION_FILE" "$APPDATA" uv.lock
    git commit -m "chore: bump version to $VERSION"
  else
    echo "== nothing to commit, tagging the current HEAD"
  fi

  git tag -a "$TAG_NAME" -m "Release $VERSION"

  echo -e "${GREEN}== tag $TAG_NAME created${NC}"
  echo ""
  echo "Next step is to push both refs together:"
  echo ""
  echo -e "   ${YELLOW}./scripts/release.sh push${NC}"
}

# ------------------------------------------------------------------- push ----

phase_push() {
  require_repo_root
  require_up_to_date

  VERSION=$(uv version --short)
  TAG_NAME="v$VERSION"
  BRANCH=$(git rev-parse --abbrev-ref HEAD)

  git rev-parse --verify --quiet "refs/tags/$TAG_NAME" >/dev/null \
    || die "no local tag $TAG_NAME -- run './scripts/release.sh tag' first."

  # The tag must be on the branch we are pushing, or we would publish a tag
  # pointing off into space.
  if ! git merge-base --is-ancestor "$TAG_NAME^{commit}" HEAD; then
    die "$TAG_NAME is not an ancestor of $BRANCH -- it is a leftover from an
   earlier attempt. Delete it and re-tag."
  fi

  echo -e "== pushing ${YELLOW}$BRANCH${NC} and ${YELLOW}$TAG_NAME${NC} to origin"

  # --atomic is the whole point: if the branch is refused, the tag does not go
  # either. Pushing them as two commands leaves a tag stranded off the branch.
  git push --atomic origin "$BRANCH" "refs/tags/$TAG_NAME" \
    || die "push refused -- nothing was published, including the tag.
   Rebase onto origin/$BRANCH and start over from 'prepare'."

  echo -e "${GREEN}== pushed $BRANCH and $TAG_NAME${NC}"
}

# ------------------------------------------------------------------- main ----

case "${1:-}" in
  prepare)
    shift
    phase_prepare "${1:-}"
    ;;
  tag)
    phase_tag
    ;;
  push)
    phase_push
    ;;
  -h | --help | help | "")
    usage
    exit 0
    ;;
  *)
    usage >&2
    die "unknown phase: $1"
    ;;
esac
