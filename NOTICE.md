# Notices

The code written for this project is licensed under the MIT License (see [LICENSE](LICENSE)). The material below is not covered by that licence and stays under its own terms.

## Other projects' code in the tests

These copies are in `tests/` only. They are not part of the add-on package. They are word for word, so that the tests run the real code of those projects.

- `tests/nvda2026_2/` (`_remoteClient/` and `extensionPoints/`) is copied from NVDA 2026.2 (<https://github.com/nvaccess/nvda>, tag `release-2026.2`). Each file carries NVDA's own notice: "Copyright (C) ... NV Access Limited ... This file is covered by the GNU General Public License. See the file COPYING for more details." NVDA's licence is at <https://github.com/nvaccess/nvda/blob/master/copying.txt>.
- `tests/issue49Sources.py` holds, as strings, code cut out of NVDA 2026.2 (`source/baseObject.py` and `source/synthSettingsRing.py`, under NVDA's licence above) and out of Eloquence64RS 19.1.4-RS (<https://github.com/Nick6489/Eloquence64RS>, tag `v19.1.4-RS`, `addon/synthDrivers/eloquence.py`, under that project's own terms).
- `tests/classicSpeechLifecycle118.py` is `_speech_core/processors/web/lifecycle.py` from ClassicSpeech 1.18 (<https://github.com/joshknnd1982/classicspeech-nvda>, tag `v1.18`, GNU General Public License, version 2 or later).
