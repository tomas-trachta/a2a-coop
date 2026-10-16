# a2a-coop dashboard design

Goal #3 · Design handoff from Codex to Claude · 2026-10-16

## Intent and scope

Make the operator's next action clear: choose a goal, follow the agents' work, and answer questions. Improve the current uncommitted native Tkinter dashboard, preserving its existing store, MCP, CLI, polling and launch semantics. Use tkinter/ttk only. Claude owns implementation in src/a2a_coop/gui.py and dialogs.py, focused tests/test_gui.py changes, and README.md dashboard documentation. A small shared theme module is optional if it avoids circular imports. Codex owns this document and design review. Do not revert unrelated working-tree changes.

## Layout

Default window 1360 × 860 logical pixels; minimum 1040 × 680. Keep DPI awareness and use named Tk fonts rather than a hard-coded font family. Root grid: header, expanding workspace, quiet status line. Header: a2a-coop title, subtitle 'Your agents, working together', right-aligned primary 'New goal…' and secondary 'New agent…'. Keep the Coop menu and existing shortcuts.

Workspace is a horizontal PanedWindow with three resizable panes. Initial widths at default size: left 260, center roughly 710, right 340 (minus outer padding/gutters). At minimum size aim for left 220, center 480, right 280. Do not impose requested Treeview widths that force the window larger than the declared minimum. Use weight on the center so extra room primarily helps conversation. Outer padding 16, pane gaps 12, card padding 12. Right and left subpanes may be vertically resizable. No fixed screen coordinates or custom canvas controls.

    ┌ a2a-coop   Your agents, working together            New goal…   New agent… ┐
    │ GOALS                    │ #3 Improve the design     │ QUESTIONS FOR YOU 2 │
    │ Show closed              │ Active · 1/2 tasks done   │ claude · Goal #3    │
    │ #3 Improve… Active  ●2   │                          │ Full question…      │
    │ #2 Stealth  Active       │ claude → codex     20:10  │ [Your answer      ] │
    │ General                  │ Message body…            │ Dismiss    Answer   │
    │                          │                          ├─────────────────────┤
    ├──────────────────────────┤ codex → everyone   20:12 │ GOAL DETAILS        │
    │ TEAM                  2  │ Message body…            │ Description…        │
    │ claude     Listening     │                          │ 1 of 2 tasks done   │
    │ codex      Busy          │                          │ Task       Assignee │
    │ Selected agent role      │                          │ Design…    codex    │
    │ Full current status…     ├──────────────────────────┤ Implement… claude   │
    │ Start  Add…  Remove…     │ Message about Goal #3    │ Selected task…      │
    │                          │ To everyone [text] Send  │ Pause Done Cancel…  │
    └──────────────────────────┴──────────────────────────┴─────────────────────┘

The sketch shows regions, not exact text sizes. Actual controls must wrap and resize safely.

### Left: navigation and team

Goals occupy the upper portion (about 55%). Header 'Goals'; 'Show closed' is a secondary checkbox. New goal is available in the global header/menu, so omit a redundant large toolbar. Compact goal table: title, status, unread badge. Keep done/total data but move the visible count to the selected-goal summary if four columns do not fit. Include General. Show explicit status words; selected row has a blue tint. Long goal titles are readable in the center title and details. Preserve latest-open-goal startup, per-goal unread counts, and Show closed semantics.

Team occupies the lower portion. Compact two-column list: Agent and Presence. Preserve presence text and distinct color; avoid coloring whole rows when it reduces name contrast. Below it, a selectable, wrapping, vertically scrollable detail area shows the selected agent's provider, role, and full status. This is where long status updates become readable. Select the first agent initially if there is one; retain selection across refresh. Start / Add… / Remove… in a compact row; Start and Remove disabled without selection. Keep double-click/Enter launch, running-copy confirmation, starting grace and removal confirmation. Empty team: 'No agents yet. Add an agent to get started.'

### Center: selected-goal conversation

