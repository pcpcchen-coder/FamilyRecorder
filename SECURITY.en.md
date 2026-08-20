# Security policy

**English** · [繁體中文](SECURITY.md)

FamilyRecorder handles household recordings, transcripts, and voice features. Security problems here have concrete consequences, and they are taken seriously.

---

## Supported versions

| Version | Status |
|---|---|
| 0.14.x | ✅ Supported |
| Below 0.14.0 | ❌ Please upgrade |

Fixes ship on the latest version only.

---

## How to report

> ⚠️ **Please do not open a public issue for a security problem.**

Use GitHub's private vulnerability reporting:

**[Security → Report a vulnerability](https://github.com/pcpcchen-coder/FamilyRecorder/security/advisories/new)**

That opens a private thread visible only to the maintainer.

### Please include

- A short description of the problem and its impact
- Steps to reproduce
- Affected version and macOS version
- A proof of concept, if you have one

> 🔒 **Redact your own transcript content, household member names, and your username in file paths before reporting.** Reproduction steps rarely need real data.

---

## What happens next

| Stage | Target |
|---|---|
| Acknowledgement | Within 7 days |
| Initial assessment | Within 14 days |
| Fix and release | Depending on severity |

This is an individually maintained project with no dedicated security team. Best effort applies; enterprise response times cannot be guaranteed.

Once a fix ships, you will be credited in the advisory if you want to be.

---

## What counts as a security problem

### ✅ In scope

- **Boundary bypass**: any path that lets audio, voice features, or SQLite contents leave the machine
- **Credential exposure**: any path that puts a ChatGPT/Codex token or Google credential into logs, YAML, a plist, or process arguments
- **Effective prompt injection**: transcript content that makes the summary process use tools, read unexpected files, or alter the fixed contracts
- **Privilege escalation**: anything giving a LaunchAgent more than user-level privileges
- **Destructive uninstall**: removing files outside the intended scope
- **Model download integrity**: bypassing the allowlist or GGML validation
- **Local file permissions**: `speaker-profiles/` not created mode `0600`, or other sensitive files being too permissive

### ❌ Out of scope

| Case | Why |
|---|---|
| **Anyone with access to this Mac can read transcripts** | A [known and documented limitation](docs/privacy.en.md#what-this-design-does-not-protect-against). Use FileVault and an account password |
| **Backups contain the data directory** | Same. Time Machine / iCloud encryption is under your control |
| **Household members can read each other's transcripts** | Shared data on a shared computer — a household trust question |
| **Speaker labeling can be fooled** | This is **not** an authentication mechanism, [as the documentation states](docs/speakers.en.md). It must not be used where identity matters |
| **Whisper recognition errors** | A quality issue — please open a normal issue |
| **The DMG is not Apple-notarized** | [Known and documented](docs/getting-started.en.md#about-gatekeeper). Verify the SHA-256 |

---

## Deliberate security tradeoffs

These are **design decisions, not vulnerabilities**:

- Transcripts are stored **in the clear** locally. Encrypting them would prevent users from reading their own records with ordinary tools, and the key would still live on the same machine.
- Voice features are **not encrypted**, but are stored `0600` and cannot be reconstructed into audio.
- All three jobs are **per-user LaunchAgents**; root is deliberately avoided.
- The summary path has **no audio upload implementation** — a structural constraint rather than a runtime check.

The full threat model is in [privacy and trust boundaries](docs/privacy.en.md#threat-model).

---

## Things you can verify yourself

The [privacy document](docs/privacy.en.md#how-to-verify-it-yourself) lists checks you can run, including watching which files a summary run opens with `fs_usage`, confirming the transcript is not in process arguments, and confirming no keys appear in the config or plists.

Behavior that does not match the documentation is worth reporting.
