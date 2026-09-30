#!/bin/sh

set -u

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
cd "$ROOT" || exit 1

failures=0

note() {
  printf '%s\n' "$1"
}

fail() {
  failures=$((failures + 1))
  printf 'FAIL: %s\n' "$1"
}

pass() {
  printf 'PASS: %s\n' "$1"
}

note "Repository lint"
note "root: $ROOT"
note ""

required_files="
AGENTS.md
spec/README.md
spec/vision.md
spec/architecture.md
progress/status.md
progress/changelog.md
memory/GUIDE.md
memory/meta/insights.md
memory/meta/usage_log.md
.githooks/pre-push
scripts/lint_repo.sh
"

missing_required=0
for file in $required_files; do
  if [ ! -f "$file" ]; then
    fail "required file is missing: $file"
    missing_required=$((missing_required + 1))
  fi
done

if [ "$missing_required" -eq 0 ]; then
  pass "required meta and lint files exist"
fi

if [ ! -x ".githooks/pre-push" ]; then
  fail ".githooks/pre-push is not executable"
else
  pass ".githooks/pre-push is executable"
fi

if [ ! -x "scripts/lint_repo.sh" ]; then
  fail "scripts/lint_repo.sh is not executable"
else
  pass "scripts/lint_repo.sh is executable"
fi

hooks_path="$(git config --local --get core.hooksPath 2>/dev/null || true)"
if [ "$hooks_path" != ".githooks" ]; then
  fail "git core.hooksPath should be .githooks, got '${hooks_path:-unset}'"
else
  pass "git core.hooksPath is .githooks"
fi

conflicts="$(git grep -n -I -E '^(<<<<<<<|=======|>>>>>>>)($|[[:space:]])' -- . 2>/dev/null || true)"
if [ -n "$conflicts" ]; then
  fail "merge conflict markers found"
  printf '%s\n' "$conflicts"
else
  pass "no merge conflict markers"
fi

trailing="$(git grep -n -I -E '[[:blank:]]$' -- . 2>/dev/null || true)"
if [ -n "$trailing" ]; then
  fail "trailing whitespace found"
  printf '%s\n' "$trailing"
else
  pass "no trailing whitespace"
fi

label_literals="$(git grep -n -E '"cik_[0-9]+",[[:space:]]*[0-9]+(\.[0-9]+)?,' -- scripts src 2>/dev/null || true)"
label_literals="${label_literals}$(git grep -n -E 'realized_max_multiple["'"'"']?[:=][[:space:]]*[0-9]' -- scripts src 2>/dev/null || true)"
if [ -n "$label_literals" ]; then
  fail "hand-written outcome label constants (use the global label store)"
  printf '%s\n' "$label_literals"
else
  pass "no hand-written outcome label constants"
fi

unresolved_links=0
markdown_files="$(git ls-files '*.md')"
for file in $markdown_files; do
  links="$(sed -n 's/.*](\([^)]*\)).*/\1/p' "$file" | sed 's/#.*$//' | grep -E '^[A-Za-z0-9_./-]+$' || true)"
  for link in $links; do
    case "$link" in
      http:*|https:*|mailto:*|"")
        continue
        ;;
    esac
    base_dir="$(dirname "$file")"
    target="$base_dir/$link"
    if [ ! -e "$target" ]; then
      printf 'FAIL: broken local markdown link in %s -> %s\n' "$file" "$link"
      unresolved_links=$((unresolved_links + 1))
    fi
  done
done

if [ "$unresolved_links" -gt 0 ]; then
  failures=$((failures + unresolved_links))
else
  pass "local markdown links resolve"
fi

note ""
if [ "$failures" -eq 0 ]; then
  note "Lint result: PASS"
  exit 0
fi

note "Lint result: FAIL ($failures issue(s))"
exit 1
