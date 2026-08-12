# Race visualizer

A replayable, esports-style view of a **multi-agent race**: three heuristic shell
agents of increasing skill compete in one shared container to claim the eight
flags, first-to-surface-a-token wins it.

- **[unixctf-race.html](unixctf-race.html)** — self-contained (no network, no deps).
  Open it in a browser, or view the hosted copy:
  <https://claude.ai/code/artifact/9f0cd36a-66e6-455e-879e-c6f6e5d2cd47>

## What you're watching

- A **flag board** of eight sealed cells. When an agent surfaces a token, the cell
  flips to that agent's colour and reveals the `flag{…}`.
- Three **lane terminals** (novice cyan · journeyman pink · expert lime), each
  running its own shell over the same filesystem, typing real commands.
- A shared **18-tick clock**. Claims are exclusive, so a slower agent recovering
  the same flag a tick later gets sniped — watch the lead change.

The skill tiers stand in for the paper's **base → GRPO → GRPO+SFT** competence
gradient; every command shown actually executed in a live shell.

## Regenerating the data

The page embeds real race transcripts (`RACES` in the HTML). To rebuild them from
fresh runs and re-inject:

```bash
for s in 1 0 3; do python3 -m cogame_unixctf race --seed $s --json /tmp/race_$s.json; done
python3 - <<'PY'
import json
races = {str(s): json.load(open(f"/tmp/race_{s}.json")) for s in [1, 0, 3]}
data = "const RACES = " + json.dumps(races, separators=(",", ":")) + ";"
tmpl = open("viz/.race.template.html").read()
open("viz/unixctf-race.html", "w").write(tmpl.replace("__RACES_JSON__", data))  # str.replace, NOT re.sub
PY
```

Use `str.replace`, never `re.sub`, to inject: the JSON is full of backslashes and
`re.sub` would interpret them in the replacement string and corrupt the data.
`.race.template.html` is the same page with a `__RACES_JSON__` placeholder.
