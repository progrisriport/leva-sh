#!/usr/bin/env bash
# Ralph loop (external) with roles: Opus plans -> Sonnet executes -> Opus reviews/commits.
# Each step is a fresh `claude -p` run. Usage limits/API errors: wait and retry the same step.
#
# Usage: scripts/ralph.sh [max_tasks]
# Env:
#   RALPH_PLANNER_MODEL (opus)   RALPH_PLANNER_EFFORT (high)
#   RALPH_EXEC_MODEL    (sonnet) RALPH_EXEC_EFFORT    (high)
#   RALPH_REVIEW_MODEL  (opus)   RALPH_REVIEW_EFFORT  (high)
#   RALPH_MAX_ROUNDS (3)          review rounds per task before BLOCKED
#   RALPH_WAIT_SECONDS (900)      wait after a usage limit / API error
#   RALPH_MAX_RETRIES (200)       consecutive failed calls before giving up
#   RALPH_MAX_IDLE (3)            tasks in a row without a new commit before stopping
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

MAX_TASKS="${1:-120}"
P_MODEL="${RALPH_PLANNER_MODEL:-opus}";  P_EFFORT="${RALPH_PLANNER_EFFORT:-high}"
E_MODEL="${RALPH_EXEC_MODEL:-sonnet}";   E_EFFORT="${RALPH_EXEC_EFFORT:-high}"
R_MODEL="${RALPH_REVIEW_MODEL:-opus}";   R_EFFORT="${RALPH_REVIEW_EFFORT:-high}"
MAX_ROUNDS="${RALPH_MAX_ROUNDS:-3}"
WAIT="${RALPH_WAIT_SECONDS:-900}"
MAX_RETRIES="${RALPH_MAX_RETRIES:-200}"
MAX_IDLE="${RALPH_MAX_IDLE:-3}"

STATE=.ralph; LOGS="$STATE/logs"
mkdir -p "$LOGS"; touch "$STATE/PROGRESS.md"

BASE_TOOLS=(
  "Read" "Edit" "Write" "Glob" "Grep" "TodoWrite"
  "WebFetch(domain:github.com)" "WebFetch(domain:raw.githubusercontent.com)"
  "WebFetch(domain:pypi.org)" "WebFetch(domain:textual.textualize.io)"
  "Bash(uv:*)" "Bash(uvx:*)" "Bash(python3:*)" "Bash(make:*)"
  "Bash(git status:*)" "Bash(git diff:*)" "Bash(git log:*)" "Bash(git show:*)"
  "Bash(git add:*)" "Bash(git stash:*)" "Bash(git restore:*)" "Bash(git checkout -- :*)"
  "Bash(git rm:*)" "Bash(git mv:*)"
  "Bash(mandoc:*)" "Bash(man:*)" "Bash(manpath:*)" "Bash(apropos:*)" "Bash(whatis:*)"
  "Bash(sw_vers:*)" "Bash(sqlite3:*)" "Bash(pbcopy:*)" "Bash(pbpaste:*)"
  "Bash(ls:*)" "Bash(cat:*)" "Bash(head:*)" "Bash(tail:*)" "Bash(wc:*)" "Bash(find:*)"
  "Bash(grep:*)" "Bash(mkdir:*)" "Bash(touch:*)" "Bash(mv:*)" "Bash(cp:*)"
  "Bash(rm -f:*)" "Bash(rm -rf .pytest_cache:*)" "Bash(time:*)" "Bash(date:*)"
  "Bash(which:*)" "Bash(command -v:*)" "Bash(sort:*)" "Bash(diff:*)" "Bash(chmod +x:*)"
  "Bash(col:*)" "Bash(mktemp:*)" "Bash(sandbox-exec:*)" "Bash(qlmanage:*)"
  "Bash(env:*)" "Bash(LEVA_HOME=:*)" "Bash(unzip:*)" "Bash(shasum:*)" "Bash(file:*)"
  "Bash(curl -fsSL https://github.com/tldr-pages/:*)" "Bash(stat:*)" "Bash(du:*)" "Bash(xargs:*)"
  "Bash(echo:*)" "Bash(printf:*)" "Bash(test:*)" "Bash(cd:*)" "Bash(pwd:*)" "Bash(sed:*)" "Bash(awk:*)"
)
COMMIT_TOOLS=("Bash(git commit:*)" "Bash(git push:*)")

log() { printf '[%s] %s\n' "$(date '+%F %T')" "$*" | tee -a "$STATE/ralph.log"; }

