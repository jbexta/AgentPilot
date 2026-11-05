# Python Coding Style Guide

## General Conventions

-   **Line Length**: 79 characters
-   **Imports**: absolute, grouped as standard library, third-party, local.
-   **Principles**: DRY, KISS, YAGNI, Separation of Concerns, SRP, Open/Closed, Liskov Substitution, Convention over Configuration, Boy Scout Rule.

## Comments & Documentation

-   Prefer **self-documenting code** over comments.
-   If comments are necessary, keep them short and consise.
-   Don't write comments explaining why a change or bug fix was made. Explain it in the conversation, not the source.

## Error Handling

-   Let errors propagate unless there’s a clear recovery strategy.
-   Use `try/except` sparingly and precisely — don’t hide errors.
-   Avoid defining custom exceptions.

## PySide6

This section defines conventions for PySide6 with `qasync` for asyncio event loop management.

**Signals & Asynchronous Code**

-   Prefer `@qasyncSlot()` decorators with **async/await** instead of `@Slot()` when defining slots that may perform asynchronous operations.
-   Use lambda expressions for signal connections if the call is trivial.
-   Never block the main thread — always offload long-running or I/O-bound tasks via `async`/`await`.
-   Never use QApplication.processEvents()

**Styling**

-   The global stylesheet is defined in **`src/gui/style.py`**.
    Do not hardcode widget styles in other `.py` files or use inline `setStyleSheet()` calls unless absolutely necessary.

**Widget Structure & Layouts**

-   Each widget class should have UI definition and layout setup in `__init__`.
-   If creating a layout for a widget, use `self.layout = QVBoxLayout(self)` instead of `self.setLayout(layout)`.
-   Prefer creating layouts without content margins or spacing using `CVBoxLayout` or `CHBoxLayout`.
-   Favor **composition over inheritance** — only subclass Qt widgets when extending or specializing behavior.

## Guide for LLM's

Behavioral guidelines for LLM's and coding agents.

**Important:**
-   Never read .env or any file containing secrets/credentials.
-   Never use git to revert local edits; undo manually with Edit/Write.
-   If you need to edit `sql_upgrade.py`, only edit the current-version method, **never** edit previous versions.
-   Never let scripts write to the real `data.db`.

The following guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Implementing

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- Reuse existing hooks (e.g. an `aboutToQuit`/`closeEvent` chain) instead of repeating their work.
- Only add a guard if you can see the concrete scenario that triggers it.
- Inline one-off logic where it's used. This includes a one-line expression used in two places; don't turn it into a helper.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.
- Never delete commented-out code when editing files.

When your changes create I am typing a full sentence out here orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.