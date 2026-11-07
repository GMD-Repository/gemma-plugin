#!/usr/bin/env bash
# Mirror the docs site sources into the public stable repo.
#
# Vercel (Hobby plan) cannot deploy private organization repos, so it builds
# https://gemma-plugin.vercel.app from the public stable repo instead. This
# copies everything the VitePress build needs and pushes it to that repo's main.
#
# Usage: sync_public_repo.sh "<commit message>"
# Env:   GH_TOKEN           token with contents:write on the stable repo
#        STABLE_REPOSITORY  owner/repo (default: GMD-Repository/gemma-plugin-stable)
set -euo pipefail

message="${1:?commit message required}"
stable_repo="${STABLE_REPOSITORY:-GMD-Repository/gemma-plugin-stable}"
workdir="$(mktemp -d)"
trap 'rm -rf "$workdir"' EXIT

git clone --depth 1 "https://x-access-token:${GH_TOKEN}@github.com/${stable_repo}.git" "$workdir"

rsync -a --delete --exclude '.vitepress/cache' --exclude '.vitepress/dist' docs/ "$workdir/docs/"
cp package.json pnpm-lock.yaml vercel.json tsconfig.json "$workdir/"

cd "$workdir"
git config user.name "Gemma Release[bot]"
git config user.email "gemma-release[bot]@users.noreply.github.com"
git add -A
if git diff --staged --quiet; then
  echo "Public repo already up to date."
  exit 0
fi
git commit -m "$message"
git push origin HEAD:main
