import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Callable, Optional

from . import reading, render, theme
from .errors import CoopError
from .models import Message
from .widgets import (
    Column,
    Segment,
    TextPanel,
    add_button,
    button_row,
    card,
    field_text,
    focus_next,
    focus_previous,
    replace_selection,
    scrolled_tree,
    section_header,
    select_first,
    select_only,
    selected_iid,
    set_enabled,
    set_field_enabled,
    surface,
    sync_rows,
    wrapping_label,
)

if TYPE_CHECKING:
    from .gui import CoopDashboard

WINDOW_SIZE = (980, 680)
MINIMUM_SIZE = (640, 460)
WINDOW_PADDING = 16
LIST_WIDTH = 300
ANSWER_LINES = 4
TITLE = "Questions for you"
ANSWER_HINT = "Enter to answer  ·  Shift+Enter for a new line  ·  Esc to close"
EMPTY_HINT = "No open questions. Agents will ask here when they need you."
ASKER_COLUMN = Column("#0", "From", 96, False)
QUESTION_COLUMNS = (Column("asker", "From", 0, False, shown=False), Column("question", "Question", 180))


class QuestionsWindow(tk.Toplevel):
    def __init__(self, dashboard: "CoopDashboard", selected: Optional[int]):
        super().__init__(dashboard.root)
        self.dashboard = dashboard
        self.answering: Optional[int] = None

        self.configure_window()
        self.build()

        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda event: self.close())

        for variant in ("r", "R"):
            self.bind(f"<Control-{variant}>", lambda event: self.answer_box.focus_set())

        self.show_questions(select=selected)
        self.answer_box.focus_set()

    def configure_window(self) -> None:
        width, height = (theme.scaled(self, size) for size in WINDOW_SIZE)
        min_width, min_height = (theme.scaled(self, size) for size in MINIMUM_SIZE)

        self.title(TITLE)
        self.geometry(f"{width}x{height}")
        self.minsize(min_width, min_height)
        self.configure(background=self.dashboard.palette.background)

    def build(self) -> None:
        padding = theme.scaled(self, WINDOW_PADDING)
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=padding, pady=padding)

        panes.add(self.build_list(panes), weight=0)
        panes.add(self.build_reader(panes), weight=1)

    def build_list(self, parent: tk.Misc) -> ttk.Frame:
        frame = card(parent)
        frame.configure(width=theme.scaled(self, LIST_WIDTH))
        _, self.heading = section_header(frame, TITLE)

        self.question_list = scrolled_tree(frame, QUESTION_COLUMNS, height=8, tree_column=ASKER_COLUMN)
        self.question_list.bind("<<TreeviewSelect>>", lambda event: self.show_selected())

        return frame

    def build_reader(self, parent: tk.Misc) -> ttk.Frame:
        frame = card(parent)

        self.build_answer_area(frame)
        ttk.Separator(frame).pack(side="bottom", fill="x", pady=(12, 0))

        self.empty_hint = wrapping_label(frame)
        self.empty_hint.configure(text=EMPTY_HINT)

        self.reader = TextPanel(frame, height=10)
        self.reader.text.configure(padx=6)
        self.configure_tags()
        reading.cap_line_length(self.reader.text)

        return frame

    def build_answer_area(self, parent: tk.Misc) -> None:
        area = surface(parent)
        area.pack(side="bottom", fill="x", pady=(12, 0))

        heading = surface(area)
        heading.pack(side="top", fill="x")
        ttk.Label(heading, text="Your answer", style="Field.Card.TLabel").pack(side="left")
        ttk.Label(heading, text=ANSWER_HINT, style="Muted.Card.TLabel").pack(side="right")

        frame, self.answer_box = field_text(area, height=ANSWER_LINES)
        frame.pack(side="top", fill="x", pady=(6, 0))

        for key in ("<Return>", "<KP_Enter>"):
            self.answer_box.bind(key, lambda event: self.answer() or "break")

        self.answer_box.bind("<Shift-Return>", lambda event: replace_selection(self.answer_box, "\n") or "break")
        self.answer_box.bind("<Tab>", lambda event: focus_next(event.widget))
        self.answer_box.bind("<Shift-Tab>", lambda event: focus_previous(event.widget))

        row = button_row(area, pady=(8, 0))
        self.error = ttk.Label(row, style="Error.TLabel", background=self.dashboard.palette.surface)
        self.error.pack(side="left", fill="x", expand=True)

        self.buttons = (
            add_button(row, "Answer", self.answer, primary=True, side="right"),
            add_button(row, "Dismiss", self.dismiss, side="right", padx=(0, 6)),
        )

    def configure_tags(self) -> None:
        palette = self.dashboard.palette
        text = self.reader.text

        text.tag_configure("muted", foreground=palette.secondary)
        text.tag_configure("lead", spacing3=10)
        reading.configure_reading_tags(text, palette)

    def recolor(self) -> None:
        self.configure_tags()
        self.error.configure(background=self.dashboard.palette.surface)
        self.dashboard.recolor_identity_tags(self.reader.text)
        self.show_questions(force=True)

    def present(self) -> None:
        self.deiconify()
        self.lift()
        self.answer_box.focus_set()

    def show_questions(self, select: Optional[int] = None, force: bool = False) -> None:
        questions = list(self.dashboard.questions.values())

        if self.answering is not None and self.answering not in self.dashboard.questions:
            self.answer_box.delete("1.0", "end")
            self.answering = None

        sync_rows(self.question_list, [self.dashboard.question_row(question) for question in questions])

        if select is not None:
            select_only(self.question_list, str(select))

        select_first(self.question_list)

        count = f" ({len(questions)})" if questions else ""
        self.heading.configure(text=f"{TITLE}{count}")
        self.title(f"{TITLE}{count} · a2a-coop")
        self.show_reader(bool(questions))
        self.show_selected(force)

    def show_reader(self, waiting: bool) -> None:
        if waiting:
            self.empty_hint.pack_forget()
            self.reader.frame.pack(side="top", fill="both", expand=True)
        else:
            self.reader.frame.pack_forget()
            self.empty_hint.pack(side="top", fill="x")

    def selected(self) -> Optional[int]:
        iid = selected_iid(self.question_list)

        return int(iid) if iid is not None else None

    def show_selected(self, force: bool = False) -> None:
        question = self.dashboard.questions.get(self.selected())

        set_field_enabled(self.answer_box, True)
        self.switch_draft(question.id if question else None)

        if force:
            self.reader.shown = None

        self.reader.show(self.details(question))

        set_field_enabled(self.answer_box, question is not None)

        for button in self.buttons:
            set_enabled(button, question is not None)

    def details(self, question: Optional[Message]) -> tuple[Segment, ...]:
        if question is None:
            return ()

        text = self.reader.text
        asker = self.dashboard.identity_tag(text, question.sender, theme.READING_BOLD_FONT)

        return (
            (f"#{question.id} · ", ("muted", "lead")),
            (question.sender, (asker, "lead")),
            (f" asks · {self.scope(question)} · {render.clock(question.created_at)}\n", ("muted", "lead")),
            *reading.body_segments(text, question.body),
        )

    def scope(self, question: Message) -> str:
        if question.goal_id is None:
            return "General"

        try:
            return f"Goal #{question.goal_id} {self.dashboard.store.get_goal(question.goal_id).title}"
        except CoopError:
            return f"Goal #{question.goal_id}"

    def switch_draft(self, target: Optional[int]) -> None:
        if target == self.answering:
            return

        self.keep_draft()
        self.answering = target
        self.answer_box.delete("1.0", "end")

        if target is not None:
            self.answer_box.insert("1.0", self.dashboard.answer_drafts.pop(target, ""))

        self.answer_box.edit_reset()
        self.error.configure(text="")

    def keep_draft(self) -> None:
        draft = self.answer_box.get("1.0", "end-1c")

        if self.answering is not None and draft.strip():
            self.dashboard.answer_drafts[self.answering] = draft

    def answer(self) -> None:
        target = self.selected()
        text = self.answer_box.get("1.0", "end-1c").strip()

        if target is not None and text and self.attempt(lambda: self.dashboard.store.answer_question(target, text)):
            self.answer_box.delete("1.0", "end")
            self.answering = None
            self.dashboard.answer_drafts.pop(target, None)
            self.dashboard.refresh_dashboard()

    def dismiss(self) -> None:
        target = self.selected()

        if target is not None and self.attempt(lambda: self.dashboard.store.dismiss_question(target)):
            self.dashboard.refresh_dashboard()

    def attempt(self, action: Callable[[], object]) -> bool:
        try:
            action()
        except CoopError as error:
            self.error.configure(text=str(error))
            self.bell()
            return False

        self.error.configure(text="")
        return True

    def close(self) -> None:
        self.keep_draft()
        selected = self.selected()

        self.destroy()
        self.dashboard.question_window_closed(selected)