Use a white card. Header has a strong wrapping goal title ('#3 Improve the design of a2a-coop'), followed by smaller status and done/total text. General gets 'General conversation' and 'Messages without a goal'. Keep full title available and do not let an unbounded title consume the workspace; a two-line header with full title also in scrollable details is acceptable. The chat is selectable/copyable read-only text with word wrap, a vertical scrollbar and no raised border. Retain sender → recipient and timestamp, meaningful sender colors, subdued event lines, warm question highlighting, and full bodies. Use 12px paragraph spacing, body indent about 12px and comfortable line spacing; native Text tags are enough, do not create bubble widgets for every message.

Place the ordinary composer inside this center card, separated from chat by a subtle rule and padding. Above the input show 'Message about Goal #3' (or 'Message in General'). Row: To combobox, expanding single-line entry, blue Send. Keep Enter to send and retain draft on failure. This label must update whenever selection changes, and the stored goal_id must match it. This iteration keeps the existing single-line input and existing goal-switch draft behavior. Existing auto-scroll must not pull the operator away from older messages during polling. No Markdown renderer, search or new persistence required.

### Right: operator attention and goal inspector

Questions stay above goal details, visible globally regardless of selected goal. Header 'Questions for you (N)' uses amber text/background only when pending. Compact list shows asker and prompt preview; full selected prompt below includes question ID and its goal ID or General, and is selectable and vertically scrollable. Do not hide the full prompt in a clipped Label. Answer Entry has a visible 'Your answer' label and its own primary Answer plus quiet Dismiss. Keep Ctrl+R, Enter to answer, bell on newly arrived questions, window-title count, disabled empty state, and question-specific routing. Explicitly state 'No open questions. Agents will ask here when they need you.' when empty. The empty panel should be modest in height, leaving more room for tasks; a fixed reasonable minimum plus sash resizing is acceptable.

Retain selected question across polls. If selection changes while an unsent answer exists, clear it (or keep drafts keyed by question ID); never silently carry one question's draft to another. New questions must not steal focus or overwrite an answer being typed.

Goal details: section heading, scrollable/selectable full title and description, done/total summary, task list with explicit state and assignee, and scrollable selected-task description/result. Keep state marker plus word (Todo, In progress, Blocked, Done), not glyph alone. Long task title/description/result must be readable in details even when the list truncates. Preserve task and text selections/scroll while unchanged data refreshes. General has 'Select a goal to see its tasks' and disables goal actions. No task editing UI in this iteration.

Goal actions belong at the bottom of the inspector: Pause or Resume as appropriate, 'Mark done', and secondary 'Cancel goal…'. Keep existing enablement rules and user ownership of goal closure. Since cancel is now a secondary action with an ellipsis, ask a native confirmation naming the goal before applying it; cancelling that dialog changes nothing. Do not add deletion or irreversible controls.

## Visual system

A calm light workspace: window background #F3F5F9; cards/input surfaces #FFFFFF; primary text #182230; secondary text #526174; borders #D6DEE8; primary blue #2457C5; primary hover #1D46A0; selected row background #E7EEFF with dark text. Listening/success #21633B; busy/question foreground #8A4B08; question background #FFF4DB; stale/error #B42318; offline uses secondary text. Maintain readable foregrounds in selected/disabled states. Presence and task status always have text as well as color. Participant colors may keep the current deterministic palette if legible on white. Do not color all body text.

Use ttk's clam theme where available so backgrounds, selected rows and button styles are consistent across platforms, with a safe fallback. Define named styles/tokens once and reuse in dialogs; do not scatter literal palettes. Body uses platform default UI font at an equivalent of 10–11pt, section titles bold, main title 16–18pt. Keep visible keyboard focus and normal Tab traversal. Buttons/entries should be approximately 30px high or follow font metrics with comfortable padding. Avoid decorative emoji, fake online indicators or external fonts/assets. 'Listening' means existing render.is_listening; use current presence rules.

Dialogs follow the same background, spacing, label hierarchy, field borders and primary button style. Preserve existing validation, focus, escape, modal behavior, directory picker, provider availability labels and shortcuts. Goal description helper text can be a muted line below a concise 'Description (optional)' label. Do not change form data semantics.

## Acceptance and verification

