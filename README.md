# DarwinGlish: PDF → Obsidian

A manually started job watches an Inbox folder, reads English-learning PDFs using **Codex or Claude Code**, creates grammar notes and exercises, then renames and organizes the source PDF. Screenshot-only PDFs are supported through rendered page images.

## 1. Libraries and tools

| Dependency | Purpose | Installation |
| --- | --- | --- |
| **Python 3.11+** | Runs the scripts | Install Python for your OS |
| **PyMuPDF** | Preferred PDF text extraction and image rendering | `python -m pip install -r requirements.txt` |
| **Codex CLI or Claude Code CLI** | Analyzes text/images and returns lesson data | Install one CLI and authenticate it separately |
| **Bash** | Linux/macOS launcher | Normally included on Linux/macOS |
| **PowerShell** | Windows launcher | Run `config/start.ps1` in PowerShell |
| **markdown-it-py** | Website rendering only | `python -m pip install -r requirements-site.txt` |
| **Ghostscript + Poppler** | Optional smaller website PDF downloads | Installed by the Pages workflow; local builds fall back to originals if absent |

The remaining modules are in Python's standard library: `argparse`, `contextlib`, `hashlib`, `importlib`, `json`, `logging`, `os`, `pathlib`, `re`, `shutil`, `signal`, `subprocess`, `sys`, `time`, `tomllib`, plus `fcntl` on Unix or `msvcrt` on Windows for the job lock. Tests additionally use `unittest`, `tempfile`, `copy`, and `zlib`.

**Optional fallback:** when PyMuPDF is unavailable, the job uses Poppler's `pdfinfo`, `pdftotext`, and `pdftoppm` if all three are on PATH. Install PyMuPDF for a simpler Windows/macOS setup. There is no requirement for OCR/Tesseract, `watchdog`, `python-dotenv`, or an OpenAI/Anthropic Python SDK.

The selected CLI must support image input, noninteractive execution, and structured output. Its selected model must support images. Your existing CLI account/API authentication and usage limits apply. `--check` checks executable availability, not authentication or remaining quota. Source text and image tiles are sent to the provider during a real analysis.

