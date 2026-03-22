"""
main.py — Entry point for the timetable input pipeline.

Usage:
    python main.py
    TIMETABLE_OUTPUT=./output/tt.json python main.py
"""

from __future__ import annotations

import sys

from pydantic import ValidationError

from .input_handler import (
    bold, green, red,
    input_teachers,
    input_rooms,
    input_courses,
    change_teacher,
    print_summary,
    export_to_json,
)


def main() -> int:
    print(bold("\n╔══════════════════════════════╗"))
    print(bold(  "║   🗓  TIMETABLE GENERATOR    ║"))
    print(bold(  "╚══════════════════════════════╝"))

    try:
        teachers = input_teachers()
        rooms    = input_rooms()
        courses  = input_courses(teachers)

        # change_teacher now requires teachers for validation
        change_teacher(courses, teachers)

        print_summary(teachers, rooms, courses)

        if not _ask_bool("\n  Export and continue to C++ stage? (yes/no): "):
            print(red("  Export cancelled."))
            return 1

        export_to_json(teachers, rooms, courses)
        print(green("\n🚀 Ready for C++ processing.\n"))
        return 0

    except ValidationError as exc:
        print(red(f"\n✗ Validation error — export aborted:\n{exc}"))
        return 2

    except KeyboardInterrupt:
        print(red("\n\n  Interrupted. Exiting."))
        return 130


# Import here to avoid circular-import issues at module level
from .input_handler import _ask_bool  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())