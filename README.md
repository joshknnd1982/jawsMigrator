# JAWS Migration Assistant for NVDA

An NVDA add-on that brings a JAWS user's settings into NVDA. It reads everything JAWS knows about you:

- Settings Center options.
- Voice profiles and voice aliases.
- Speech and sound schemes.
- Dictionaries and punctuation.
- Keyboard assignments and quick navigation keys.
- Sounds, and settings for single applications.

Each one is mapped to its closest NVDA equivalent. You choose exactly which settings, schemes, voice profiles, voice aliases and keyboard layouts come over. Anything NVDA can't use is kept in an archive and explained in a report.

Before anything changes, NVDA's settings, every add-on and the add-ons' own settings are backed up, so you can always go back to how NVDA was.

JAWS itself is never changed. The assistant only reads JAWS files. It never writes to, updates, reconfigures or uninstalls JAWS. When the migration is finished, it tells you that you can uninstall JAWS yourself if you want to.

- Version: 1.2
- Requires: NVDA 2026.1 or later (tested with NVDA 2026.2) on Windows 10 22H2 or Windows 11
- Works with: JAWS 18 and later, in any JAWS language, including settings left behind by an uninstalled JAWS
- License: GNU General Public License, version 2 or later

## Contents

- [What it does](#what-it-does)
- [Installing](#installing)
- [Using the assistant](#using-the-assistant)
- [Choosing what to import](#choosing-what-to-import)
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
3. **Lets you choose** your settings, the shared settings, or both, layered as JAWS layers them. It also lets you choose what to migrate, down to single settings, schemes, voice profiles, voice aliases and keyboard layouts, and where it goes.
4. **Migrates** into a separate NVDA configuration profile named "JAWS settings" (recommended), or into NVDA's normal configuration.
5. **Backs up NVDA first**: its settings, every add-on and the add-ons' own settings. If anything goes wrong, the settings are put back automatically. You can restore any backup later, add-ons included.
6. **Writes a report** of everything that changed, everything kept for NVDA, and everything JAWS had that NVDA has no equivalent for.

## Installing

1. Download `jawsMigrator-1.2.nvda-addon` from the [releases page](https://github.com/joshknnd1982/jawsMigrator/releases).
2. Press Enter on the file. NVDA asks you to confirm, installs the add-on and offers to restart.
3. A few seconds after NVDA starts, the assistant checks the computer once and offers to migrate. After that it only runs when you ask.

## Using the assistant

Open it from the NVDA menu: Tools, JAWS Migration Assistant, Migrate JAWS settings to NVDA. Or press NVDA+Shift+J, then M.

The assistant is a single dialog with Back, Next and Cancel buttons. Each step is a labeled group. NVDA says the step name and puts you on the step's first control. Long text is in read-only boxes you can read line by line. Nothing changes until you press Migrate on the last step.

1. **System check.** What was found on this computer. Choose the JAWS version and settings language if there is more than one.
2. **Which JAWS settings.** Your settings and the shared settings (recommended), only yours, or only the shared ones.
3. **What was found.** A summary of every JAWS manager's files and entries, JAWS's synthesizers and their NVDA equivalents, and whether Eloquence or IBM ViaVoice is available. The View the full index button shows every file.
4. **Choose what to migrate.** A checklist with counts: Settings Center, voices, application profiles, sleep mode applications, dictionaries, punctuation, keyboard commands, and the archive. If you saved a choice in [JAWS Migration Assistant settings](#choosing-what-to-import), the step says so and starts from it.
5. **Where the JAWS settings go.** A separate profile, or NVDA's normal configuration. For a profile, you can turn it on every time NVDA starts, and right away.
6. **Voices.** Which NVDA synthesizer and voice replaces your JAWS voice, and which JAWS voice profiles to migrate.
7. **ClassicSpeech** (only when it is installed). Which JAWS speech and sound schemes to copy, which one to turn on, and whether to copy voice profiles, voice aliases, and verbosity, number and text settings.
8. **Sound effects** (only when ClassicSpeech is installed). Whether JAWS sounds play in place of NVDA's sounds, with the list of which JAWS sound replaces which NVDA sound, and whether to copy every JAWS sound into ClassicSpeech.
9. **Keyboard commands.** Whether JAWS keystrokes become NVDA input gestures, which [JAWS keyboard layouts](#keyboard-layouts) to bring over (desktop, laptop and so on), NVDA's keyboard layout afterwards, whether to use JAWS quick navigation letters in browse mode, and whether JAWS keystrokes may replace NVDA's own. The list shows every keystroke that will be added.
10. **Recommended add-ons.** Which of the four recommended add-ons to install, what each does, and what happens if you don't.
11. **Ready to migrate.** A summary of what will happen. Press Migrate.

Every checklist in the assistant has Select all and Select none buttons.

Progress is spoken as it happens. The last step shows the result. It has buttons to open the report, open the folder with the migration's files, and restart NVDA when a restart is needed.

## Choosing what to import

To pick exactly which JAWS items come over, open the NVDA menu, Preferences, JAWS Migration Assistant settings. You can also press NVDA+Shift+J then O, use the NVDA menu, Tools, JAWS Migration Assistant, Choose what to import, or use the button in NVDA's Settings, JAWS Migration Assistant.

The dialog reads your JAWS settings, which takes a few seconds, and lists every item with a check box:

- **JAWS settings (Settings Center):** each option that has an NVDA equivalent, with the JAWS file and option it comes from.
- **Speech and sound schemes:** each scheme, with its number of sounds and voices.
- **Voice profiles:** each JAWS voice profile and the NVDA synthesizer it becomes.
- **Voice aliases:** each alias (LinkVoice, HeadingLevel1Voice, the Rent-A-Crowd aliases...) with what it does in each voice profile.
- **Keyboard settings and layouts:** keyboard options such as typing echo, the NVDA key and the keyboard layout, JAWS keystrokes as NVDA gestures, each [JAWS keyboard layout](#keyboard-layouts), and quick navigation letters.
- **Dictionaries, punctuation, sounds and applications:** your dictionary rules, Freedom Scientific's rules, punctuation, JAWS sounds in place of NVDA's, all JAWS sounds copied into ClassicSpeech, ClassicSpeech voices and settings, the archive, each application's profile, and each application where NVDA should sleep.

The dialog's controls:

| Control | What it does |
| --- | --- |
| Show | Lists everything, or one kind of item |
| Items to import | Check the items you want; Space checks or unchecks one |
| Select all, Select none | Check or uncheck every item shown, so a whole kind can be turned on or off at once |
| Import the selected items now | Saves your choice and opens the migration assistant |
| Check for updates | Looks for a newer version of the assistant on GitHub |
| Open NVDA's Input Gestures dialog | Opens NVDA's Input Gestures dialog, to see or change keystrokes |
| Save and close | Saves your choice |
| Close without saving | Closes; if you changed anything, asks whether to save it |

Items this computer can't use (for example a voice profile for a synthesizer NVDA doesn't have, or schemes when ClassicSpeech isn't installed) say why and can't be checked. The choice is saved and used by every migration. Items that appear later, for example after you change JAWS, are imported unless you turn them off. The dialog never changes NVDA or JAWS; only a migration does.

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

JAWS sounds play through [ClassicSpeech](https://github.com/joshknnd1982/classicspeech-nvda). Without ClassicSpeech, NVDA keeps its own sounds, and the assistant says so rather than changing anything.

### Every JAWS sound in ClassicSpeech

The assistant can copy every JAWS sound it finds (`.wav`, your own and the shared ones) into ClassicSpeech, as a scheme named "JAWS Sounds (from JAWS)":

`%APPDATA%
vda\ClassicSpeech\Schemes\JAWS Sounds (from JAWS)\Sounds`

Sounds JAWS keeps compressed are converted so NVDA can play them. Where you have your own copy of a JAWS sound, yours is used, as in JAWS. The scheme changes nothing by itself; its sounds are at hand in ClassicSpeech's Speech and Sound Schemes, for any item. Copying again later keeps what you set up in the scheme.

Do it in the migration's Sound effects step, or at any time with NVDA+Shift+J then A, or NVDA menu, Tools, JAWS Migration Assistant, Copy all JAWS sounds into ClassicSpeech.

### JAWS sounds in place of NVDA's

NVDA plays its own sounds when you switch between focus and browse mode, and for other events. The assistant can have JAWS sounds play instead:

| NVDA sound | JAWS sound used |
| --- | --- |
| Switching to browse mode | Leaving forms mode (boink1, or the sound you chose in JAWS) |
| Switching to focus mode | Entering forms mode (boink2, or your choice) |
| Spelling error | Proofing error (BuzzerShort, or your choice) |
| Auto-suggestions appear and close | Auto-complete list opens and closes |
| Screen curtain on and off | Screen Shade blinds down and up |
| Remote Access connected, controlled, joined and disconnected | Tandem connect and disconnect (or your choice) |
| Error written to the NVDA log | Error buzzer |

JAWS has no sounds for NVDA starting or exiting, or for the Remote Access clipboard, so NVDA keeps its own for those.

To switch quickly, press NVDA+Shift+J then S. The first press plays JAWS sounds; the next restores NVDA's own. The same actions are in NVDA menu, Tools, JAWS Migration Assistant (Use JAWS sounds in place of NVDA's sounds, and Restore NVDA's own sounds), and in NVDA's Settings, JAWS Migration Assistant. The migration's Sound effects step does it too.

How it works, and how to go back:

- ClassicSpeech plays a scheme's "NVDA sound" items in place of NVDA's own sounds. The assistant gives every ClassicSpeech scheme the JAWS sounds, each copied into that scheme's own Sounds folder, so the JAWS sounds play whichever scheme is active. A sound you already chose for an item in a scheme is left as it is. If ClassicSpeech's speech and sound schemes were off, they are turned on, since the sounds need them.
- NVDA's own sound files, in NVDA's program folder, are never changed. Before the JAWS sounds go in, a copy of NVDA's own sounds is kept in `jawsMigrator
vdaSounds`, and NVDA's settings, add-ons and add-on settings are backed up.
- Restore NVDA's own sounds takes out exactly what the assistant added, and turns ClassicSpeech's schemes off again if the assistant had turned them on. Sounds you changed in ClassicSpeech since are left as you set them. The JAWS sounds copied into "JAWS Sounds (from JAWS)" stay.
- Restoring a backup also puts everything back as it was.

Some NVDA sounds only play when their NVDA option is on. For example, focus and browse mode sounds need "Audio indication of focus and browse modes" in NVDA's Browse Mode settings. NVDA plays the logged error sound only in its test versions, unless you change that in its Advanced settings.

Version 1.1 of the assistant played JAWS sounds by itself. In 1.2 they play through ClassicSpeech, and 1.1's way is turned off. If you used it, turn JAWS sounds on again with NVDA+Shift+J then S.

## Keyboard commands

The assistant reads JAWS's default key map and turns keystrokes for commands NVDA also has into NVDA input gestures. It uses both your changes and the shared key map. Examples:

- Reading the current line, word or character, Say All, and reading sentences.
- The window title, status line, focus, time and date.
- The elements list and the Find commands.
- Reading table rows and columns.
- Speech rate and punctuation level.

### Keyboard layouts

JAWS has a keyboard layout for each kind of computer keyboard. Each layout adds its own keystrokes to the ones all layouts share. The assistant finds the layouts in your JAWS key map and lets you choose which to bring over. Its keystrokes become gestures of the matching NVDA keyboard layout, so they work whenever NVDA uses that layout:

| JAWS layout | JAWS key | NVDA keyboard layout |
| --- | --- | --- |
| Desktop | Insert | Desktop |
| Laptop | Caps Lock | Laptop |
| Classic Laptop (the older Alt+letter layout) | Insert | Laptop |
| Kinesis | Insert | Desktop |

Layouts of other JAWS versions and languages are found the same way. Freedom Scientific notetaker layouts (PAC Mate) are left out.

- The layout your JAWS uses is chosen at first. Choose more to have your JAWS keystrokes on another kind of keyboard too. For example, choose Desktop and Laptop if you switch NVDA between them.
- When two chosen JAWS layouts put different commands on the same keystroke for the same NVDA layout, the layout your JAWS uses wins. The report lists the others.
- NVDA's keyboard layout follows the JAWS layout you used, or the layouts you chose. You can also pick Desktop, Laptop, or keep NVDA's current layout.
- Caps Lock becomes an NVDA key when the Laptop layout's keystrokes come over, as it was the JAWS key there. The Insert keys follow your JAWS key setting.
- Classic Laptop uses Alt with letters, which takes those keystrokes away from programs. Choose it only if you used it in JAWS.

### Everything else about keystrokes

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
| O | JAWS Migration Assistant settings: choose which JAWS items to import |
| G | Open NVDA's Input Gestures dialog |
| P | Turn the JAWS settings profile on or off |
| K | JAWS keystroke helper: hear what a JAWS keystroke does in NVDA |
| S | Play JAWS sounds in place of NVDA's sounds, or restore NVDA's own (needs ClassicSpeech) |
| A | Copy all JAWS sounds into ClassicSpeech |
| R | Open the last migration report |
| B | Restore NVDA settings from a backup |
| U | Check for updates |
| I | Hear the JAWS, Windows and NVDA versions on this computer |
| H or F1 | List these commands |

Any other key, or Escape, leaves the layer. Every command is also in NVDA's Input Gestures dialog, under JAWS Migration Assistant, where you can give it its own keystroke. NVDA+Shift+J itself can be changed there too.

The NVDA menu, Tools, JAWS Migration Assistant has the same actions, and the NVDA menu, Preferences, has JAWS Migration Assistant settings. The JAWS Migration Assistant category of NVDA's Settings dialog has buttons to choose which JAWS items to import, open NVDA's Input Gestures dialog, use JAWS sounds in place of NVDA's, restore NVDA's own sounds, copy all JAWS sounds into ClassicSpeech, open the assistant, restore a backup, open the last migration report and check for updates. It also says whether JAWS sounds or NVDA's own are playing. That category also has:

- automatic update checks;
- turning on the JAWS settings profile when NVDA starts;
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

Before every migration, and before every restore, the assistant backs up NVDA's whole settings folder:

- nvda.ini, gestures.ini and profileTriggers.ini, with the settings add-ons keep in nvda.ini;
- every configuration profile, speech dictionary and user symbol file;
- ClassicSpeech's settings and schemes;
- every installed add-on, including ones waiting for a restart;
- the settings and data add-ons keep in their own files and folders, such as downloaded voices;
- NVDA's record of which add-ons are enabled or disabled;
- the assistant's own record of sounds and sleeping applications;
- NVDA's own sound files.

Left out is only what NVDA downloads or builds again by itself: the Add-on Store's cache, NVDA update downloads and compiled Python files. The assistant's own add-on and backups aren't copied into backups.

The first backup copies everything, which can take a minute and a few gigabytes when many add-ons are installed. Later backups share every unchanged file with the previous one (as a hard link), so they take seconds and almost no space. The wizard's last step says how much will be copied. If the disk doesn't have room, nothing is migrated.

If the migration fails, the backup is put back and NVDA reloads its saved settings, so NVDA is left as it was.

To undo a migration later, open the NVDA menu, Tools, JAWS Migration Assistant, Restore NVDA settings from a backup, or press NVDA+Shift+J then B. Choose a backup and press Restore. Before restoring, the assistant tells you what will happen to each add-on. Then:

1. Your current settings and add-ons are backed up first, so a restore can be undone too.
2. Settings files that changed are put back, each checked against the backup's SHA-256 first. Files the migration created, such as the JAWS settings profile and the ClassicSpeech schemes, are removed.
3. Add-ons go back the way NVDA itself installs and removes them. Add-ons installed after the backup, such as the recommended ones, are removed. Add-ons that were removed or updated since are reinstalled from the backup. Each add-on is enabled or disabled as it was, and add-on settings are put back.
4. NVDA reloads its settings. It offers to restart, which finishes putting back the add-ons.

The backup made before your first migration is kept for good, as your NVDA before any JAWS migration. Of the others, the fifteen newest are kept. Backups made by version 1.0 hold NVDA's settings only; restoring one leaves add-ons as they are.

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
| `jawsMigrator\backups\<date>` | Backups of NVDA's settings, add-ons and add-on settings (`backup.json` lists every file and add-on) |
| `jawsMigrator\archive\JAWS <version> <date>` | Copies of your JAWS settings (and the shared settings, when chosen) |
| `jawsMigrator\migrations\<date>` | The report (`report.html`, `report.txt`), the JAWS index (`jaws-index.json`, `jaws-index.txt`), gestures.ini as it was, and ClassicSpeech voice and scheme files |
| `jawsMigrator
vdaSounds\<NVDA version>` | A copy of NVDA's own sounds, kept before JAWS sounds are used in their place |
| `jawsMigrator\state.json` | The assistant's own settings, including your choice of JAWS items to import |
| `profiles\JAWS settings.ini`, `profiles\JAWS - program.ini` | Migrated NVDA configuration profiles |
| `ClassicSpeech\Schemes\<scheme> (from JAWS)` | Migrated ClassicSpeech schemes |
| `ClassicSpeech\Schemes\JAWS Sounds (from JAWS)\Sounds` | Every JAWS sound, ready for ClassicSpeech |

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

`tests/plugin_smoke.py` needs wxPython. It loads the add-on as NVDA does, with real menus, and checks the NVDA menu items, the Settings panel and the NVDA+Shift+J commands.

Three further scripts need wxPython and a computer with JAWS or JAWS settings. They change nothing outside a temporary folder:

- `tests/gui_smoke.py` walks through every step of the wizard.
- `tests/settings_dialog_smoke.py` drives JAWS Migration Assistant settings (filters, Select all, Select none, saving) and checks that the wizard and its keyboard layouts follow the saved choice.
- `tests/integration_migration.py` runs a whole migration into an imitation NVDA, checks what it wrote, then restores it, add-ons included.

## Credits

- Written by Josh Kennedy, with Claude.
- The update check and update dialog follow [ClassicSpeech](https://github.com/joshknnd1982/classicspeech-nvda)'s, also under the GPL.
- JAWS, Leasey, Eloquence and other product names belong to their owners. This add-on is not affiliated with Freedom Scientific, Vispero or Hartgen Consultancy.