1. At 1360×860 and 1040×680, header actions, both composers and goal actions remain visible with no overlapping controls; panes resize and long content scrolls. Inspect the actual rendered window, including Windows DPI if available, and provide screenshots or describe any visual limits.
2. Empty coop shows useful empty states; populated coop with long goal title, multiline question, long agent status and task result lets each full value be read. No live database mutations just for screenshot fixtures: use a disposable database.
3. Goal switching updates conversation, title, composer scope, details and unread badge together; sending routes to that goal (General remains unscoped). Existing 15 GUI tests and store/CLI/protocol tests must stay green. Update old assertions to reflect intended label changes where appropriate.
4. Ordinary send and question answer remain separate. Exercise two questions belonging to different goals: answer the selected one; incoming polling does not steal the selection or lose its draft. Switching question must never send its previous draft as an answer to the new question. Add a focused regression for this behavior.
5. Agent selection retains and reveals full details on refresh, launching and confirmations behave as before. Start/Remove unavailable when no selection. Task selection reveals description/result and remains stable on unchanged polls.
6. Scrolling back in conversation and polling does not jump to bottom. Selection/copy and keyboard shortcuts work. Empty/inactive controls show disabled state; the light theme keeps selected rows and focus legible.
7. Cancel goal asks once with goal context; rejecting it leaves the goal untouched. Add a focused behavior check. Mark done, Pause and Resume retain existing semantics.
8. Run pytest and pyflakes for affected code (report any GUI skips). If native rendering cannot be verified, say so explicitly; a headless import is insufficient visual evidence.

## Handoff

The scope is one dashboard visual/UX pass with two focused interaction corrections (question draft safety and explicit cancel confirmation), not a backend redesign. If layout constraints require a different minimum size or prioritization, coordinate before changing it. Implementation can introduce small reusable helpers/theme constants; avoid a large architecture split. Claude reports changed files, verification and limitations; Codex reviews design conformance and the changed interaction paths before completion.


# Iteration 2: clearer reading and better operator messages

Operator requested a second pass on goal #3 after accepting progress. This section supersedes the matching iteration-1 layout/control details. Preserve the first iteration's palette, three-pane structure, store/MCP semantics, question draft safety and confirmations. Codex task #10 owns this design, Claude task #11 owns implementation, followed by a new Codex review task.

## A. Write useful instructions in the conversation

Replace the central single-line message Entry with a native Text input styled as a field, initially two lines high and growing to four visible lines as the draft gains newlines or wraps. Beyond four lines, scroll vertically. Keep To and Send visible alongside or below the text without squashing it at 1040px. At minimum size, put recipient and Send in a small row below the full-width input if necessary; use one consistent arrangement at both sizes if simpler. Show a muted helper 'Enter to send · Shift+Enter for a new line'. Keep the visible scope label.

Enter sends the trimmed nonempty draft, preserves internal newlines, and consumes the key (no extra newline). Shift+Enter inserts a newline and consumes the key without sending. Support normal selection, paste and undo. Empty/whitespace sends do nothing. Successful send clears the input and restores its initial height; failure keeps exact draft content and shows the existing error. Escape focuses this input as before. Preserve the existing explicit goal scope and draft behavior when changing goals. Update GUI tests to use native Text APIs; do not build an Entry-compatibility wrapper just for old tests. Question answers remain a separate Entry in this pass.

## B. Make new conversation activity discoverable

When the current conversation is scrolled back and receives new messages, retain the scroll position and display a compact center-pane button just above the composer: 'N new messages ↓'. Count newly appended timeline messages for this selected conversation (including event messages), not initial backlog and not messages in other goals. Clicking scrolls to the end and clears/hides the count. Manually scrolling to the end also clears it. When already following the end, incoming content follows as before with no badge. Changing goals resets this local count; other-goal unread badges keep their existing behavior. Use existing text/scroll callbacks safely rather than replacing autohiding scrollbar handling. Keep keyboard focus where the operator left it when activity arrives; the new button must be keyboard reachable. No smooth animation or persistent unread storage.

## C. Spend narrow-pane space on titles

In the Goals list, remove the dedicated fixed-width Status column from display (the underlying value can stay for tests/data). Display title plus a narrow unread count. Active goals use '#N Title'; paused/closed goals use 'Paused · #N Title', 'Done · #N Title', or 'Cancelled · #N Title' so exceptional states still have words and do not depend on color. Selected goal always has the full status word in the center summary. The full title is available in the Overview inspector. No icon-only replacement for paused/closed status. Keep General and Show closed semantics. Preserve existing sort/order and selection retention.