# run_step <label> <model> <effort> <prompt_file> <out_file> <can_commit:0|1> [extra prompt text]
# Retries the same step on usage limits / API errors. Returns 0 when the step produced a RALPH_ line.
run_step() {
  local label=$1 model=$2 effort=$3 prompt_file=$4 out=$5 can_commit=$6 extra=${7:-}
  local tools=("${BASE_TOOLS[@]}") retries=0 rc prompt
  (( can_commit )) && tools+=("${COMMIT_TOOLS[@]}")
  prompt=$(cat "$prompt_file")
  [[ -n "$extra" ]] && prompt+=$'\n\n'"$extra"
  while :; do
    log "  $label ($model/$effort) -> $out"
    claude -p "$prompt" \
      --model "$model" --effort "$effort" --permission-mode dontAsk \
      --allowedTools "${tools[@]}" >"$out" 2>&1
    rc=$?
    if grep -q '^RALPH_' "$out"; then return 0; fi
    if (( rc != 0 )) || grep -qiE 'session limit|usage limit|rate limit|limit reached|overloaded|529|api error|authenticate' "$out"; then
      retries=$((retries + 1))
      if (( retries > MAX_RETRIES )); then log "  too many retries, stopping."; exit 2; fi
      log "  $label failed (rc=$rc): $(head -c 160 "$out" | tr '\n' ' '). Waiting ${WAIT}s (retry $retries)."
      sleep "$WAIT"; continue
    fi
    log "  $label ended without a RALPH_ status line (rc=$rc)."
    return 1
  done
}

last_status() { grep -E '^RALPH_' "$1" | tail -1; }

bump_idle() {
  idle=$((idle + 1)); log "no new commit (idle $idle/$MAX_IDLE)."
  if (( idle >= MAX_IDLE )); then log "no progress for $MAX_IDLE tasks, stopping."; exit 3; fi
}

tasks=0; idle=0
log "start: tasks<=$MAX_TASKS planner=$P_MODEL/$P_EFFORT exec=$E_MODEL/$E_EFFORT review=$R_MODEL/$R_EFFORT rounds=$MAX_ROUNDS"

while (( tasks < MAX_TASKS )); do
  tasks=$((tasks + 1)); stamp=$(date +%m%d-%H%M%S)
  head_before=$(git rev-parse HEAD)
  rm -f "$STATE/brief.md" "$STATE/review.md"
  log "task $tasks: planning"

  p_out="$LOGS/$stamp-1-plan.log"
  if ! run_step plan "$P_MODEL" "$P_EFFORT" "$STATE/pre.md" "$p_out" 0; then
    log "planner gave no status."; bump_idle; continue
  fi
  st=$(last_status "$p_out"); log "  planner: $st"
  case "$st" in
    *NOTHING_TO_DO*|*WAITING_FOR_USER*) log "loop finished: $st"; touch "$STATE/DONE"; exit 0 ;;
    RALPH_TASK:*) task_id=${st#RALPH_TASK: } ;;
    *) log "unexpected planner status."; bump_idle; continue ;;
  esac
  if [[ ! -f "$STATE/brief.md" ]]; then log "planner wrote no brief.md."; bump_idle; continue; fi

  round=1; final=""
  while (( round <= MAX_ROUNDS )); do
    e_out="$LOGS/$stamp-2-exec-r$round.log"
    run_step "exec r$round" "$E_MODEL" "$E_EFFORT" "$STATE/exec.md" "$e_out" 0 || true
    e_st=$(last_status "$e_out"); log "  executor: ${e_st:-<none>}"

    r_out="$LOGS/$stamp-3-review-r$round.log"
    note="Executor status: ${e_st:-<none>}. Review round $round of $MAX_ROUNDS."
    if (( round == MAX_ROUNDS )); then note+=" This is the FINAL round: APPROVE or BLOCKED only, never CHANGES."; fi
    run_step "review r$round" "$R_MODEL" "$R_EFFORT" "$STATE/post.md" "$r_out" 1 "$note" || true
    r_st=$(last_status "$r_out"); log "  reviewer: ${r_st:-<none>}"
    case "$r_st" in
      *"RALPH_STATUS: DONE"*|*"RALPH_STATUS: BLOCKED"*) final=$r_st; break ;;
      *"RALPH_REVIEW: CHANGES"*) round=$((round + 1)) ;;
      *) log "  reviewer gave no usable status; leaving this task."; break ;;
    esac
  done
  log "task $tasks ($task_id): ${final:-unfinished}"

  if [[ "$(git rev-parse HEAD)" == "$head_before" ]]; then bump_idle
  else idle=0; log "committed: $(git log --oneline -1)"; fi
done
log "max tasks reached ($MAX_TASKS)."
