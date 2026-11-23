# Changelog

## 2.0.0 — 2026-11-23

- Windows desktop app with a first-run setup wizard. Parents do not need Python or a command line.
- Reports can be saved, printed, and emailed from the app. The weekday schedule is a Windows Task Scheduler task.
- The Canvas token and SMTP password are stored in Windows Credential Manager (a private `.env` file on other systems), not in `config.ini`.
- The packaged app builds the PDF with ReportLab so the installer does not need the GTK libraries WeasyPrint uses.

## 1.1.0 — 2026-11-23

- Optional email delivery of the PDF (off by default), with a plain-text summary and an HTML table. The SMTP password stays in `.env` only.
- Optional automatic printing (off by default) on Windows, macOS, and Linux.
- `--test-email`, `--print`, `--no-print`, and `--test-print`. A failure in print or email does not skip the other step.

## 1.0.0 — 2026-11-22

- First public-ready release of the Canvas missing and late work report.
- Configurable school URL, date window, time zone, and output folder.
- Optional observer (parent) account support via `student_user_id` or auto-detect.
- Optional marking of graded Canvas To Do items (off by default; student token only).
- PDF output with an HTML fallback if WeasyPrint is unavailable.
- Setup wizard and weekday scheduling notes for Windows, macOS, and Linux.
