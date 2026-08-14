#!/usr/bin/env bash
# Install Question Surface for the current user.
#
#   ./install.sh              interactive
#   ./install.sh --yes        take the default for every prompt
#   ./install.sh --uninstall  remove what this script created
#
# Three things get wired up, each independently skippable:
#
#   1. `qsurface` on PATH, as a symlink into this clone.
#   2. The `question-surface` skill symlinked into ~/.claude/skills/, so every
#      Claude Code session in every project can see it.
#   3. A pointer line in ~/.claude/CLAUDE.md carrying the current gate, because
#      a skill is text an agent reads rather than a program that can look a
#      setting up — without the line the agent assumes the default.
#
# Symlinks rather than copies: `git pull` in this clone then updates the
# installed tool and skill together, so the two can never disagree about which
# version they are.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${QSURFACE_BIN_DIR:-$HOME/.local/bin}"
BIN_LINK="$BIN_DIR/qsurface"
SKILL_DIR="$HOME/.claude/skills"
SKILL_LINK="$SKILL_DIR/question-surface"
CLAUDE_MD="$HOME/.claude/CLAUDE.md"
BEGIN_MARK="<!-- question-surface:begin -->"
END_MARK="<!-- question-surface:end -->"

ASSUME_YES=0
UNINSTALL=0
for arg in "$@"; do
  case "$arg" in
    --yes|-y) ASSUME_YES=1 ;;
    --uninstall) UNINSTALL=1 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

say()  { printf '  %s\n' "$1"; }
step() { printf '\n%s\n' "$1"; }

confirm() {
  # confirm "question" -> 0 for yes
  [ "$ASSUME_YES" = "1" ] && return 0
  [ -t 0 ] || return 1          # non-interactive without --yes: decline
  local reply
  read -r -p "  $1 [Y/n] " reply
  case "$reply" in [nN]*) return 1 ;; *) return 0 ;; esac
}

strip_pointer() {
  # Remove the marked block, leaving the rest of the file untouched.
  [ -f "$CLAUDE_MD" ] || return 0
  grep -q "$BEGIN_MARK" "$CLAUDE_MD" || return 0
  local tmp
  tmp="$(mktemp)"
  awk -v b="$BEGIN_MARK" -v e="$END_MARK" '
    index($0, b) { skip = 1 }
    !skip        { print }
    index($0, e) { skip = 0 }
  ' "$CLAUDE_MD" > "$tmp"
  # Collapse the blank-line pair the removal can leave behind.
  awk 'NF == 0 { blanks++; if (blanks > 1) next } NF { blanks = 0 } { print }' \
    "$tmp" > "$tmp.2"
  mv "$tmp.2" "$CLAUDE_MD"
  rm -f "$tmp"
}

# ---------------------------------------------------------------- uninstall --

if [ "$UNINSTALL" = "1" ]; then
  step "Removing Question Surface"
  [ -L "$BIN_LINK" ]   && { rm -f "$BIN_LINK";   say "removed $BIN_LINK"; }   || say "no CLI link"
  [ -L "$SKILL_LINK" ] && { rm -f "$SKILL_LINK"; say "removed $SKILL_LINK"; } || say "no skill link"
  if [ -f "$CLAUDE_MD" ] && grep -q "$BEGIN_MARK" "$CLAUDE_MD"; then
    strip_pointer
    say "removed the pointer block from $CLAUDE_MD"
  else
    say "no pointer block in CLAUDE.md"
  fi
  say "config left at $(python3 -c 'import sys; sys.path.insert(0,"'"$ROOT"'"); from qsurface import config; print(config.config_path())' 2>/dev/null || echo '~/.config/question-surface/')"
  say "this clone was not deleted"
  echo
  exit 0
fi

# ------------------------------------------------------------------ install --

step "Question Surface — installing from $ROOT"

if ! command -v python3 >/dev/null 2>&1; then
  echo "  python3 is required and was not found on PATH" >&2
  exit 1
fi
PYV="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
if ! python3 -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 9) else 1)'; then
  echo "  python $PYV found; 3.9 or newer is required" >&2
  exit 1
fi
say "python $PYV"

step "1. Command on PATH"
mkdir -p "$BIN_DIR"
ln -sfn "$ROOT/qsurface.py" "$BIN_LINK"
chmod +x "$ROOT/qsurface.py"
say "$BIN_LINK -> $ROOT/qsurface.py"
case ":$PATH:" in
  *":$BIN_DIR:"*) say "$BIN_DIR is on PATH" ;;
  *) say "NOTE: $BIN_DIR is not on PATH — add this to your shell profile:"
     say "      export PATH=\"\$PATH:$BIN_DIR\"" ;;
esac

step "2. Skill for Claude Code"
if [ -e "$SKILL_LINK" ] && [ ! -L "$SKILL_LINK" ]; then
  say "SKIPPED: $SKILL_LINK exists and is not a symlink — not overwriting it"
else
  mkdir -p "$SKILL_DIR"
  ln -sfn "$ROOT/.claude/skills/question-surface" "$SKILL_LINK"
  say "$SKILL_LINK -> $ROOT/.claude/skills/question-surface"
fi

step "3. Gate pointer in $CLAUDE_MD"
GATE_LINE="$(python3 -c "
import sys
sys.path.insert(0, '$ROOT')
from qsurface import config
print(config.gate_sentence())
")"
say "The line to add:"
printf '\n    %s\n\n' "$GATE_LINE"
say "Without it an agent assumes the default gate. Change it later with"
say "\`qsurface config gate <n>\` and re-run this script."
if confirm "Add it to your global CLAUDE.md?"; then
  mkdir -p "$(dirname "$CLAUDE_MD")"
  touch "$CLAUDE_MD"
  strip_pointer
  {
    printf '\n%s\n' "$BEGIN_MARK"
    printf '%s\n' "$GATE_LINE"
    printf '%s\n' "$END_MARK"
  } >> "$CLAUDE_MD"
  say "added — remove it any time with ./install.sh --uninstall"
else
  say "skipped"
fi

step "Checking the install"
python3 "$ROOT/qsurface.py" doctor || true

echo
say "Done. Try: qsurface list"
echo
