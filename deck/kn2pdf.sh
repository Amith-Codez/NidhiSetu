#!/bin/zsh
# usage: kn2pdf.sh in.pptx out.pdf
IN="$1"; OUT="$2"
osascript <<APPLESCRIPT
tell application "Keynote"
  set theDoc to open POSIX file "$IN"
  delay 1
  export theDoc to POSIX file "$OUT" as PDF with properties {PDF image quality:Best}
  close theDoc saving no
end tell
APPLESCRIPT
