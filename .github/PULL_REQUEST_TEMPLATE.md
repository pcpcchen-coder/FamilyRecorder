## What changed / 改了什麼

<!-- One or two sentences. 一到兩句話說明。 -->

## Why / 為什麼

<!-- What problem does this solve? Link an issue if there is one. -->
<!-- 這解決什麼問題？如果有相關 issue 請連結。 -->

## How it was verified / 怎麼驗證的

- [ ] `ruff check .`
- [ ] `ruff format --check .`
- [ ] `pytest --cov=family_recorder`
- [ ] `python -m build`

<!-- For hardware-related changes, list which acceptance-checklist items you ran on real hardware. -->
<!-- 硬體相關改動請列出在實機跑過驗收清單的哪幾項。 -->

## Documentation / 文件

- [ ] Both language versions updated (`name.md` and `name.en.md`), or not applicable
      兩個語言版本都更新了，或不適用
- [ ] Default values in documentation match the code
      文件中的預設值與程式碼一致
- [ ] Planned features are marked 🚧 rather than described as existing
      規劃中的功能標示 🚧，沒有寫成已實作

## Design principles / 設計原則

<!-- If this change conflicts with any principle in CONTRIBUTING.md, explain why here. -->
<!-- 若本次改動牴觸 CONTRIBUTING.md 中的任一原則，請在此說明理由。 -->

- [ ] Does not weaken the text-only cloud boundary
      沒有削弱「只送純文字」的雲端邊界
- [ ] Silence still produces no WAV and no Whisper call
      安靜時仍然不產生 WAV、不呼叫 Whisper
- [ ] Approximate results still read as approximate
      近似結果仍然以近似的措辭呈現
