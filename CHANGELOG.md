# Changelog

## 2.1.0 — 2026-11-23

- Optional To Do detail pages, off by default. After the summary, the PDF can add one card per open To Do item: overdue work from the start date, plus items due in the next 14 days.
- The schedule can be twice a day, once a day, or once a week. Older settings that saved a morning and an evening time stay twice a day.

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