Official references: [Codex noninteractive mode](https://learn.chatgpt.com/docs/non-interactive-mode), [Claude Code programmatic mode](https://code.claude.com/docs/en/headless).

## 2. Project structure

```text
DARWINGLISH/
├── README.md
├── requirements.txt
├── requirements-site.txt              # Website-only dependency
├── .github/workflows/pages.yml         # Deploy after your push
├── scripts/                          # Python only
│   ├── watch_pdfs.py                  # CLI, polling, state, publication, recovery
│   ├── pdf_input.py                   # PDF text extraction and image tiling
│   ├── providers.py                   # Codex and Claude CLI adapters
│   ├── lesson_output.py               # Result validation and Markdown rendering
│   ├── build_site.py                  # Markdown/wiki links → static HTML
│   ├── compress_pdfs.py               # Smaller PDF download copies
│   ├── site_validation.py             # Website file/heading/download checks
│   ├── site_assets/                   # CSS and browser JavaScript
│   └── tests/                        # Watcher and website behavior tests
├── content/                          # Open THIS folder as your Obsidian vault
│   ├── .obsidian/                     # Existing vault settings, preserved and relocated
│   ├── Inbox/                        # Put new PDFs here
│   ├── PDFs/                         # Existing PDFs plus newly organized originals
│   ├── Obsidian English/             # Existing study notes
│   │   ├── Imported Lessons.md        # Automatically maintained import index
│   │   └── Imported/<topic>--<hash>/  # One generated bundle per new PDF
│   │       ├── Lesson.md
│   │       ├── Exercises.md           # All answers are at the end
│   │       └── manifest.json
│   ├── Duplicates/                    # Repeated PDFs retained without another AI call
│   └── References/                    # Existing standalone screenshots
└── config/
    ├── job.toml                      # Shared job settings
    ├── site.toml                     # Website and PDF compression settings
    ├── linux.env                     # Linux Bash overrides
    ├── macos.env                     # macOS Bash overrides
    ├── windows.ps1                   # Windows environment overrides
    ├── start.sh                      # Bash launcher
    ├── start.ps1                     # PowerShell launcher
    ├── skills/english-pdf-notes/
    │   ├── SKILL.md                  # Reusable conversion instructions
    │   └── schema.json               # Structured result contract
    └── state/                        # Created at runtime; ignored by Git
        ├── job.lock
        ├── job.log
        ├── history.json
        ├── previews/                 # --prepare-only output
        └── jobs/<full-sha256>/        # Prompt, result, plan, provider logs
```

The original six PDFs and 22 Markdown notes were moved into `content/`. Their PDF wiki links remain relative to the vault root. The existing `.obsidian` settings now live at `content/.obsidian`; workspace note paths were adjusted for the new location. Reopen **content/** as the vault if Obsidian still points at the previous notes-only folder.

## 3. Install

Run these commands from the project folder. Do not put credentials in the config files; use your CLI's normal login.

### Linux or macOS

```bash
python3 --version                    # Must be 3.11 or newer
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

On Debian/Ubuntu, if creating the virtual environment reports that `ensurepip` is unavailable, install the appropriate `python3-venv` package first. An existing pip can also manage a virtual environment without its own pip using `python3 -m pip --python .venv/bin/python install -r requirements.txt`. Package installation requires network access.

If all three Poppler tools are already installed, you can run using that fallback without installing a Python package.

### Windows PowerShell

```powershell
python --version                    # Must be 3.11 or newer
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Install Codex or Claude Code using its official instructions, then sign in interactively. The executable must be callable from Python without a shell; use a native executable path in `job.toml` when necessary. A shell alias/function is not an executable. The launchers use the project's virtual-environment Python when present; otherwise Bash uses `PYTHON_COMMAND`/`python3`, and PowerShell uses `python` on PATH.

## 4. Activate the job

### Linux/macOS: Bash

```bash
bash config/start.sh --check
bash config/start.sh --provider codex
# Or:
bash config/start.sh --provider claude
```

### Windows: PowerShell

```powershell
.\config\start.ps1 --check
.\config\start.ps1 --provider codex
# Or:
.\config\start.ps1 --provider claude
```

If your Windows execution policy blocks the launcher, review/trust the local script and configure a policy appropriate to your machine. You can also call the Python entry point directly:

```powershell
.\.venv\Scripts\python.exe .\scripts\watch_pdfs.py --provider claude
```

The job runs **in the foreground**. Leave that terminal open. **Press Ctrl+C to stop.** Closing the terminal also ends the watcher, though Ctrl+C allows orderly cleanup. This version does not install a startup service or scheduled task.

Once it is running:

1. Copy or move a PDF into `content/Inbox/`.
2. Wait for its size and modification time to remain unchanged for `stable_seconds` (default 10 seconds).
3. The job extracts text, renders low-text pages into overlapping image tiles, and invokes the selected provider.
4. It validates structured output, publishes the Markdown bundle, archives the PDF under its generated name, and removes that successfully archived Inbox copy.
5. Open `content/Obsidian English/Imported Lessons.md` in Obsidian.

Only direct children of Inbox with a `.pdf` extension (case-insensitive) are watched. It is not recursive. Use a temporary extension such as `.part` while downloading, then rename to `.pdf` when complete; this avoids a long pause during copying being mistaken for a completed file. Symlink inputs are ignored.

Example result:

```text
content/Inbox/screencapture_123.pdf
  → content/PDFs/Grammar/second-conditional--a1b2c3d4e5f6.pdf
  → content/Obsidian English/Imported/second-conditional--a1b2c3d4e5f6/Lesson.md
  → content/Obsidian English/Imported/second-conditional--a1b2c3d4e5f6/Exercises.md
```

The suffix is the first 12 characters of the source file's SHA-256. The full hash is recorded in the manifest and processing history.

## 5. Useful commands

| Purpose | Bash | PowerShell |
| --- | --- | --- |
| Check configuration/tools | `bash config/start.sh --check` | `.\config\start.ps1 --check` |
| Watch with Codex | `bash config/start.sh --provider codex` | `.\config\start.ps1 --provider codex` |
| Watch with Claude | `bash config/start.sh --provider claude` | `.\config\start.ps1 --provider claude` |
| Process one stable inbox snapshot, then exit | `bash config/start.sh --once` | `.\config\start.ps1 --once` |
| Reset failed attempts and try again | `bash config/start.sh --once --retry-failed` | `.\config\start.ps1 --once --retry-failed` |
| Show command help | `bash config/start.sh --help` | `.\config\start.ps1 --help` |

Test PDF preparation **without an agent call or PDF move**:

```bash
bash config/start.sh --prepare-only "content/PDFs/Grammar/04 Cause and Result/Making time work.pdf"
```

```powershell
.\config\start.ps1 --prepare-only 'content\PDFs\Grammar\04 Cause and Result\Making time work.pdf'
```

This creates `pages.json` and any rendered PNGs under `config/state/previews/`. Stop another running watcher before preparing a preview; these commands share the single-job lock.

`--once` waits for the stability interval and processes one snapshot. Files that change during that interval wait for a later run. A considered file that fails or remains retry-blocked makes the command exit with status 1. Ctrl+C exits with status 130. `--check` and `--prepare-only` do not verify provider inference.

## 6. User configuration

Edit `config/job.toml` to set the default provider, optional model, Inbox location, limits, executable paths, and timing.

```toml
provider = "codex"           # or "claude"
model = ""                   # empty uses the CLI's configured default
inbox = "content/Inbox"
poll_seconds = 5
stable_seconds = 10
max_attempts = 2
retry_seconds = 60
agent_timeout_seconds = 900
```

All configured directories must be inside this project; Inbox must be a subdirectory of `content`, and state must remain separate. Relative paths resolve from the **project root**, regardless of the terminal's current directory. Only one configured state directory should manage a given Inbox. Do not start two copies with separate state directories against the same Inbox.

For OS-specific overrides, edit `config/linux.env`, `config/macos.env`, or `config/windows.ps1`. For example:

```bash
# Linux/macOS, or put these exports in the matching .env file:
export ENGLISH_PROVIDER=claude
export ENGLISH_MODEL=""       # Or a model available to your account that supports images
bash config/start.sh
```

```powershell
$env:ENGLISH_PROVIDER = 'claude'
.\config\start.ps1
```

Precedence: **`--provider` > nonempty `ENGLISH_PROVIDER` > `job.toml`**. A nonempty `ENGLISH_MODEL` overrides the TOML model. `ENGLISH_CONFIG` selects a different TOML file; Bash also accepts `PYTHON_COMMAND` when no project virtual environment exists. `codex_command`/`claude_command` each take one executable name or path, not a shell command containing arguments.

Restart the watcher after changing settings. When retrying an already analyzed job with a saved publication plan, the existing result/provider is reused; selecting a different provider does not replace that saved analysis.

## 7. Reusable skill and note behavior

Both provider adapters explicitly load `config/skills/english-pdf-notes/SKILL.md`. The instructions are project-local and need no installation in your global Codex or Claude configuration. They are also readable and reusable in manual sessions: ask the agent to use that file for an English PDF conversion. Automatic global skill discovery is not configured by these launchers.

The skill requests:

- Grammar usage, contrasts, common mistakes, source examples, and clearly labelled new examples.
- Related links selected from the existing note catalog.
- Visible source exercises, including choices and blanks.
- Clearly labelled adapted/new practice when the PDF does not supply the requested task type.
- Separate answers and explanations, rendered **after all questions**, in the final `Answers` section at the end of the exercise note.
- Explicit limitations for clipped screenshots, missing prompts, unreadable areas, unavailable audio, and inferred answers.

Python validates the result's shape, page references, related-note targets, and filename slug. It creates the links and performs file operations. Codex runs in a read-only sandbox; Claude is limited to its Read tool for local images. Neither is asked to rename files or edit the vault. Structural checks cannot prove the linguistic accuracy of an answer, so review generated lessons normally.

Existing authored notes are preserved. New imports get their own bundle and appear in a generated index; the job does not automatically merge them into old topic notes. The agent sees the catalog for linking, not the full text of every old note.

## 8. Recovery, duplicates, and limits

- **Duplicates:** after a hash was successfully processed by this job, a new copy is moved to `content/Duplicates/` without another provider call. PDFs already in `content/PDFs` are not automatically indexed into processing history.
- **Failures:** the Inbox source stays in place through agent/preparation/validation failures. The job records an error and retries up to `max_attempts`, separated by `retry_seconds`. Inspect the logs before using `--retry-failed`.
- **Interrupted publication:** a saved plan is reused without another AI call. A matching archived PDF and verified note bundle let the next run recover completed state. A hard interruption during a PDF copy can leave a partial destination; inspect/move that partial file aside before retrying. The original is retained until a verified archive exists.
- **Collisions/edits:** existing destination files are never overwritten. If notes in an incomplete publication were edited manually, a retry stops instead of replacing those edits.
- **Limits:** default maximums are 80 pages, 60 image tiles, and 400,000 extracted text characters. Exceeding a limit fails explicitly; pages are not silently discarded. Split large PDFs or change the limits to fit the provider's context/image capacity.
- **PDF support:** password-protected PDFs must be unlocked first. Low-text pages are rendered; text-rich pages use extracted text. Diagrams on text-rich pages are not separately interpreted in this version. Extremely small screenshot text may require a larger `image_width`.
- **Logs/state:** `config/state/job.log` summarizes activity. Each job directory stores source-containing prompts/results and provider stdout/stderr. Work images and the temporary PDF copy are removed after successful processing; failed-job work and preparation previews remain for diagnosis. You can remove previews and successful-job logs while the watcher is stopped. Keep `history.json` and publication plans if you want deduplication/recovery.
- **Concurrency:** a file lock prevents two processes from using the same state directory. It releases on exit; the lock file remaining on disk is normal.

Do not delete all processing history to fix one failed file: that loses duplicate tracking for other imports. Errors and attempts are keyed by the full PDF hash in `history.json`.

## 9. Tests and validation status

Run the behavior tests without paid agent calls (install both requirements files for the complete suite):

```bash
python3 -m unittest discover -s scripts/tests -v
```

```powershell
python -m unittest discover -s scripts/tests -v
```

Tests use temporary directories and simulated provider responses. They cover publication, final answer placement, bounded retries, duplicates, source preservation, collision handling, interrupted publication/recovery, edited-note preservation, lock contention, file stability, symlink inputs, invalid results, both CLI adapters, and real text/image PDF preparation when a backend is available.

Validated here on Linux: 17 behavior tests, both CLI executable checks, Bash syntax, real screenshot preparation, and the 22-page IELTS PDF preparation using the Poppler fallback. The skill passed its frontmatter/name validator. PyMuPDF installation could not complete in this environment because package-network access was unavailable. Windows/PowerShell and macOS launchers have not been executed here. No real Codex/Claude inference, account authentication, or output quality test was performed; run your first real import with `--once` and inspect the generated bundle before leaving the watcher running.

## 10. GitHub Pages: enable the website

Your publication workflow is deliberately separate from local AI processing:

```text
Local Inbox → local Codex/Claude processing → your review → your Git commit and push
→ GitHub Actions → GitHub Pages
```

The new `.github/workflows/pages.yml` workflow builds the website and deploys it. It **never commits, pushes, or invokes an AI provider**. No model credentials are needed in GitHub Actions.

### One-time GitHub setup

1. Create/open the GitHub repository that will contain this project. The workflow currently targets **main**. If your publishing branch has another name, change both `branches: [main]` and the `github.ref == 'refs/heads/main'` condition in `.github/workflows/pages.yml`.
2. In the repository, go to **Settings → Pages**.
3. Under **Build and deployment → Source**, select **GitHub Actions**. Do not select a branch or `/docs` source: this workflow uploads the generated `dist` artifact.
4. If Actions is disabled, enable it in **Settings → Actions → General**. Organization policies may need to allow the official `actions/*` actions. The workflow declares its required permissions; it does not need repository-content write access.
5. Review and commit the implementation and your finished content yourself, then push to the publishing branch. For the first setup, an example is:

   ```bash
   git status
   git add .github scripts config content README.md requirements.txt requirements-site.txt .gitignore
   git diff --cached --stat
   git commit -m "Add English library website and GitHub Pages pipeline"
   git push origin main
   ```

   If this is a new local repository, connect it to your GitHub repository before pushing. Use your own repository URL and authentication. No Git commands have been run to commit or push on your behalf.

6. Open the repository's **Actions** tab and select **Publish English library**. The build runs tests, compresses download copies, checks website links, and uploads the site; the deploy job publishes it.
7. Open **Settings → Pages → Visit site**, or the deployment URL shown by the workflow. A project site is normally `https://YOUR-USERNAME.github.io/YOUR-REPOSITORY/`.

If the first push happened before Pages was enabled, enable Pages and rerun the failed workflow, or use **Actions → Publish English library → Run workflow**, selecting `main`.

GitHub Pages availability depends on your repository visibility and plan. A public repository on GitHub Free is supported. See [GitHub's Pages publishing documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site) and [custom workflow documentation](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).

### Publish newly added lessons

1. Start the local watcher using section 4.
2. Put the new PDF in `content/Inbox/` and wait for local processing to finish.
3. Review the generated notes, exercises, and PDF under `content/`.
4. Commit and push your reviewed content:

   ```bash
   git add "content/Obsidian English" content/PDFs
   git diff --cached --stat
   git commit -m "Add a new English lesson"
   git push origin main
   ```

5. The website updates after the GitHub Actions deployment succeeds. A local commit without a push does not publish anything.

Only changes matching the workflow's content/build paths trigger an automatic build. Documentation-only changes do not require a website rebuild. You can also run the workflow manually for already committed content. Editing files in Inbox does not trigger GitHub or an upload.

### What gets published

The website includes:

- All non-hidden `.md` files under `content/Obsidian English/`.
- PDF distribution copies made from files under `content/PDFs/`.
- The CSS/JavaScript in `scripts/site_assets/`.
- A small compression report.

The builder does not copy the whole repository or vault. Inbox files, duplicates, standalone reference images, `.obsidian`, `.processing`, provider prompts/logs, runtime state, configuration, and the Python scripts are outside the website allowlist. `.gitignore` additionally excludes local Inbox files, state, generated `dist`, Obsidian settings, and duplicates from new Git tracking.

The site supports searchable/filterable notes, working Obsidian wiki links and heading links, tables, source callouts, and expandable answer sections. Generated links use relative URLs, so both repository project sites and account-root Pages sites work. Broken or ambiguous note links fail the build rather than publishing broken navigation. The last successful deployment stays live if a subsequent build fails.

All published PDF links use same-origin URLs and the HTML `download` attribute, with no page fragment and no embedded viewer. Clicking a PDF requests a file download; the browser controls save prompts and download preferences. This includes PDF links inside lesson notes and on the PDF bookshelf. Reference: [HTML download behavior](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/a#download).

### Build or preview locally

The website needs one extra Python library, kept separate from the PDF watcher's dependencies:

```bash
python3 -m pip install -r requirements-site.txt
python3 scripts/build_site.py
python3 -m http.server 8000 --directory dist
```

Then visit `http://localhost:8000`. If you use the virtual environment, run these commands with `.venv/bin/python` on Linux/macOS or `.\.venv\Scripts\python.exe` on Windows. On Windows without a virtual environment, use `python` in place of `python3`.

`config/site.toml` controls the site title/tagline, input folders, compression quality, and output directory. Only the generated `dist/` directory is uploaded. You do not need to commit `dist/`; GitHub rebuilds it from your committed Markdown and original PDFs.

For a fast build without recompression:

```bash
python3 scripts/build_site.py --no-compress
```

`build_site.py` rejects output directories overlapping source/configuration folders and refuses to replace a nonempty directory it did not create. Notes use CommonMark plus tables, Obsidian wiki links, and basic callout conversion. Plugins such as Dataview, math rendering, arbitrary HTML, and attachment image embeds are not implemented; unsupported image attachments or unresolved links stop the build with a diagnostic.

### Smaller PDFs

Compression happens **at website build time**, on separate download copies. Original PDFs in `content/PDFs` and their source hashes are preserved. This reduces website downloads, not the Git repository's original-file size.

The build uses Ghostscript with JPEG quality **90**, a **220 DPI** target for high-resolution color/grayscale images, and no monochrome downsampling. It preserves PDF page geometry. A candidate is used only when it is at least 2% smaller and checks preserve page count, dimensions, and normalized extracted text. Otherwise, the original is copied into the website. Compression may be lossy for images; increase `jpeg_quality`/`image_dpi` or disable it in `config/site.toml` if a particular screenshot needs more detail.

GitHub Actions installs Ghostscript and Poppler automatically. Locally, the builder looks for `gs`, `gswin64c`, or `gswin32c`, plus `pdfinfo` and `pdftotext`. If they are absent, the site still builds using original PDF copies. No system packages are installed by the Python scripts.

For separate download copies outside the website build:

```bash
python3 scripts/compress_pdfs.py --input content/PDFs --output config/state/pdf-download-copies
```

Initial six-PDF measurement:

| PDF | Original | Website download |
| --- | ---: | ---: |
| Getting along | 4.65 MB | 0.48 MB |
| Open source | 6.74 MB | 0.49 MB |
| Presenting a project update | 1.80 MB | 1.55 MB |
| Making time work | 3.64 MB | 2.63 MB |
| IELTS common idioms | 1.15 MB | 1.15 MB |
| Why do we trust it so much? | 5.31 MB | 2.59 MB |
| **Total** | **23.29 MB** | **8.89 MB** |

That is approximately **61.8% smaller** overall. The IELTS candidate did not satisfy the preservation checks, so its original is served unchanged. `dist/compression-report.json` records the actual result after each build.

### Website validation

Install `requirements-site.txt` before running the full suite; `requirements.txt` alone is sufficient only for the watcher portion. Run watcher-only tests with `python3 -m unittest discover -s scripts/tests -p test_job.py` if you do not need the site builder.

The complete suite currently has **31 tests**. Website coverage includes note/heading links, relative project-site URLs, downloadable PDFs, collapsible answers, wiki aliases in tables, excluded local data, failed-build preservation, output directory protection, raw HTML escaping, ambiguous imports, and compression fallback/preservation behavior.

The generated site was built locally with all 23 notes and 6 PDFs. All 31 PDF pages were rendered; detailed compressed grammar sections were visually inspected. Browser preview could not run in this environment because opening a local HTTP socket was denied. The GitHub Actions deployment itself has not run here; it will run after your commit/push and Pages setup.
