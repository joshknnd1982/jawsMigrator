# JAWS Migration Assistant for NVDA

An NVDA add-on that brings a JAWS user's settings into NVDA. It reads everything JAWS knows about you:

- Settings Center options.
- Voice profiles and voice aliases.
- Speech and sound schemes.
- Dictionaries and punctuation.
- Keyboard assignments and quick navigation keys.
- Sounds, and settings for single applications.

Each one is mapped to its closest NVDA equivalent. Anything NVDA can't use is kept in an archive and explained in a report.

JAWS itself is never changed. The assistant only reads JAWS files. It never writes to, updates, reconfigures or uninstalls JAWS. When the migration is finished, it tells you that you can uninstall JAWS yourself if you want to.

- Version: 1.0
- Requires: NVDA 2026.1 or later (tested with NVDA 2026.2) on Windows 10 22H2 or Windows 11
- Works with: JAWS 18 and later, in any JAWS language, including settings left behind by an uninstalled JAWS
- License: GNU General Public License, version 2 or later

## Contents

- [What it does](#what-it-does)
- [Installing](#installing)
- [Using the assistant](#using-the-assistant)
- [What each JAWS manager becomes in NVDA](#what-each-jaws-manager-becomes-in-nvda)
- [Voices, voice profiles and voice aliases](#voices-voice-profiles-and-voice-aliases)
- [ClassicSpeech](#classicspeech)
- [Sounds](#sounds)
- [Keyboard commands](#keyboard-commands)
- [The assistant's own commands](#the-assistants-own-commands)
- [Recommended add-ons](#recommended-add-ons)
- [Backups and restoring](#backups-and-restoring)
- [JAWS is never changed](#jaws-is-never-changed)
- [Adapting to each computer](#adapting-to-each-computer)
- [Leasey](#leasey)
- [Updates](#updates)
- [Where things are kept](#where-things-are-kept)
- [Limits](#limits)
- [Building from source](#building-from-source)
- [Credits](#credits)

## What it does

1. **Checks the computer.** It finds every installed JAWS version, its build and languages, and your personal and shared JAWS settings. It also checks Windows, your copy of NVDA, the synthesizers and voices NVDA can use, and ClassicSpeech. If JAWS is not installed, an accessible message box says so; press OK and carry on with your day. If JAWS was uninstalled but its settings are still there, it offers to migrate those.
2. **Indexes all JAWS settings.** It catalogs every JAWS settings file, sound and synthesizer for the chosen JAWS version, by JAWS manager. Your personal settings are for the Windows user who is signed in. Shared settings apply to everyone on the computer.
3. **Lets you choose** your settings, the shared settings, or both, layered as JAWS layers them. It also lets you choose what to migrate and where it goes.
4. **Migrates** into a separate NVDA configuration profile named "JAWS settings" (recommended), or into NVDA's normal configuration.
5. **Backs up NVDA's settings first.** If anything goes wrong, it puts them back automatically. You can restore any backup later.
6. **Writes a report** of everything that changed, everything kept for NVDA, and everything JAWS had that NVDA has no equivalent for.

## Installing

1. Download `jawsMigrator-1.0.nvda-addon` from the [releases page](https://github.com/joshknnd1982/jawsMigrator/releases).
2. Press Enter on the file. NVDA asks you to confirm, installs the add-on and offers to restart.
3. A few seconds after NVDA starts, the assistant checks the computer once and offers to migrate. After that it only runs when you ask.

## Using the assistant

Open it from the NVDA menu: Tools, JAWS Migration Assistant, Migrate JAWS settings to NVDA. Or press NVDA+Shift+J, then M.

The assistant is a single dialog with Back, Next and Cancel buttons. Each step is a labeled group. NVDA says the step name and puts you on the step's first control. Long text is in read-only boxes you can read line by line. Nothing changes until you press Migrate on the last step.

1. **System check.** What was found on this computer. Choose the JAWS version and settings language if there is more than one.
2. **Which JAWS settings.** Your settings and the shared settings (recommended), only yours, or only the shared ones.
3. **What was found.** A summary of every JAWS manager's files and entries, JAWS's synthesizers and their NVDA equivalents, and whether Eloquence or IBM ViaVoice is available. The View the full index button shows every file.
4. **Choose what to migrate.** A checklist with counts: Settings Center, voices, application profiles, sleep mode applications, dictionaries, punctuation, keyboard commands, and the archive.
5. **Where the JAWS settings go.** A separate profile, or NVDA's normal configuration. For a profile, you can turn it on every time NVDA starts, and right away.
6. **Voices.** Which NVDA synthesizer and voice replaces your JAWS voice, and which JAWS voice profiles to migrate.
7. **ClassicSpeech** (only when it is installed). Which JAWS speech and sound schemes to copy, which one to turn on, and whether to copy voice profiles, voice aliases, and verbosity, number and text settings.
8. **Sound effects.** Whether JAWS sound effects replace NVDA's sounds, with the list of which JAWS sound replaces which NVDA sound.
9. **Keyboard commands.** Whether JAWS keystrokes become NVDA input gestures, whether to use JAWS quick navigation letters in browse mode, and whether JAWS keystrokes may replace NVDA's own. The list shows every keystroke that will be added.
10. **Recommended add-ons.** Which of the four recommended add-ons to install, what each does, and what happens if you don't.
11. **Ready to migrate.** A summary of what will happen. Press Migrate.

Progress is spoken as it happens. The last step shows the result. It has buttons to open the report, open the folder with the migration's files, and restart NVDA when a restart is needed.

## What each JAWS manager becomes in NVDA

| JAWS manager | What happens |
| --- | --- |
| Settings Center (`.jcf`) | Every option with an NVDA equivalent is set. Examples: typing echo, keyboard layout and NVDA key, speech interruption, screen echo (dynamic content), language switching, phonetic reading after a pause, capitals, verbosity (access keys, tooltips, position information), progress bars, mouse echo, touch typing, audio ducking. Also browse mode (simple layout, line length, lines per page, Say All on page load, forms mode, audio indication), document formatting (headings, lists, tables, landmarks, links, graphics, table headers and coordinates, font attributes) and braille (mode, word wrap, cursor shapes and blink rate, messages, scroll rate, English braille tables). |
| Settings for one application (`.jcf` for that program) | An NVDA configuration profile named "JAWS - program" that turns on in that program. |
| Sleep mode in an application | NVDA sleeps in that application too. You can change this in NVDA's Settings, JAWS Migration Assistant. |
| Quick Settings (`.qs`, `.qsm`) | Quick Settings saves into the application's `.jcf`, which is migrated as above. |
| Voice profiles (`.vpf`) | See [Voices](#voices-voice-profiles-and-voice-aliases). |
| Speech and Sounds Manager (`.smf`) | ClassicSpeech Speech and Sound Schemes. See [ClassicSpeech](#classicspeech). |
| Dictionary Manager (`.jdf`) | NVDA speech dictionary entries (details below this table). |
| Punctuation (`.sbl`) | Symbols you changed become NVDA symbol pronunciations, at the NVDA level where JAWS spoke them. You can also choose JAWS's names for every symbol. |
| Keyboard Manager (`.jkm`) | NVDA input gestures for JAWS commands NVDA also has. See [Keyboard commands](#keyboard-commands). |
| Navigation Quick Keys | NVDA browse mode quick navigation letters, when you choose JAWS letters. |
| Mark Colors in Braille | NVDA's font attribute reporting includes braille when JAWS marked bold, italic or underline. |
| Skim Reading Tool | "Allow skim reading in Say All" when JAWS rapid skim reading was on. Skim reading rules are archived. |
| Window Class Reassign | Archived and listed. Enhanced Control Support from the Add-on Store adds support for more controls. |
| Prompt Create and custom labels | Archived and listed. Custom Labels from the Add-on Store lets you label controls in NVDA. |
| Graphics Labeler (`.jgf`) | Archived. NVDA cannot recognize graphics by their pixels. |
| Frame Viewer (`.jff`, `.jfd`) | Archived. NVDA reports changing content through its dynamic content setting. |
| Custom Highlight Assign | Archived. NVDA has no color-based highlight detection. |
| Customize List View | Archived. NVDA reads all list columns. |
| Flexible Web (`FlexibleWeb.db`) | Archived. Custom Browse Mode from the Add-on Store can switch profiles in browse mode. |
| Research It | Options and rules archived. |
| Commands Search | Archived. NVDA's Input Gestures dialog has a filter box. |
| Message Center | Nothing to migrate (Freedom Scientific news). Archived. |
| Notification History | Archived. Custom Notifications from the Add-on Store chooses how notifications are read. |
| Script Manager (`.jss`, `.jsb`, `.jsh`, `.jsd`, `.jsm`) | JAWS scripts cannot run in NVDA. Your scripts are archived and listed in the report, with the commands they add. |

Dictionary rules in more detail:

- Plain words become whole-word entries in NVDA's default dictionary.
- JAWS root words such as `reposition*` keep matching every word that starts with the root.
- Rules for another language are left out.
- Rules for one synthesizer go into NVDA's voice dictionary for the voice you migrate to.
- Rules that only play a sound are listed, because NVDA dictionaries cannot play sounds.
- Freedom Scientific's own rules are only added if you ask.

## Voices, voice profiles and voice aliases

The assistant reads every JAWS voice profile, yours and the shared ones. Your changes are layered over JAWS's defaults, as JAWS does. Each profile's contexts are read: Global, PC cursor, JAWS cursor, keyboard, menus and dialogs, and messages.

- **Your JAWS voice** becomes NVDA's voice. The assistant looks for the NVDA synthesizer that speaks the same voices. It prefers a native NVDA add-on driver, such as IBMTTS for Eloquence, then matching SAPI 5 or OneCore voices, in your JAWS language. Eloquence and IBM ViaVoice are looked for both as NVDA add-ons and as SAPI 5 voices. JAWS person names (Reed, Shelley, Glen, Rocko, Grandma and the others) select the matching voice or variant.
- **Rate, pitch and volume** are converted from each JAWS synthesizer's own units into NVDA's 0 to 100. Eloquence uses 0 to 100 already. SAPI 5 uses 0 to 20. DECtalk uses words per minute, and so on.
- **Punctuation level** and **capital pitch change** are migrated too.
- **Every other voice profile** with an NVDA synthesizer on this computer is saved as that synthesizer's NVDA settings. When you switch NVDA to it later, your JAWS settings for it are already there.
- **Voice aliases** (for example HeadingLevel1Voice, LinkVoice, QuotationVoice, and the Rent-A-Crowd aliases) are migrated into ClassicSpeech, as described next.

## ClassicSpeech

When [ClassicSpeech](https://github.com/joshknnd1982/classicspeech-nvda) is installed, the assistant also copies these into it, in ClassicSpeech's own formats:

- **Voice Profiles.** Each JAWS context becomes a ClassicSpeech category:
  - PC cursor becomes Focus and navigation.
  - JAWS cursor becomes Review and object navigation, and Mouse.
  - Keyboard becomes Keyboard entry.
  - JAWS messages become System and notifications.
  - This is done for every migrated voice profile's NVDA synthesizer.
- **Speech and Sound Schemes.** Every JAWS scheme becomes a ClassicSpeech scheme with its sounds, including SayAll Text With Sounds, Web RentACrowd, ProofReading and your own schemes:
  - JAWS control types become NVDA roles, including heading levels and landmarks.
  - JAWS control states become NVDA states.
  - Text attributes become formatting items (bold, italic, spelling errors, revisions, comments...).
  - Sounds are copied with the scheme.
  - Compressed JAWS sounds are converted so NVDA can play them.
  - The scheme JAWS used can be turned on in ClassicSpeech.
- **Voice aliases.** Each alias becomes a ClassicSpeech voice for every migrated synthesizer:
  - The alias's person becomes the matching NVDA voice or variant.
  - Its pitch and rate changes are applied to the migrated voice.
  - Aliases list fallbacks after a semicolon, and the first person the NVDA synthesizer has is used, as JAWS does.
  - Rent-A-Crowd's links, headings and quotations keep their different voices.
  - A "JAWS voice aliases" scheme gives every alias its natural item, even aliases no JAWS scheme used.
- **Verbosity, number and text processing.** JAWS Beginner, Intermediate and Advanced verbosity become ClassicSpeech's verbosity profiles. Number processing, single digits, currency, dates, mixed case, repeated characters and new line announcements are also copied.

Each migration also saves `.classicspeech-voices` and `.classicspeech-scheme` files. ClassicSpeech's Import buttons can bring those into ClassicSpeech on another computer.

Without ClassicSpeech, everything NVDA itself supports is migrated. The report lists what ClassicSpeech would add.

## Sounds

The assistant finds every JAWS sound (`.wav`), in your settings and the shared settings, and asks whether JAWS sound effects should replace NVDA's sounds:

| NVDA sound | JAWS sound used |
| --- | --- |
| Switching to browse mode | Leaving forms mode (boink1, or the sound you chose in JAWS) |
| Switching to focus mode | Entering forms mode (boink2, or your choice) |
| Spelling error | Proofing error (BuzzerShort, or your choice) |
| Auto-suggestions appear and close | Auto-complete list opens and closes |
| Screen curtain on and off | Screen Shade blinds down and up |
| Remote Access connected, controlled, joined and disconnected | Tandem connect and disconnect (or your choice) |
| Error written to the NVDA log | Error buzzer |

NVDA's own sound files, in NVDA's program folder, are never changed. The chosen JAWS sounds are copied into the assistant's folder and played in their place while JAWS sound effects are on. Turn them on or off with NVDA+Shift+J then S, or in NVDA's Settings, JAWS Migration Assistant. NVDA's original sounds are also copied into every backup.

## Keyboard commands

The assistant reads JAWS's default key map and turns keystrokes for commands NVDA also has into NVDA input gestures. It uses both your changes and the shared key map. Examples:

- Reading the current line, word or character, Say All, and reading sentences.
- The window title, status line, focus, time and date.
- The elements list and the Find commands.
- Reading table rows and columns.
- Speech rate and punctuation level.

Keystrokes for JAWS's desktop or laptop layout are used according to the layout you used in JAWS, and NVDA's layout is set to match.

- Before any gesture is added, gestures.ini is backed up.
- Keystrokes NVDA already uses for the same command are left alone.
- Keystrokes NVDA uses for something else stay NVDA's, unless you choose otherwise.
- JAWS quick navigation letters can be used in browse mode, so R moves to regions and A to radio buttons, as in JAWS.
- Layered keystrokes (such as INSERT+SPACE, then a letter) and braille display keys are listed in the report. NVDA has no layered keys of its own.
- Application key maps and JAWS-only commands are listed too.

To learn NVDA, use the JAWS keystroke helper: press NVDA+Shift+J, then K, then a JAWS keystroke. NVDA tells you:

- what that keystroke did in JAWS, from JAWS's own documentation;
- the NVDA command that does the same, and its keystroke;
- what the keystroke now does in NVDA.

## The assistant's own commands

Press NVDA+Shift+J, then:

| Key | Command |
| --- | --- |
| M | Open the JAWS Migration Assistant |
| P | Turn the JAWS settings profile on or off |
| K | JAWS keystroke helper: hear what a JAWS keystroke does in NVDA |
| S | Turn JAWS sound effects on or off |
| R | Open the last migration report |
| B | Restore NVDA settings from a backup |
| U | Check for updates |
| I | Hear the JAWS, Windows and NVDA versions on this computer |
| H or F1 | List these commands |

Any other key, or Escape, leaves the layer. Every command is also in NVDA's Input Gestures dialog, under JAWS Migration Assistant, where you can give it its own keystroke. NVDA+Shift+J itself can be changed there too.

The NVDA menu, Tools, JAWS Migration Assistant has the same actions. So does the JAWS Migration Assistant category of NVDA's Settings dialog. That category also has:

- automatic update checks;
- turning on the JAWS settings profile when NVDA starts;
- JAWS sound effects;
- the list of applications where NVDA sleeps.

## Recommended add-ons

The assistant checks whether four Add-on Store add-ons are installed. It lets you choose which to install, and explains what happens without each:

| Add-on | What it adds | Without it |
| --- | --- | --- |
| Enhanced Control Support | Support for controls NVDA does not recognize, like JAWS Window Class Reassign | Controls JAWS read only because of a reassignment may be silent or "unknown" in NVDA |
| Custom Labels | Your own labels for unlabeled controls, like JAWS Prompt Create and custom labels | Controls you named in JAWS are read without your names; the report lists them |
| Custom Browse Mode | An NVDA profile that turns on in browse mode, like JAWS's separate web settings | Browse mode uses the same settings as everything else, as NVDA normally does |
| Custom Notifications | How notifications are read: full text, just the application, speech or braille | NVDA keeps reading every notification in full |

The add-ons you choose are:

1. looked up in NVDA's Add-on Store catalog, choosing the newest stable version that works with your NVDA;
2. downloaded and checked against the Add-on Store's SHA-256 checksum;
3. installed with NVDA's own installer.

They start after NVDA restarts.

## Backups and restoring

Before every migration, the assistant backs up:

- nvda.ini, gestures.ini and profileTriggers.ini;
- every configuration profile, speech dictionary and user symbol file;
- ClassicSpeech's settings and schemes;
- the assistant's own record of sounds and sleeping applications;
- NVDA's own sound files.

If the migration fails, the backup is put back and NVDA reloads its saved settings, so NVDA is left as it was.

To undo a migration later, open the NVDA menu, Tools, JAWS Migration Assistant, Restore NVDA settings from a backup, or press NVDA+Shift+J then B. Choose a backup and press Restore. Your current settings are backed up first, so a restore can be undone too. Files the migration created, such as the JAWS settings profile and the ClassicSpeech schemes, are removed. The fifteen newest backups are kept.

## JAWS is never changed

- JAWS files are only ever opened for reading.
- Every file the assistant writes goes through a check that refuses any location inside a JAWS program or settings folder. So even a mistake in the assistant cannot change JAWS.
- The assistant does not uninstall, update or reconfigure JAWS, and does not stop JAWS if it is running.
- Your JAWS settings stay where they are. A copy is also kept with NVDA's settings.

When the migration finishes, the assistant tells you that you can now uninstall JAWS yourself if you wish, from Windows Settings, Apps, Installed apps. You might keep JAWS for a while to compare, or for programs you still need it for.

## Adapting to each computer

Nothing about the computer is assumed. The System Check reports, and the migration adapts to:

- **Windows:** version, build and architecture (x64 or ARM64), and roaming or redirected profiles.
- **NVDA:** version, and whether it is an installed, portable or Microsoft Store copy. Also whether its settings folder can be written, the free disk space, secure screens, and existing profiles.
- **JAWS:**
  - every version found in the registry or on disk (JAWS 18 and later, including several side by side);
  - settings left behind by an uninstalled JAWS;
  - every settings language (enu, deu, fra, esn...);
  - whether JAWS is running;
  - personal and shared settings folders, including missing or unreadable ones;
  - files in UTF-8, UTF-16 or the Windows code page.
- **Speech:** every synthesizer NVDA can load, and every SAPI 5 voice (32-bit and 64-bit, including voices SAPI makes up at run time), OneCore voice and Speech Platform voice.
- **Add-ons:** ClassicSpeech and the recommended add-ons, including disabled ones and ones waiting for a restart.

## Leasey

If Hartgen Consultancy's Leasey is installed, the assistant ignores all Leasey settings. Leasey is detected from:

- its entry in Add or Remove Programs;
- its program and data folders;
- Leasey files in the JAWS settings.

Leasey files, settings sections and keystrokes are left out of the migration and the archive, and the report says what was found.

## Updates

The assistant checks [its GitHub releases](https://github.com/joshknnd1982/jawsMigrator/releases) for a newer version at most once a day, a little after NVDA starts. It only speaks up when there is one. You can also check any time with NVDA+Shift+J then U.

The update dialog shows the release notes in a box you can read line by line. It offers to download the new version. The download must match the release's SHA-256 checksum. NVDA's own installer then asks you to confirm, installs it, keeps your settings, backups and reports, and offers to restart. This is the same updater ClassicSpeech uses. Automatic checks can be turned off in NVDA's Settings, JAWS Migration Assistant.

## Where things are kept

Everything the assistant writes is inside NVDA's settings folder, usually `%APPDATA%\nvda`:

| Location | What |
| --- | --- |
| `jawsMigrator\backups\<date>` | Backups of NVDA's settings |
| `jawsMigrator\archive\JAWS <version> <date>` | Copies of your JAWS settings (and the shared settings, when chosen) |
| `jawsMigrator\migrations\<date>` | The report (`report.html`, `report.txt`), the JAWS index (`jaws-index.json`, `jaws-index.txt`), gestures.ini as it was, and ClassicSpeech voice and scheme files |
| `jawsMigrator\sounds` | JAWS sounds that replace NVDA's |
| `jawsMigrator\state.json` | The assistant's own settings |
| `profiles\JAWS settings.ini`, `profiles\JAWS - program.ini` | Migrated NVDA configuration profiles |
| `ClassicSpeech\Schemes\<scheme> (from JAWS)` | Migrated ClassicSpeech schemes |

## Limits

- JAWS scripts cannot run in NVDA, and there is no automatic translation. Custom scripts are archived and listed.
- NVDA has no layered keystrokes, frames, graphics labels, color-based highlight detection, Flexible Web, Research It or list view column customization. Those settings are archived and listed.
- Rates and pitches are converted by scale, anchored at each JAWS synthesizer's default, so a voice may need a small adjustment afterwards.
- JAWS voices from synthesizers with no NVDA equivalent on the computer (for example old hardware synthesizers) cannot be used. The report says which ones.
- NVDA speech dictionaries are not per application. Rules from JAWS application dictionaries go into the default dictionary; you can leave them out.
- Braille tables are chosen automatically for English only. For other languages, choose the table in NVDA's Braille settings.

## Building from source

The add-on is plain Python. To build it you need Python 3.10 or later and the `markdown` package (`pip install markdown`), which turns this README into the add-on's help page.

```bash
python build.py
```

This writes `dist/jawsMigrator-<version>.nvda-addon` and its `.sha256` checksum file. The version comes from `addon/manifest.ini`.

Tests:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Two further scripts need wxPython and a computer with JAWS or JAWS settings. They change nothing outside a temporary folder:

- `tests/gui_smoke.py` walks through every step of the wizard.
- `tests/integration_migration.py` runs a whole migration into an imitation NVDA, checks what it wrote, then restores it.

## Credits

- Written by Josh Kennedy, with Claude.
- The update check and update dialog follow [ClassicSpeech](https://github.com/joshknnd1982/classicspeech-nvda)'s, also under the GPL.
- JAWS, Leasey, Eloquence and other product names belong to their owners. This add-on is not affiliated with Freedom Scientific, Vispero or Hartgen Consultancy.
