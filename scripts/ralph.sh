#!/usr/bin/env bash
# Ralph loop (external): runs `claude -p` repeatedly with fresh context.
# Each iteration does one PLAN.md task. Survives usage limits by waiting and retrying.
#
# Usage: scripts/ralph.sh [max_iterations]
# Env:   RALPH_MODEL (default opus), RALPH_EFFORT (default xhigh),
#        RALPH_WAIT_SECONDS (default 900), RALPH_MAX_RETRIES (default 200),
#        RALPH_MAX_IDLE (default 3: stop after N successful iterations with no new commit)
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

MAX_ITER="${1:-120}"
MODEL="${RALPH_MODEL:-opus}"
EFFORT="${RALPH_EFFORT:-xhigh}"
WAIT="${RALPH_WAIT_SECONDS:-900}"
MAX_RETRIES="${RALPH_MAX_RETRIES:-200}"
MAX_IDLE="${RALPH_MAX_IDLE:-3}"

STATE=.ralph
LOGS="$STATE/logs"
mkdir -p "$LOGS"
touch "$STATE/PROGRESS.md"

ALLOWED_TOOLS=(
  "Read" "Edit" "Write" "Glob" "Grep" "TodoWrite"
  "WebFetch(domain:github.com)" "WebFetch(domain:raw.githubusercontent.com)"
  "WebFetch(domain:pypi.org)" "WebFetch(domain:textual.textualize.io)"
  "Bash(uv:*)" "Bash(uvx:*)" "Bash(python3:*)"
  "Bash(git status:*)" "Bash(git diff:*)" "Bash(git log:*)" "Bash(git show:*)"
  "Bash(git add:*)" "Bash(git commit:*)" "Bash(git push:*)" "Bash(git stash:*)"
  "Bash(git restore:*)" "Bash(git checkout -- :*)" "Bash(git rm:*)" "Bash(git mv:*)"
  "Bash(mandoc:*)" "Bash(man:*)" "Bash(manpath:*)" "Bash(apropos:*)" "Bash(whatis:*)"
  "Bash(sw_vers:*)" "Bash(sqlite3:*)" "Bash(pbcopy:*)" "Bash(pbpaste:*)"
  "Bash(ls:*)" "Bash(cat:*)" "Bash(head:*)" "Bash(tail:*)" "Bash(wc:*)" "Bash(find:*)"
  "Bash(grep:*)" "Bash(mkdir:*)" "Bash(touch:*)" "Bash(mv:*)" "Bash(cp:*)"
  "Bash(rm -f:*)" "Bash(rm -rf .pytest_cache:*)" "Bash(time:*)" "Bash(date:*)"
  "Bash(which:*)" "Bash(command -v:*)" "Bash(sort:*)" "Bash(diff:*)" "Bash(chmod +x:*)"
  "Bash(make:*)" "Bash(col:*)" "Bash(mktemp:*)" "Bash(sandbox-exec:*)" "Bash(qlmanage:*)"
  "Bash(env:*)" "Bash(LEVA_HOME=:*)" "Bash(unzip:*)" "Bash(shasum:*)" "Bash(file:*)"
  "Bash(curl -fsSL https://github.com/tldr-pages/:*)" "Bash(stat:*)" "Bash(du:*)" "Bash(xargs:*)"
  "Bash(echo:*)" "Bash(printf:*)" "Bash(test:*)" "Bash(cd:*)" "Bash(pwd:*)" "Bash(sed:*)" "Bash(awk:*)"
)

log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*" | tee -a "$STATE/ralph.log"; }

iter=0; retries=0; idle=0
log "start: max_iter=$MAX_ITER model=$MODEL effort=$EFFORT"

while (( iter < MAX_ITER )); do
  if [[ -f "$STATE/DONE" ]]; then log "DONE file found, stopping."; exit 0; fi

  n=$((iter + 1))
  out="$LOGS/iter-$(printf '%03d' "$n")-$(date +%H%M%S).log"
  head_before=$(git rev-parse HEAD)
  log "iteration $n starting (log: $out)"

  claude -p "$(cat "$STATE/PROMPT.md")" \
    --model "$MODEL" --effort "$EFFORT" \
    --permission-mode dontAsk \
    --allowedTools "${ALLOWED_TOOLS[@]}" \
    >"$out" 2>&1
  rc=$?

  if (( rc != 0 )) || { ! grep -q '^RALPH_STATUS:' "$out" && grep -qiE 'usage limit|rate limit|limit reached|overloaded|529|api error|authenticate' "$out"; }; then
    retries=$((retries + 1))
    if (( retries > MAX_RETRIES )); then log "too many retries, stopping."; exit 2; fi
    log "iteration $n failed (rc=$rc) — likely usage limit/API error. Waiting ${WAIT}s (retry $retries)."
    sleep "$WAIT"
    continue
  fi

  iter=$n; retries=0
  status=$(grep -E '^RALPH_STATUS:' "$out" | tail -1)
  log "iteration $n status: ${status:-<none>}"
  case "$status" in
    *NOTHING_TO_DO*|*WAITING_FOR_USER*) log "loop finished: $status"; touch "$STATE/DONE"; exit 0 ;;
  esac
  if [[ "$(git rev-parse HEAD)" == "$head_before" ]]; then
    idle=$((idle + 1))
    log "iteration $n finished with NO new commit (idle $idle/$MAX_IDLE)."
    if (( idle >= MAX_IDLE )); then log "no progress for $MAX_IDLE iterations, stopping."; exit 3; fi
  else
    idle=0
    log "iteration $n ok: $(git log --oneline -1)"
  fi
done

log "max iterations reached ($MAX_ITER)."
