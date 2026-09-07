#!/usr/bin/env bash
# Cut a GitHub release of the Blender add-on as OneZeroOne-<version>.zip
#
# Usage:
#   ./scripts/release.sh           # use version from blender_manifest.toml
#   ./scripts/release.sh 1.1.0     # bump that version, commit, then release
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MANIFEST="onezeroone/blender_manifest.toml"
current_version() {
  grep -E '^version = "' "$MANIFEST" | head -1 | sed 's/.*"\(.*\)"/\1/'
}

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  VERSION="$(current_version)"
fi

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9.]+)?$ ]]; then
  echo "Invalid version: $VERSION (expected e.g. 1.0.0)" >&2
  exit 1
fi

TAG="v${VERSION}"
ZIP="OneZeroOne-${VERSION}.zip"

if git rev-parse "$TAG" >/dev/null 2>&1; then
  echo "Tag $TAG already exists. Bump the version and try again." >&2
  exit 1
fi

if [[ "$(current_version)" != "$VERSION" ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Working tree is dirty. Commit or stash before bumping the version." >&2
    exit 1
  fi
  sed -i "s/^version = \".*\"/version = \"$VERSION\"/" "$MANIFEST"
  git add "$MANIFEST"
  git commit -m "Bump version to ${VERSION}."
  git push origin HEAD
fi

rm -f "$ZIP"
zip -r "$ZIP" onezeroone \
  -x '*/__pycache__/*' \
  -x '*.pyc' \
  -x '*/.gitkeep'

echo "Created $ZIP"

git tag -a "$TAG" -m "OneZeroOne ${VERSION}"
git push origin "$TAG"

gh release create "$TAG" \
  --title "OneZeroOne ${VERSION}" \
  --generate-notes \
  "$ZIP"

echo "Release: $(gh release view "$TAG" --json url --jq .url)"