Task list displays Task plus Assignee, with the existing state marker in the Task text; remove the fixed-width State column from display to free title space. Selected-task detail retains full state word, title, assignee, description and result. Keep underlying state data if helpful. User can read every full value through the inspector. Don't reduce fonts to fit columns.

## D. Give task details room without hiding questions

Keep global Questions in the upper right with its full selected prompt and answer controls, the current empty/waiting resizing behavior, and per-question drafts. In the lower-right Goal details card, add a native ttk Notebook with two tabs:

- Overview: full selected-goal title and description in a selectable scrolling TextPanel, plus task progress. General shows the existing General guidance.
- Tasks done/total (for example, Tasks 1/3): a short task progress summary, the Task/Assignee list, and the full selected-task detail. Allow the list and detail region to share remaining height through a vertical sash or practical expanding layout. The important difference is that the goal description no longer competes with task details on this tab.

Goal actions remain outside the notebook at the bottom of the card and preserve enablement/confirmation. On initial dashboard open, default to Tasks for a goal with tasks, otherwise Overview. Thereafter preserve the operator's chosen tab across goal switches, polling and task updates. For General, temporarily select Overview and disable Tasks; restore the last chosen non-General tab when returning to a goal. All General goal actions stay disabled. Style notebook tabs with the existing tokens and a clear selected/focus treatment. Selecting a task should keep its full detail readable and retain selection across unchanged polls. Retain the current goal/task widget attributes where sensible. At minimum size with two questions and three tasks, task titles should be visibly longer than iteration 1, more than one task row should be visible in the Tasks tab, and the selected task's description/result must scroll. At default size aim for at least three rows plus useful detail space. Questions continue to be visible while Tasks is selected.

## E. Finish lifecycle polish

Cancel owned refresh/notice/idle-sash callbacks when the dashboard/root is destroyed; do not schedule new callbacks after destruction. In particular, stop the new after_idle sash reset callback from firing against a destroyed Tk command. Keep the normal refresh cadence. Avoid swallowing arbitrary exceptions. This is lifecycle cleanup of current behavior, not a refactor of the app.

## Verification for iteration 2

1. Render a populated fixture at both 1360×860 and 1040×680 with the Tasks tab selected, a multiline draft, two pending questions, and one selected task with a long description/result. Also show Overview. All controls must remain usable without overlap; show that navigation/title room improved. Retain no-live-data fixture policy.
2. Test Shift+Enter preserves a newline without sending, Enter sends a multiline body to the currently selected goal, empty draft does nothing, failed send preserves the exact text, and success resets height/content. Test actual key bindings on a mapped window if key generation in withdrawn fixtures is unreliable.
3. Test scrolled-back receipt yields the correct count without jumping, further messages increment it, clicking jump clears it, manually reaching the bottom clears it, and goal switching cannot leak the count. Messages for a different goal must not increment the center count.
4. Verify initial inspector tab choice and retained user choice across goal switches; selecting Overview survives refresh/new tasks; General temporarily selects Overview and returning restores the user's tab. Preserve question draft/selection regressions and cancellation tests.
5. Run GUI and full regression checks and lint; distinguish existing terminal-path failures and GUI skips. Test root teardown repeatedly without new invalid-command callback warnings, and inspect actual screenshots. State any rendering/DPI limits.

No task editing, dark mode, message grouping, external GUI libraries or backend/schema changes in this pass. Defer hover previews unless trivial; full-value inspector access is the primary path. Coordinate any tradeoff that weakens multiline input, unread navigation or minimum-size task readability.


## Iteration 2 addition: agent identity colors (operator message #118)

Give every agent a consistent identity color, visible in Team and conversation and when it asks a question. The existing CRC modulo palette can assign Claude and Codex the same color; replace that behavior for known agents with a per-dashboard identity-color registry. Assign distinct dark palette colors to agents at initial load (sorted names are fine), resolving collisions rather than hashing modulo without checking. Keep each assignment stable for the current dashboard lifetime, including when agents join, leave, or lists are resorted. New agents do not recolor existing agents. User and everyone retain their reserved colors; never allocate those reserved colors to agents.

