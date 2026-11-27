#!/bin/bash
# Safely load KEY=VALUE assignments from an env file without evaluating arbitrary shell code.
# Compatible with macOS /bin/bash 3.2 under `set -euo pipefail`.

_mcp_trim_ws() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

load_env_safe() {
  local env_file="$1"
  if [ ! -f "$env_file" ]; then
    return 0
  fi

  local lineno=0
  local raw_line=""
  local trimmed=""
  local key=""
  local val=""
  local first_char=""
  local last_char=""

  while IFS= read -r raw_line || [ -n "$raw_line" ]; do
    lineno=$((lineno + 1))
    raw_line="${raw_line%$'\r'}"
    trimmed="$(_mcp_trim_ws "$raw_line")"

    if [ -z "$trimmed" ] || [[ "$trimmed" == \#* ]]; then
      continue
    fi

    if [[ "$trimmed" == export[[:space:]]* ]]; then
      trimmed="${trimmed#export}"
      trimmed="$(_mcp_trim_ws "$trimmed")"
    fi

    if [[ "$trimmed" != *=* ]]; then
      printf '[load_env_safe] warning: skipping malformed line %d in %s\n' "$lineno" "$env_file" >&2
      continue
    fi

    key="$(_mcp_trim_ws "${trimmed%%=*}")"
    val="${trimmed#*=}"

    if ! [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]]; then
      printf '[load_env_safe] warning: skipping invalid key at line %d in %s\n' "$lineno" "$env_file" >&2
      continue
    fi

    if [ "${#val}" -ge 2 ]; then
      first_char="${val:0:1}"
      last_char="${val:$((${#val} - 1)):1}"
      if { [ "$first_char" = "'" ] && [ "$last_char" = "'" ]; } || { [ "$first_char" = '"' ] && [ "$last_char" = '"' ]; }; then
        val="${val:1:$((${#val} - 2))}"
      fi
    fi

    export "${key}=${val}"
  done < "$env_file"
}
