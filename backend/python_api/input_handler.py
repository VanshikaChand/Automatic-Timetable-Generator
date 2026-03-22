"""
input_handler.py
Robust CLI input collection for the timetable generator.

Key improvements over the original:
  - Safe prompt helpers — no crash on bad input, always re-prompts.
  - All Pydantic models built with keyword arguments (positional args crash in v2).
  - .model_dump() instead of deprecated .dict().
  - change_teacher validates the new teacher_id before applying it.
  - export_to_json runs full TimetableInput cross-validation before writing.
  - Output path configurable via TIMETABLE_OUTPUT env var.
  - Zero third-party dependencies beyond pydantic (colors degrade on non-TTY).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Callable, List, TypeVar

from pydantic import ValidationError

from .data_models import Course, Room, RoomType, Teacher, TimetableInput

# ─────────────────────────────────────────────
# Output path — override with env var if needed
# ─────────────────────────────────────────────

_DEFAULT = Path(__file__).resolve().parents[2] / "backend" / "output" / "timetable.json"
OUTPUT_PATH: Path = Path(os.environ.get("TIMETABLE_OUTPUT", str(_DEFAULT)))


# ─────────────────────────────────────────────
# Minimal ANSI helpers (degrade on non-TTY)
# ─────────────────────────────────────────────

_TTY = sys.stdout.isatty()

def _c(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _TTY else text

bold   = lambda t: _c(t, "1")
green  = lambda t: _c(t, "32")
yellow = lambda t: _c(t, "33")
red    = lambda t: _c(t, "31")
cyan   = lambda t: _c(t, "36")
dim    = lambda t: _c(t, "2")


# ─────────────────────────────────────────────
# Safe prompt helpers — never crash, always retry
# ─────────────────────────────────────────────

T = TypeVar("T")

def _ask(prompt: str, parser: Callable[[str], T], err: str = "Invalid — try again.") -> T:
    """Prompt until parser(raw) succeeds without raising."""
    while True:
        raw = input(prompt).strip()
        try:
            result = parser(raw)
            return result
        except (ValueError, KeyError, IndexError):
            print(red(f"  ✗ {err}"))


def _ask_int(prompt: str, *, lo: int = 1, hi: int = 10_000) -> int:
    return _ask(
        prompt,
        lambda r: int(r) if lo <= int(r) <= hi else (_ for _ in ()).throw(ValueError()),
        f"Enter a whole number between {lo} and {hi}.",
    )


def _ask_str(prompt: str, *, min_len: int = 1) -> str:
    return _ask(
        prompt,
        lambda r: r if len(r) >= min_len else (_ for _ in ()).throw(ValueError()),
        "Cannot be empty.",
    )


def _ask_bool(prompt: str) -> bool:
    return _ask(
        prompt,
        lambda r: True if r.lower() in {"yes", "y"} else
                  False if r.lower() in {"no", "n"} else
                  (_ for _ in ()).throw(ValueError()),
        "Enter yes or no.",
    )


def _section(title: str) -> None:
    bar = cyan("─" * 45)
    print(f"\n{bar}\n  {bold(title)}\n{bar}")


# ─────────────────────────────────────────────
# Input functions
# ─────────────────────────────────────────────

def input_teachers() -> List[Teacher]:
    _section("👨‍🏫  TEACHERS")
    n = _ask_int("Number of teachers: ", lo=1, hi=100)
    teachers: List[Teacher] = []

    for i in range(n):
        print(f"\n  {yellow(f'Teacher {i+1}/{n}')}")
        name     = _ask_str("  Name: ")
        raw_subs = _ask_str("  Subjects (comma-separated): ")
        subjects = [s.strip() for s in raw_subs.split(",") if s.strip()]
        max_lec  = _ask_int("  Max lectures/day: ", lo=1, hi=10)

        try:
            t = Teacher(
                teacher_id=i + 1,
                name=name,
                subjects=subjects,
                max_lectures_per_day=max_lec,
            )
            teachers.append(t)
            print(green(f"  ✓ {t.name} added."))
        except ValidationError as exc:
            print(red(f"  ✗ Validation failed:\n{exc}"))
            i -= 1   # redo this teacher

    return teachers


def input_rooms() -> List[Room]:
    _section("🏫  ROOMS")
    n = _ask_int("Number of rooms (LTs + Labs): ", lo=1, hi=200)
    rooms: List[Room] = []

    for i in range(n):
        print(f"\n  {yellow(f'Room {i+1}/{n}')}")
        name     = _ask_str("  Room name (e.g. LT1, LabA): ")
        capacity = _ask_int("  Capacity: ", lo=1, hi=2000)
        rtype    = _ask(
            "  Type — [L]ecture / [B]lab: ",
            lambda r: {
                "l": RoomType.LECTURE, "lecture": RoomType.LECTURE,
                "b": RoomType.LAB,     "lab":     RoomType.LAB,
            }[r.lower()],
            "Enter L for Lecture or B for Lab.",
        )

        rooms.append(Room(
            room_id=i + 1,
            room_name=name,
            capacity=capacity,
            room_type=rtype,
        ))
        print(green(f"  ✓ {rooms[-1].room_name} ({rooms[-1].room_type.value}) added."))

    return rooms


def input_courses(teachers: List[Teacher]) -> List[Course]:
    _section("📚  COURSES")

    print(f"\n  {bold('Available Teachers:')}")
    for t in teachers:
        print(f"    {cyan(str(t.teacher_id)):>6}  {t.name:<25} {dim(', '.join(t.subjects))}")

    valid_ids = {t.teacher_id for t in teachers}
    n = _ask_int("\nNumber of courses: ", lo=1, hi=500)
    courses: List[Course] = []

    for i in range(n):
        print(f"\n  {yellow(f'Course {i+1}/{n}')}")
        name       = _ask_str("  Course name: ")
        teacher_id = _ask(
            "  Teacher ID: ",
            lambda r: int(r) if int(r) in valid_ids else (_ for _ in ()).throw(ValueError()),
            f"Must be one of: {sorted(valid_ids)}",
        )
        lectures   = _ask_int("  Lectures/week: ", lo=1, hi=20)
        is_lab     = _ask_bool("  Is this a lab course? (yes/no): ")

        courses.append(Course(
            course_id=i + 1,
            name=name,
            teacher_id=teacher_id,
            lectures_per_week=lectures,
            is_lab=is_lab,
        ))
        print(green(f"  ✓ '{courses[-1].name}' added."))

    return courses


# ─────────────────────────────────────────────
# Dynamic edit — change a course's teacher
# ─────────────────────────────────────────────

def change_teacher(courses: List[Course], teachers: List[Teacher]) -> None:
    """
    Interactively reassign a teacher to a course.
    Validates both course_id and new teacher_id before mutating.
    Now takes `teachers` so it can validate the new assignment.
    """
    valid_teacher_ids = {t.teacher_id for t in teachers}
    course_map        = {c.course_id: c for c in courses}

    while _ask_bool("\nChange a teacher assignment? (yes/no): "):
        if not course_map:
            print(red("  No courses available."))
            break

        # Show current assignments
        print(f"\n  {bold('Current courses:')}")
        for c in courses:
            teacher_name = next(
                (t.name for t in teachers if t.teacher_id == c.teacher_id), "Unknown"
            )
            print(f"    {cyan(str(c.course_id)):>5}  {c.name:<30} → {teacher_name}")

        course_id = _ask(
            "  Course ID to update: ",
            lambda r: int(r) if int(r) in course_map else (_ for _ in ()).throw(ValueError()),
            f"Valid course IDs: {sorted(course_map)}",
        )

        print(f"\n  {bold('Available Teachers:')}")
        for t in teachers:
            print(f"    {cyan(str(t.teacher_id)):>5}  {t.name}")

        new_teacher_id = _ask(
            "  New Teacher ID: ",
            lambda r: int(r) if int(r) in valid_teacher_ids else (_ for _ in ()).throw(ValueError()),
            f"Valid teacher IDs: {sorted(valid_teacher_ids)}",
        )

        course = course_map[course_id]
        old_teacher = next(
            (t.name for t in teachers if t.teacher_id == course.teacher_id), "Unknown"
        )
        new_teacher = next(t.name for t in teachers if t.teacher_id == new_teacher_id)

        # Pydantic v2: use model_copy to preserve immutability semantics
        updated = course.model_copy(update={"teacher_id": new_teacher_id})
        idx = courses.index(course)
        courses[idx] = updated
        course_map[course_id] = updated

        print(green(f"  ✓ '{updated.name}' reassigned: {old_teacher} → {new_teacher}"))


# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────

def print_summary(teachers: List[Teacher], rooms: List[Room], courses: List[Course]) -> None:
    teacher_map = {t.teacher_id: t.name for t in teachers}
    _section("📋  SUMMARY")

    print(f"\n  {bold(f'Teachers ({len(teachers)})')}")
    for t in teachers:
        print(f"    • {t.name:<25}  max/day: {t.max_lectures_per_day}  subjects: {', '.join(t.subjects)}")

    print(f"\n  {bold(f'Rooms ({len(rooms)})')}")
    for r in rooms:
        print(f"    • {r.room_name:<10}  {r.room_type.value:<8}  capacity: {r.capacity}")

    print(f"\n  {bold(f'Courses ({len(courses)})')}")
    for c in courses:
        lab_tag = yellow(" [LAB]") if c.is_lab else ""
        print(f"    • {c.name:<30}  teacher: {teacher_map.get(c.teacher_id, '?'):<20}"
              f"  {c.lectures_per_week} lec/wk{lab_tag}")


# ─────────────────────────────────────────────
# JSON export
# ─────────────────────────────────────────────

def export_to_json(
    teachers : List[Teacher],
    rooms    : List[Room],
    courses  : List[Course],
    *,
    path     : Path = OUTPUT_PATH,
) -> Path:
    """
    Cross-validates the full dataset, then writes timetable.json.
    Uses .model_dump() (Pydantic v2) — .dict() is deprecated.
    Returns the path written.
    """
    # Full referential + structural validation
    TimetableInput(teachers=teachers, rooms=rooms, courses=courses)

    data = {
        "teachers" : [t.model_dump() for t in teachers],
        "rooms"    : [r.model_dump() for r in rooms],
        "courses"  : [c.model_dump() for c in courses],
    }

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print(green(f"\n  ✅ Saved → {bold(str(path))}"))
    return path