Use an expanded palette of at least 12 distinct dark hues readable on white (aim for 4.5:1 contrast). If the team exceeds the palette, derive additional colors and retain explicit agent names; avoid silently giving the first two agents the same hue. Registry scope is UI memory, no schema/persistence change. Messages from historical/removed agents also retain a session assignment.

The color must be consistent for sender and recipient headers in chat, a small identity swatch next to each agent in the Team list, and question asker in the question list (swatch and/or identity-colored asker text). Solid color swatches can use Tk PhotoImage squares in the Treeview #0 column and retain references for Tk; this is code-drawn UI, no image assets/dependencies needed. Preserve explicit agent names everywhere and accessible selection/focus styling. Keep identity colors separate from listening/busy/stale/offline presence semantics: semantic words and colors remain available, and a blue identity swatch must not imply online status. Ordinary message bodies remain primary text, not fully tinted paragraphs. Team selected-agent detail can also show the identity in its name.

Add a focused check that Claude and Codex get different colors, one agent has the same color across chat sender/recipient and its Team/question identity, and adding/removing an agent does not change existing assignments. Include at least three agents and a question in the rendered fixture so differentiation is visible. No backend change or user-configurable color picker in this iteration.


# Selectable light and dark appearance (operator message #138)

Codex task #13 designs; Claude task #14 implements, then Codex reviews. This request supersedes the earlier deferral of dark mode. Keep the current layouts, interactions and agent identity behavior.

## Choice and preference

Add a compact header control with visible label 'Appearance' and a readonly combobox containing 'Light' and 'Dark'. Place it before New goal/New agent in the header; keep everything usable at 1040×680. Initial default is Light when no valid preference exists. A user choice applies immediately, without rebuilding the dashboard or restarting. No System mode or OS polling in this scope, and no new shortcut required; native Tab/arrow selection must work.

Remember choice in ui.json next to the selected coop database; default location is ~/.a2a_coop/ui.json. This is local UI state, not a coop DB/schema/MCP event. JSON stores appearance as 'light' or 'dark'. Preserve unknown keys on a successful valid-file update where practical; use an atomic same-directory replacement. A missing file or malformed/unknown appearance falls back to Light without crashing. A preference write failure leaves the chosen in-memory appearance active and shows a concise existing notice, such as 'Using dark mode for this session; could not save appearance.' Do not lose drafts or abort the app. No need to write preferences on every poll or on default initialization; only an actual choice writes them. No extra approval dialog.

All tests and screenshot fixtures must point to a temporary DB/preference directory, never change the operator's real appearance preference just to verify. Document the preference location and selector in README.

## Palettes

Keep the existing light palette and introduce immutable LIGHT/DARK palette definitions (a frozen dataclass is appropriate). Active palette is scoped to the dashboard/Tk root, rather than overwriting module globals shared by separate dashboard/test roots. The functions that configure ttk and raw Tk widgets should use the active palette. Dialogs resolve the same palette from their parent or receive it explicitly.

Dark tokens:

| Token | Value |
| --- | --- |
| Background | #0E1624 |
| Surface/card/input | #172233 |
| Text | #E5EDF7 |
| Secondary text | #A9B8CC |
| Disabled text | #778599 |
| Border | #35445B |
| Hover surface | #233149 |
| Primary/accent | #94B8FF |
| Primary hover/pressed | #B4CCFF |
| Primary disabled | #344762 |
| Primary button foreground | #101A2B |
| Disabled primary foreground | #A9B8CC |
| Selected row/text background | #294269 |
| Selected foreground | #E5EDF7 |
| Success/listening | #86D6A0 |
| Warning/busy/question heading | #F6C66D |
| Question background | #382A15 |
| Error/stale | #FDA4AF |
| Scrollbar thumb | #4B5C76 |
| Scrollbar thumb hover | #687D9E |
| User identity | #86D6A0 |
| Everyone identity | #CBD5E1 |

