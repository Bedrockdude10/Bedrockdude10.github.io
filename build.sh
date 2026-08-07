#!/usr/bin/env bash
# Render every view from data/cv.yml, then compile the PDFs.
#
#   data/cv.yml ──▶ index.html     (served by GitHub Pages)
#               ──▶ cv.tex     ──▶ media/Danny_Rollo_CV.pdf      (4pp, full record)
#               ──▶ resume.tex ──▶ media/Danny_Rollo_Resume.pdf  (1pp)
#
# Those three are what you maintain. For a specific application that needs a
# different framing, run `./build.sh --targeted` to additionally produce
# media/Danny_Rollo_Resume_Research.pdf — a disposable, uncommitted copy.
#
# Edit data/cv.yml — never the generated files.
set -euo pipefail
cd "$(dirname "$0")"

TARGETED=""
[ "${1:-}" = "--targeted" ] && TARGETED="--targeted"

echo "▸ rendering from data/cv.yml"
python3 build.py $TARGETED

compile() {  # compile <basename> <output.pdf>
    # Two passes so hyperref bookmarks and \hfill widths settle.
    pdflatex -interaction=nonstopmode -halt-on-error "$1.tex" >/dev/null
    pdflatex -interaction=nonstopmode -halt-on-error "$1.tex" >/dev/null
    mv -f "$1.pdf" "$2"
    rm -f "$1.aux" "$1.log" "$1.out"
    echo "  $2 ($(pdfinfo "$2" | awk '/^Pages/{print $2}') pages)"
}

echo "▸ compiling PDFs"
compile cv     media/Danny_Rollo_CV.pdf
compile resume media/Danny_Rollo_Resume.pdf
if [ -n "$TARGETED" ]; then
    compile resume-research media/Danny_Rollo_Resume_Research.pdf
fi

echo "✓ done"
