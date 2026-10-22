#!/usr/bin/env bash
# lane_park.sh — the parked-lane ACK-or-stop bound (issue #517; design
# record .claude/deep-review/2026-10-21-issue517-parked-lane-stop-bound.md).
#
# A parked lane is DETECTED and BOUNDED here (increment SKILL.md "Parking a
# lane"): detection, notification, archive and fold are proven; the STOP is
# best-effort — the #517 drill measured a detached writer surviving the
# runner's task-kill past its deadline, so a lane still writing past the
# deadline is the orchestrator's signal to escalate to the human (the fold
# has already preserved the branch). It runs from a plain shell with
# explicit arguments, prints exit codes a script can assert, and never assumes
# it is running inside an agent.
#
# Usage:
#   scripts/lane_park.sh arm     <worktree> <lane> [deadline-minutes=15]
#   scripts/lane_park.sh check   <worktree>
#   scripts/lane_park.sh enforce <worktree> <lane>
#   scripts/lane_park.sh fold    <worktree> <lane>
#
# Exit codes for check/enforce (the verdict a wake asserts on):
#   0 QUIESCENT  PARK-ACK present AND zero commits with committer time >= the
#                arm epoch on the worktree's branch. Fail-closed: no ACK, any
#                post-arm commit — including one in the same second as the
#                arm — or any doubt reads ACTIVE.
#   1 ACTIVE     the lane did not stop; the orchestrator TaskStops the lane
#                (a harness primitive, not a message) and folds.
#   2 STRUCTURAL not armed / not a worktree / unreadable — never a verdict.
# arm and fold: 0 success, 2 refused or structural (no 1 — they carry no
# verdict).
#
# Disclosed residuals (design record §7): the compare is committer-timestamp
# based — a lane forging GIT_COMMITTER_DATE evades it; the recorded runaways
# were deaf, not adversarial. Requires git >= 2.31 (--path-format in fold).
set -uo pipefail

PROG="${0##*/}"
say()  { printf '%s: %s\n' "$PROG" "$*"; }
note() { printf '%s: %s\n' "$PROG" "$*" >&2; }
die_usage() {
  note "usage: $PROG arm <worktree> <lane> [minutes] | check <worktree> | enforce <worktree> <lane> | fold <worktree> <lane>"
  exit 2
}
need_worktree() { # $1=verb $2=path — a directory that git sees as a worktree
  [ -d "$2" ] || { note "$1: no such worktree directory: $2"; exit 2; }
  git -C "$2" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    note "$1: not a git worktree: $2"; exit 2;
  }
}

# do_check <worktree> — prints the verdict line, returns 0 QUIESCENT / 1
# ACTIVE / 2 structural. Shared by check and the enforce wake.
do_check() {
  wt="$1"
  [ -d "$wt" ] || { note "check: no such worktree directory: $wt"; return 2; }
  intent="$wt/PARK.intent"
  [ -f "$intent" ] || { note "check: not armed (no $intent)"; return 2; }
  git -C "$wt" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
    note "check: not a git worktree: $wt"; return 2;
  }
  lane="$(sed -n 's/^lane=//p' "$intent")"
  armed="$(sed -n 's/^armed_epoch=//p' "$intent")"
  case "$armed" in
    ''|*[!0-9]*) note "check: unreadable armed_epoch in $intent"; return 2 ;;
  esac
  branch="$(git -C "$wt" branch --show-current 2>/dev/null)"
  rev="${branch:-HEAD}" # detached parks judge HEAD; fold archives the commit
  # Count commits with committer time >= the arm epoch. Full enumeration and
  # an integer compare — no clock semantics beyond the compare; a commit in
  # the SAME second as the arm counts as post-arm activity (fail-closed).
  count="$(git -C "$wt" log --format=%ct "$rev" 2>/dev/null \
    | awk -v t="$armed" '$1 >= t {n++} END {print n + 0}')"
  reasons=""
  [ -f "$wt/PARK-ACK" ] || reasons="no PARK-ACK; ${reasons}"
  [ "${count:-0}" -eq 0 ] || reasons="${count} commit(s) with committer time >= arm epoch; ${reasons}"
  if [ -n "$reasons" ]; then
    say "ACTIVE lane=${lane:-?} branch=${rev} — ${reasons%; }"
    return 1
  fi
  say "QUIESCENT lane=${lane:-?} branch=${rev} — ACK present, no commits since arm"
  return 0
}