Primary foreground is a separate token: do not reuse Surface as button text once Surface becomes dark. Light primary button text remains white. Keep visible focus rings and readable active/disabled/selected states. Normal and secondary text, participant labels and semantic status labels should meet 4.5:1 against their actual surfaces; disabled UI need only remain recognizably disabled. Existing font sizes and spacing stay.

Dark identity palette corresponds by slot to the existing 12 light hues:

1. Blue #93B4FF
2. Orange #FDBA74
3. Violet #C4B5FD
4. Teal #5EEAD4
5. Rose #FDA4AF
6. Gold #FDE68A
7. Magenta #F0ABFC
8. Cyan #67E8F9
9. Olive #BEF264
10. Brown/peach #FDBA8C
11. Indigo #A5B4FC
12. Purple #D8B4FE

Keep the same name→identity-slot mapping when switching; only the mode-specific shade changes. Returning to Light restores the exact original colors. Derived colors beyond the palette use a lightness suitable for dark cards and maintain reasonable readability. Refresh swatches in place or regenerate/reassign them while retaining Tk references. All Team/question swatches, sender/recipient tags, agent detail names and question detail asker tags must agree immediately after every switch, including historical agents. Names remain explicit; color is supplementary to text.

## Live recoloring contract

Reconfigure shared ttk styles, root/background surfaces, headings, controls, Notebook tabs, tree headings/selected states, scrollbars, checkbox indicators and combobox popup options. Explicit Tk backgrounds/foregrounds need recoloring too: conversation, composer, overview/task/agent/question panels, selection/caret/focus colors, question highlight tags, participant tags, semantic Treeview row tags, goal tags and status notices. Existing errors must remain red/pink after switching rather than becoming ordinary secondary text. Update already-created combobox popdown listboxes as well as the option database for future ones; a list opened before switching must not keep the old palette.

Do not clear/reload chat or replace the widget tree. Preserve goal, inspector tab, question selection, task/agent selection, text selections where possible, scroll position, focus, composer draft/undo, unsent per-question drafts, unread/jump counts, and pane positions. Palette work must not send a message, answer a question, announce a coop event or modify goal/task state.

New Goal and Agent dialogs open in the selected appearance. If a dialog is already open when appearance changes programmatically, recolor it too, including goal description Text, validation error, hints and directory field. This should preserve typed form values and validation state. Modal dialogs need no independent selector. Standard OS-owned title bars, file choosers and message boxes may follow the OS appearance; do not add platform-specific shell commands/native API work for them in this pass. Style Tk menu content where supported, but do not claim control over system-owned window chrome.

## Acceptance and verification

1. On a populated dashboard, switch Light→Dark→Light and inspect all panels, controls, both inspector tabs, the question highlight, at least three agent colors, popup recipient/appearance lists and notices. Body text, identities and focus/selection remain readable. Returning to Light restores original token values/colors.
2. During the switch retain a multiline composer draft and undo, a selected question with an unsent answer, a selected task, a manually positioned sash, a scrolled-back conversation and its new-message count. Assert no messages/events/state changes are emitted by appearance selection. Do not reset tab/selection/focus to defaults.
3. Verify valid saved Dark loads at startup; absent/malformed/unknown settings safely load Light; save updates only on choice; write failure keeps the session usable and chosen palette active. Isolate paths in tests. A small preferences helper module and focused tests are appropriate; no new dependency.
4. Verify new and already-open Goal/Agent dialogs and a previously opened combobox popup recolor. Form drafts/validation survive. Include an error-state screenshot in Dark. OS-owned chrome exceptions above are acceptable and should be stated.
5. Add meaningful contrast checks for body/secondary/status/identity text against light/dark surfaces, plus primary-button foreground and selected text. Preserve existing interaction regressions. Run full suite and lint; distinguish known path failures/GUI skips.
6. Provide actual Dark screenshots at 1360×860 and 1040×680 (populated, questions/Tasks/multiline input) and a dark dialog, plus Light after switch. State OS/DPI visual limits. No light rectangles in app-owned dark surfaces, clipping or lost agent differentiation.

Expected code ownership: Claude may edit theme.py, gui.py, dialogs.py, widgets.py, add a small preferences.py and focused tests, and update README. Codex edits only DESIGN.md and performs read-only review. Coordinate deviations before weakening live retheming or retained state.
