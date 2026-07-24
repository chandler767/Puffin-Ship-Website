#!/usr/bin/env bash
# Blocks AI attribution from entering this repo. See CLAUDE.md rule 1.
#
# Used by three callers so local hooks and CI enforce identical rules:
#   --range <rev-range>   check identity + message of existing commits (CI)
#   --identity            check the identity the pending commit would use (pre-commit)
#   --message <file>      check a pending commit message (commit-msg)
set -uo pipefail

# Identities permitted to author/commit here. The docs bot is expected and
# allowed to appear as a contributor; it just has to be named explicitly.
ALLOWED_EMAILS=(
  "chandler@chandlermayo.com"
  "docs-bot@users.noreply.github.com"
  "noreply@github.com"            # GitHub web UI edits
)

# Identity denylist: AI vendors and assistant names.
AI_EMAIL_RE='@anthropic\.com|@openai\.com'
AI_NAME_RE='(^|[^[:alnum:]])(Claude|Anthropic|Copilot|ChatGPT|Cursor)([^[:alnum:]]|$)'

# Message denylist: attribution trailers ONLY.
#
# Deliberately narrow. This repo documents a product that uses Claude, so
# commit messages like "Document Claude Vision processor" are legitimate and
# must pass. Only the trailer/marker forms are blocked.
AI_MSG_RE='[Cc]o-[Aa]uthored-[Bb]y:.*([Cc]laude|[Aa]nthropic)|[Cc]laude-[Ss]ession:|[Gg]enerated with \[|🤖|noreply@anthropic\.com|claude\.ai/code|claude\.com/claude-code'

FAILED=0

fail() { printf '  ✗ %s\n' "$1" >&2; FAILED=1; }

is_allowed_email() {
  local e="$1"
  for a in "${ALLOWED_EMAILS[@]}"; do
    [ "$e" = "$a" ] && return 0
  done
  return 1
}

check_identity() {
  local label="$1" name="$2" email="$3"
  if is_allowed_email "$email"; then
    return
  fi
  if printf '%s' "$email" | grep -qE "$AI_EMAIL_RE"; then
    fail "$label email is an AI identity: $name <$email>"
    return
  fi
  if printf '%s' "$name" | grep -qE "$AI_NAME_RE"; then
    fail "$label name is an AI identity: $name <$email>"
    return
  fi
  fail "$label is not an allowed identity: $name <$email>
      allowed: ${ALLOWED_EMAILS[*]}"
}

check_message() {
  local label="$1" msg="$2"
  local hits
  hits=$(printf '%s' "$msg" | grep -nE "$AI_MSG_RE" || true)
  if [ -n "$hits" ]; then
    while IFS= read -r line; do
      fail "$label contains AI attribution: $line"
    done <<< "$hits"
  fi
}

case "${1:-}" in
  --range)
    RANGE="${2:?--range needs a rev-range}"
    COUNT=0
    while IFS= read -r sha; do
      [ -z "$sha" ] && continue
      COUNT=$((COUNT + 1))
      check_identity "commit $sha author"    "$(git log -1 --format='%an' "$sha")" "$(git log -1 --format='%ae' "$sha")"
      check_identity "commit $sha committer" "$(git log -1 --format='%cn' "$sha")" "$(git log -1 --format='%ce' "$sha")"
      check_message  "commit $sha message"   "$(git log -1 --format='%B' "$sha")"
    done < <(git rev-list "$RANGE")
    echo "Checked $COUNT commit(s) in $RANGE"
    ;;
  --identity)
    # Resolve the identity this commit would actually use.
    A_NAME=$(git var GIT_AUTHOR_IDENT | sed -E 's/ <.*//')
    A_MAIL=$(git var GIT_AUTHOR_IDENT | sed -E 's/.*<([^>]*)>.*/\1/')
    C_NAME=$(git var GIT_COMMITTER_IDENT | sed -E 's/ <.*//')
    C_MAIL=$(git var GIT_COMMITTER_IDENT | sed -E 's/.*<([^>]*)>.*/\1/')
    check_identity "author"    "$A_NAME" "$A_MAIL"
    check_identity "committer" "$C_NAME" "$C_MAIL"
    ;;
  --message)
    MSGFILE="${2:?--message needs a file}"
    # Ignore comment lines git strips from the final message.
    check_message "commit message" "$(grep -v '^#' "$MSGFILE" || true)"
    ;;
  *)
    echo "usage: $0 --range <rev-range> | --identity | --message <file>" >&2
    exit 2
    ;;
esac

if [ "$FAILED" -ne 0 ]; then
  cat >&2 <<'EOT'

BLOCKED: AI attribution detected. See CLAUDE.md rule 1.
No AI may appear as author, co-author, committer, or in commit messages.
EOT
  exit 1
fi

echo "OK: no AI attribution"
