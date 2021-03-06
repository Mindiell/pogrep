"""Find translations examples by grepping in .po files.
"""

__version__ = "0.1.2"

import argparse
import curses
import glob
import os
import sys
from textwrap import fill
from typing import Sequence, NamedTuple, List, Tuple
from shutil import get_terminal_size

import regex
import polib
from tabulate import tabulate


def get_colors():
    """Just returns the CSI codes for red, green, magenta, and reset color.
    """
    try:
        curses.setupterm()
        fg_color = curses.tigetstr("setaf") or curses.tigetstr("setf") or ""
        red = str(curses.tparm(fg_color, 1), "ascii")
        green = str(curses.tparm(fg_color, 2), "ascii")
        magenta = str(curses.tparm(fg_color, 5), "ascii")
        no_color = str(curses.tigetstr("sgr0"), "ascii")
    except curses.error:
        red, green, magenta = "", "", ""
        no_color = ""
    return red, green, magenta, no_color


RED, GREEN, MAGENTA, NO_COLOR = get_colors()


def colorize(text, pattern, prefixes=()):
    """Add CSI color codes to make pattern red in text.

    Optionally also highlight prefixes (as (line, file) tuples) in
    magenta and green.

    colorize(" file.py:30:foo bar baz", "bar", [("30:","file.py:")]) gives:
     file.py:30:foo bar baz, with the following colors:
     |   M  ||G|    |R|
    """
    result = regex.sub(pattern, RED + r"\g<0>" + NO_COLOR, text)
    for pnum, pfile in prefixes:
        prefix = " " + pfile + pnum
        prefix_colored = regex.escape(
            regex.sub(pattern, RED + r"\g<0>" + NO_COLOR, prefix)
        )
        if regex.escape(RED) in prefix_colored:
            prefix = prefix_colored
        prefix_replace = " " + MAGENTA + pfile + GREEN + pnum + NO_COLOR
        result = regex.sub(prefix, prefix_replace, result, count=1)
    return result


class Match(NamedTuple):
    """Represents a string found in a po file.
    """

    file: str
    line: int
    msgid: str
    msgstr: str


def find_in_po(
    pattern: str,
    path: Sequence[str],
    not_in_source: bool = False,
    in_translation: bool = False,
) -> Tuple[List[str], List[Match]]:
    """Find the given pattern in the given list of paths or files.
    """
    results = []
    errors = []
    for filename in path:
        try:
            pofile = polib.pofile(filename)
        except OSError:
            errors.append("{} doesn't seem to be a .po file".format(filename))
            continue
        for entry in pofile:
            if entry.msgstr and (
                (not not_in_source and regex.search(pattern, entry.msgid))
                or (in_translation and regex.search(pattern, entry.msgstr))
            ):
                results.append(
                    Match(filename, entry.linenum, entry.msgid, entry.msgstr)
                )
    return errors, results


def display_results(
    matches: Sequence[Match], pattern: str, line_number: bool, files_with_matches: bool,
):
    """Display matches as a colorfull table.
    """
    files = {match.file for match in matches}
    if files_with_matches:  # Just print filenames
        for file in files:
            print(MAGENTA + file + NO_COLOR)
        return
    prefixes = []
    table = []
    term_width = get_terminal_size()[0]
    for match in matches:
        left = match.msgid
        if line_number:
            pnum = str(match.line) + ":"
            if len(files) > 1:
                pfile = match.file + ":"
            else:
                pfile = ""
            left = pfile + pnum + left
            prefixes.append((pnum, pfile))
        table.append(
            [
                fill(left, width=(term_width - 7) // 2),
                fill(match.msgstr, width=(term_width - 7) // 2),
            ]
        )
    print(colorize(tabulate(table, tablefmt="fancy_grid"), pattern, prefixes))


def process_path(path: Sequence[str], recursive: bool) -> List[str]:
    """Apply the recursive flag to the given paths.

    Also check that -r is not used on files, that no directories are
    given without -r, and file exists.
    """
    files = []
    if len(path) == 0:
        if not recursive:
            sys.exit(0)
        return glob.glob("**/*.po", recursive=True)
    for elt in path:
        if os.path.isfile(elt):
            files.append(elt)
        elif os.path.isdir(elt):
            if recursive:
                files.extend(glob.glob(elt + os.sep + "**/*.po", recursive=True))
            else:
                print(
                    "{}: {}: Is a directory".format(sys.argv[0], elt), file=sys.stderr
                )
                sys.exit(1)
        else:
            print(
                "{}: {}: No such file or directory".format(sys.argv[0], elt),
                file=sys.stderr,
            )
            sys.exit(1)
    return files


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.
    """
    parser = argparse.ArgumentParser(description="Find translated words.")
    parser.add_argument(
        "-F",
        "--fixed-strings",
        action="store_true",
        help="Interpret pattern as fixed string, not regular expressions.",
    )
    parser.add_argument(
        "-i",
        "--ignore-case",
        action="store_true",
        help="Ignore case distinctions, so that characters that differ "
        "only in case match each other.",
    )
    parser.add_argument(
        "-w",
        "--word-regexp",
        action="store_true",
        help="Select only those lines containing matches that form whole words.",
    )
    parser.add_argument(
        "-n",
        "--line-number",
        action="store_true",
        help="Prefix each line of output with the 1-based line number within "
        "its input file.",
    )
    parser.add_argument(
        "-l",
        "--files-with-matches",
        action="store_true",
        help="Suppress normal output; instead print the name of each input file "
        "from which output would normally have been printed.  "
        "The scanning will stop on the first match.",
    )
    parser.add_argument(
        "-s",
        "--no-messages",
        action="store_true",
        help="Suppress error messages about nonexistent or unreadable files.",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Read all files under each directory, recursively, following "
        "symbolic links only if they are on the command line.  "
        "Note that if no file operand is given, pogrep searches "
        "the working directory.",
    )
    parser.add_argument(
        "--translation",
        action="store_true",
        help="search pattern in translated text (result printed on the right column",
    )
    parser.add_argument(
        "--no-source",
        action="store_true",
        help="do NOT search pattern in original text (result printed on the "
        "left column",
    )
    parser.add_argument(
        "--exclude-dir",
        help="Skip any command-line directory with a name suffix that matches "
        "the pattern.  "
        "When searching recursively, skip any subdirectory whose base name "
        "matches GLOB.  "
        "Ignore any redundant trailing slashes in GLOB.",
    )
    parser.add_argument("pattern")
    parser.add_argument("path", nargs="*")
    return parser.parse_args()


def main():
    """Command line entry point.
    """
    args = parse_args()
    if args.fixed_strings:
        args.pattern = regex.escape(args.pattern)
    if args.word_regexp:
        args.pattern = r"\b" + args.pattern + r"\b"
    if args.ignore_case:
        args.pattern = r"(?i)" + args.pattern
    files = process_path(args.path, args.recursive)
    if args.exclude_dir:
        files = [f for f in files if args.exclude_dir.rstrip(os.sep) + os.sep not in f]
    errors, results = find_in_po(args.pattern, files, args.no_source, args.translation)
    if not args.no_messages:
        for error in errors:
            print(error, file=sys.stderr)
    display_results(
        results, args.pattern, args.line_number, args.files_with_matches,
    )


if __name__ == "__main__":
    main()
