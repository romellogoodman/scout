#!/usr/bin/env bash
# Smoke test: can each OpenRouter finalist drive pi's tools at all?
# Needs OPENROUTER_API_KEY set (or pi's /login openrouter done).
# Each model must read a file and write a file through pi's tool loop.
set -u
export PATH="$HOME/.pi/bin:$PATH"

MODELS=(
  "deepseek/deepseek-v4-flash-0731"
  "cohere/north-mini-code:free"
  "meta/muse-spark-1.2"
  "moonshotai/kimi-k3"
)

TIMEOUT_CMD=$(command -v gtimeout || command -v timeout || echo "")

for m in "${MODELS[@]}"; do
  dir=$(mktemp -d)
  echo "The magic word is: pomegranate" > "$dir/clue.txt"
  start=$SECONDS
  out=$(cd "$dir" && ${TIMEOUT_CMD:+$TIMEOUT_CMD 300} pi \
    --provider openrouter --model "$m" \
    --no-session --no-extensions --no-skills --no-context-files \
    -p "Read clue.txt, then create a file named answer.txt containing only the magic word from clue.txt." 2>&1)
  elapsed=$((SECONDS - start))
  if [ -f "$dir/answer.txt" ] && grep -qi pomegranate "$dir/answer.txt"; then
    echo "PASS  ${elapsed}s  $m"
  else
    echo "FAIL  ${elapsed}s  $m"
    echo "$out" | tail -5 | sed 's/^/      /'
  fi
  rm -rf "$dir"
done
