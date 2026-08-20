# FamilyRecorder documentation

**English** · [繁體中文](README.md) · [Back to the project home](../README.en.md)

Every document exists in both languages: `name.md` is Traditional Chinese, `name.en.md` is English.

---

## I want to…

| I want to… | Read this |
|---|---|
| Understand what it does first | [Project home](../README.en.md) |
| **Install and use it** | [Getting started](getting-started.en.md) |
| Confirm the microphone is set up correctly | [Hardware and capture](hardware.en.md) |
| Tune sensitivity, retention, summary time | [Configuration reference](configuration.en.md) |
| Understand how the daily summary is produced | [Daily summary and calendar](daily-summary.en.md) |
| Have transcripts say who probably spoke | [Speakers and direction](speakers.en.md) |
| Drive it from the menu bar, or **remove it** | [Menu bar and services](menu-bar.en.md) |
| Query the database myself | [Data and SQLite](data-model.en.md) |
| Do everything from the command line | [CLI reference](cli.en.md) |
| **Know exactly where my data goes** | [Privacy and trust boundaries](privacy.en.md) |
| Understand how it works inside | [Architecture](architecture.en.md) |
| **Use it for tutoring notes or a dream journal** | [Use-case guide](use-cases.en.md) |
| See where the project is heading | [Roadmap](roadmap.en.md) |
| Fix a specific problem | [Troubleshooting](troubleshooting.en.md) |
| Contribute | [Development](development.en.md) · [Contributing guide](../CONTRIBUTING.en.md) |

---

## All documents

### For users

| Document | Contents |
|---|---|
| **[Getting started](getting-started.en.md)** | Requirements, DMG and source installs, macOS permissions, first bring-up, next steps |
| **[Hardware and capture](hardware.en.md)** | The XVF3800's two channels, beamforming diagnosis, direction telemetry and calibration, A/B/C placement test |
| **[Configuration reference](configuration.en.md)** | Every `config.yaml` field, defaults, tuning advice, and what needs a restart |
| **[Daily summary and calendar](daily-summary.en.md)** | Summary contents, time/speaker/direction contracts, the text-only boundary, custom prompts, Google Calendar |
| **[Speakers and direction](speakers.en.md)** | Enrollment, the three decision conditions, how direction sits alongside timbre, threshold tuning, privacy |
| **[Menu bar and services](menu-bar.en.md)** | Every menu action, how pause works, the three LaunchAgents, one-click uninstall |
| **[Use-case guide](use-cases.en.md)** | Household log, tutoring review, dream journal, and thinking-out-loud setups with prompt templates |
| **[Troubleshooting](troubleshooting.en.md)** | Symptom-oriented fixes with diagnostic commands and SQL |

### Reference

| Document | Contents |
|---|---|
| **[CLI reference](cli.en.md)** | Every subcommand and flag, and when to use it |
| **[Data and SQLite](data-model.en.md)** | Directory layout, ER diagram, every column of all seven tables, useful queries |
| **[Privacy and trust boundaries](privacy.en.md)** | Complete data flow, threat model, explicit non-goals, consent checklist, self-verification |
| **[Architecture](architecture.en.md)** | Layered overview, module map, gate decisions, sequence diagrams, process topology, trust boundary |

### Project

| Document | Contents |
|---|---|
| **[Roadmap](roadmap.en.md)** | Candidate directions, what will not be built, how to influence priorities |
| **[Development and testing](development.en.md)** | Local development, testing strategy, code structure, building the DMG, the 31-item acceptance checklist |
| **[Contributing guide](../CONTRIBUTING.en.md)** | Pull request flow, code conventions, documentation conventions |
| **[Security policy](../SECURITY.en.md)** | How to report a security problem |
| **[Changelog](../CHANGELOG.md)** | Version history |

---

## If this is your first visit

If you only read three:

1. **[Project home](../README.en.md)** — what it is and why it is built this way
2. **[Privacy and trust boundaries](privacy.en.md)** — where the data actually goes, and how to verify it yourself
3. **[Use-case guide](use-cases.en.md)** — what it can do beyond a household log

---

## Documentation conventions

| Marker | Meaning |
|---|---|
| ✅ | Fully implemented |
| 🟡 | Possible today, but needs manual configuration |
| 🚧 | Planned, **not implemented** |
| ❌ | Deliberately excluded |
| ⚠️ | A tradeoff or risk worth noticing |

Every default value in these documents matches the actual default in the code. If you find a mismatch, that is a bug — please [open an issue](https://github.com/pcpcchen-coder/FamilyRecorder/issues).

> Some menu-bar labels and built-in prompt text are quoted in Traditional Chinese, because that is what the shipping UI shows. English glosses are given alongside them.
