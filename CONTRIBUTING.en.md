# Contributing

**English** · [繁體中文](CONTRIBUTING.md)

Contributions to FamilyRecorder are welcome. This document covers how to propose changes, the conventions in use, and where help is most valuable.

---

## Where help is most valuable

| Area | Why it matters |
|---|---|
| **Support for other microphone arrays** | The project is bound to the XVF3800 today, and real routing/telemetry responses are nearly impossible to guess |
| **Prompt templates for new scenarios** | They go straight into the [use-case guide](docs/use-cases.en.md) and help everyone immediately |
| **Reports from non-Chinese setups** | There is almost no real data on this today |
| **Documentation translation and corrections** | Especially wording in the English versions |
| **Failures on the [31-item acceptance checklist](docs/development.en.md#acceptance-checklist)** | Any item failing on your machine is a concrete bug |

---

## Before opening an issue

**Redact sensitive content first.** Logs, SQL results, and `doctor` output can contain:

- Transcript content
- Household member names
- Your username inside file paths
- Calendar IDs and display names

Substitute those before pasting.

These are helpful to include:

```bash
RUNTIME="$HOME/Library/Application Support/FamilyRecorder"
CONFIG="$HOME/.config/familyrecorder/config.yaml"

"$RUNTIME/venv/bin/family-recorder" --config "$CONFIG" doctor
sw_vers
```

> 🔒 **Do not open a public issue for a security problem.** See the [security policy](SECURITY.en.md).

---

## Development setup

```bash
git clone https://github.com/pcpcchen-coder/FamilyRecorder.git
cd FamilyRecorder
/opt/homebrew/bin/python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]'
```

All four must pass before you open a pull request:

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/pytest --cov=family_recorder
.venv/bin/python -m build
```

Those are exactly what CI runs. See [development and testing](docs/development.en.md).

---

## Code conventions

### Dependency direction

Module dependencies are **deliberately one-directional**: lower modules never import higher ones.

```text
config → devices/audio/metrics → transcriber/direction/speakers/hallucination/storage → listener/summary → cli
```

Place new modules within this hierarchy and avoid introducing cycles. The full graph is in [architecture → module map](docs/architecture.en.md#module-map).

### Style

- `ruff`: line-length 100, target `py311`, rule sets `E` `F` `I` `UP` `B` `SIM`
- Type annotations: annotate parameters and return values on public functions in new code
- Data classes: prefer `@dataclass(frozen=True)` for immutable data

### Tests

**CI does not depend on physical hardware.** New features should come with isolated tests that run without an XVF3800. Existing tests show how device responses are simulated:

```bash
.venv/bin/pytest tests/test_direction.py -v   # USB response decoding
.venv/bin/pytest tests/test_listener.py -v    # gate decisions
.venv/bin/pytest tests/test_summary.py -v     # the text-only boundary
```

> For hardware-related changes, please also run the relevant items from the [acceptance checklist](docs/development.en.md#acceptance-checklist) on real hardware, and note in the pull request which items you ran.

---

## Design principles

If a change conflicts with any of these, explain why in the pull request:

| Principle | What it means |
|---|---|
| **Boundaries must be testable** | Do not replace a structural constraint with "the prompt tells it not to" |
| **Silence produces no data** | Do not write files during silence for convenience |
| **No single sensor is authoritative** | Software and hardware evidence must check each other |
| **Approximate must read as approximate** | Do not present `speaker_confidence` as an identity probability |
| **Degrade, never abort** | Recording must continue when telemetry fails |
| **Removal must be complete** | New files belong in the uninstall scope, or the pull request should say why not |

Also see [explicit non-goals](docs/privacy.en.md#explicit-non-goals) — pull requests for those are not accepted.

---

## Documentation conventions

**Every document exists in both languages:** `name.md` is Traditional Chinese, `name.en.md` is English.

When changing documentation:

1. **Change both versions.** Editing only one lets them drift apart.
2. Keep the language-switch links at the top.
3. Use the shared markers consistently: ✅ implemented, 🟡 needs manual setup, 🚧 planned, ❌ deliberately excluded, ⚠️ caution.
4. **Never describe a planned feature as if it exists.**
5. Default values in documentation must match the code.

### Mermaid diagrams

Architecture diagrams use Mermaid, which GitHub renders natively. When adding one:

- Quote node labels: `A["text"]`
- Specify `fill`, `stroke`, and `color` together in `classDef` so the diagram stays readable in both light and dark themes
- Verify the syntax parses before submitting

---

## Pull requests

1. Branch from `main`.
2. One pull request, one concern.
3. Write commit messages in the imperative, saying what changed and why.
4. Run all four checks above before submitting.
5. In the description, state what changed, why, and how you verified it. For hardware-related changes, list the acceptance items you ran.

---

## License

By contributing, you agree that your contributions are licensed under the [MIT License](LICENSE).
