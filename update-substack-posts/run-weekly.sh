#!/usr/bin/env bash
# Weekly Substack run, done locally because Substack returns HTTP 403 to GitHub-hosted runners.
# Does what .github/workflows/update-substack-posts.yml does: classify new posts, then open or update the PR.
#
# Needs ANTHROPIC_API_KEY in the environment, so run it through 1Password, e.g.
#   opclaude update-substack-posts/run-weekly.sh
# Extra arguments go to the pipeline, e.g. --publication-url name.substack.com or --post-url URL --force
#
# Needs: git, gh (logged in), pixi.
set -euo pipefail

PR_BRANCH="bot/substack-articles"
PATHS=(data.json update-substack-posts/data/*.json)

cd "$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ANTHROPIC_API_KEY is not set. Run this through 1Password, e.g. opclaude $0" >&2
  exit 1
fi

# The run commits to a bot branch, so never start with uncommitted work that could end up on it
if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree has uncommitted changes. Commit or stash them first." >&2
  exit 1
fi

start_ref="$(git symbolic-ref --short -q HEAD || git rev-parse HEAD)"
git fetch origin main

# Continue an open pipeline PR instead of opening a second one; its state isn't on main yet
open_pr="$(gh pr list --head "$PR_BRANCH" --state open --json number --jq '.[].number')"
if [ -n "$open_pr" ]; then
  git fetch origin "$PR_BRANCH"
  git checkout -q -B "$PR_BRANCH" FETCH_HEAD
else
  git checkout -q -B "$PR_BRANCH" origin/main
fi

# If anything below fails, stay on the bot branch: the pipeline saves as it goes, so re-running resumes
trap 'echo "Stopped on branch $PR_BRANCH; fix the problem and re-run (progress is saved)." >&2' ERR

pixi run pipeline "$@"

tmp="$(mktemp -d)"
git show origin/main:update-substack-posts/data/articles.json > "$tmp/base-articles.json" 2>/dev/null \
  || echo '[]' > "$tmp/base-articles.json"
git show origin/main:data.json > "$tmp/base-data.json"
pixi run pr-body --base "$tmp/base-articles.json" --base-resources "$tmp/base-data.json"
rm -rf "$tmp"

# No changes means no commit and no PR
if [ -z "$(git status --porcelain -- "${PATHS[@]}")" ]; then
  echo "No changes; nothing to commit."
  trap - ERR
  git checkout -q "$start_ref"
  exit 0
fi

git add -- "${PATHS[@]}"
git commit -q -m "Add Substack articles"
git push -u origin "$PR_BRANCH"

body="update-substack-posts/output/pr-body.md"
if [ -n "$open_pr" ]; then
  gh pr edit "$PR_BRANCH" --title "Add Substack articles" --body-file "$body"
else
  gh pr create --base main --head "$PR_BRANCH" --title "Add Substack articles" --body-file "$body"
fi

trap - ERR
git checkout -q "$start_ref"