[ $# -ge 1 ] || die_usage
cmd="$1"
shift

case "$cmd" in
  arm)
    [ $# -ge 2 ] && [ $# -le 3 ] || die_usage
    wt="$1"; lane="$2"; minutes="${3:-15}"
    case "$minutes" in ''|*[!0-9]*) die_usage ;; esac
    need_worktree arm "$wt"
    intent="$wt/PARK.intent"
    if [ -e "$intent" ]; then
      note "arm: $intent already exists — the bound never extends (fold or resume first)"
      exit 2
    fi
    now_epoch="$(date +%s)" || { note "arm: date failed"; exit 2; }
    now_iso="$(date -u +%Y-%m-%dT%H:%M:%SZ)" || { note "arm: date failed"; exit 2; }
    printf 'lane=%s\narmed_epoch=%s\narmed_iso=%s\ndeadline_minutes=%s\n' \
      "$lane" "$now_epoch" "$now_iso" "$minutes" > "$intent" || {
        note "arm: cannot write $intent"; exit 2;
      }
    abs="$(cd "$wt" && pwd -P)" || { note "arm: cannot resolve $wt"; exit 2; }
    say "armed lane=$lane worktree=$abs deadline=${minutes}m (T0=$now_iso)"
    say "lane duty: write $abs/PARK-ACK (ISO time + lane) before finishing the current command, then stop"
    say "wake: (sleep $((minutes * 60)); scripts/lane_park.sh enforce '$abs' '$lane') &"
    exit 0
    ;;

  check)
    [ $# -eq 1 ] || die_usage
    do_check "$1"
    exit $?
    ;;

  enforce)
    [ $# -eq 2 ] || die_usage
    wt="$1"; lane="$2"
    do_check "$wt"
    rc=$?
    case "$rc" in
      0)
        say "wake: lane $lane cooperated — QUIESCENT. Fold when convenient: scripts/lane_park.sh fold '$wt' '$lane'"
        exit 0
        ;;
      1)
        say "wake: lane $lane is ACTIVE — TaskStop the lane NOW (a harness primitive, not a message), then: scripts/lane_park.sh fold '$wt' '$lane'"
        exit 1
        ;;
      *)
        say "wake: cannot judge lane $lane (structural) — inspect $wt manually"
        exit 2
        ;;
    esac
    ;;

  fold)
    [ $# -eq 2 ] || die_usage
    wt="$1"; lane="$2"
    need_worktree fold "$wt"
    tip="$(git -C "$wt" rev-parse 'HEAD^{commit}' 2>/dev/null)" || {
      note "fold: no HEAD commit in $wt"; exit 2;
    }
    branch="$(git -C "$wt" branch --show-current 2>/dev/null)"
    common="$(git -C "$wt" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || {
      note "fold: cannot resolve the repository of $wt (git >= 2.31 required)"; exit 2;
    }
    abs="$(cd "$wt" && pwd -P)" || { note "fold: cannot resolve $wt"; exit 2; }
    ts="$(date -u +%Y%m%dT%H%M%S)" || { note "fold: date failed"; exit 2; }
    ref="archive/parked/$lane-$ts"
    # Remove the worktree FIRST (force: dirty and mid-write state dies with
    # it — debris stays inside the lane's own worktree and never reaches the
    # shared checkout), then move the ref. If the rename fails after a
    # successful removal the branch stays live and the fold re-runs — no data
    # is lost either way. -M force-renames past a same-second name collision
    # (the overwritten tip stays reachable via reflog).
    git --git-dir="$common" worktree remove --force --force "$abs" 2>/dev/null || {
      note "fold: git worktree remove failed for $abs"; exit 2;
    }
    if [ -n "$branch" ]; then
      git --git-dir="$common" branch -M "$branch" "$ref" 2>/dev/null || {
        note "fold: cannot archive branch $branch to $ref"; exit 2;
      }
    else
      git --git-dir="$common" branch "$ref" "$tip" 2>/dev/null || {
        note "fold: cannot archive detached HEAD to $ref"; exit 2;
      }
    fi
    was="${branch:-detached @${tip}}"
    say "folded lane=$lane archived=$ref (was $was)"
    say "resume: git worktree add <path> '$ref'"
    say "ledger row: lane=$lane archived=$ref folded=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    exit 0
    ;;

  *)
    die_usage
    ;;
esac
