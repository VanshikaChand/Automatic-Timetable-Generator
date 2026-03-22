"""
data_models.py
Pydantic v2 models for the timetable generator.
"""

from __future__ import annotations

from enum import Enum
from typing import List

from pydantic import BaseModel, Field, field_validator, model_validator


# ─────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────

class RoomType(str, Enum):
    LECTURE = "lecture"
    LAB     = "lab"


class Day(str, Enum):
    MONDAY    = "Monday"
    TUESDAY   = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY  = "Thursday"
    FRIDAY    = "Friday"


# ─────────────────────────────────────────────
# Core models
# ─────────────────────────────────────────────

class Teacher(BaseModel):
    teacher_id           : int       = Field(..., gt=0)
    name                 : str       = Field(..., min_length=1, max_length=80)
    subjects             : List[str] = Field(..., min_length=1)   # Pydantic v2 syntax
    max_lectures_per_day : int       = Field(..., ge=1, le=10)

    @field_validator("subjects")
    @classmethod
    def clean_subjects(cls, v: List[str]) -> List[str]:
        cleaned = [s.strip() for s in v if s.strip()]
        if not cleaned:
            raise ValueError("At least one non-empty subject is required.")
        return cleaned

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return v.strip()


class Room(BaseModel):
    room_id   : int      = Field(..., gt=0)
    room_name : str      = Field(..., min_length=1, max_length=40)
    capacity  : int      = Field(..., ge=1, le=2000)
    room_type : RoomType

    @field_validator("room_name")
    @classmethod
    def clean_room_name(cls, v: str) -> str:
        return v.strip().upper()


class Course(BaseModel):
    course_id         : int  = Field(..., gt=0)
    name              : str  = Field(..., min_length=1, max_length=80)
    teacher_id        : int  = Field(..., gt=0)
    lectures_per_week : int  = Field(..., ge=1, le=20)
    is_lab            : bool = False

    @field_validator("name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        return v.strip()


# ─────────────────────────────────────────────
# Aggregate model — full referential validation
# ─────────────────────────────────────────────

class TimetableInput(BaseModel):
    teachers : List[Teacher]
    rooms    : List[Room]
    courses  : List[Course]

    @model_validator(mode="after")
    def validate_no_duplicate_ids(self) -> "TimetableInput":
        for collection, label, id_attr in [
            (self.teachers, "teacher", "teacher_id"),
            (self.rooms,    "room",    "room_id"),
            (self.courses,  "course",  "course_id"),
        ]:
            ids = [getattr(obj, id_attr) for obj in collection]
            dupes = {x for x in ids if ids.count(x) > 1}
            if dupes:
                raise ValueError(f"Duplicate {label} IDs: {dupes}")
        return self

    @model_validator(mode="after")
    def validate_teacher_references(self) -> "TimetableInput":
        valid_ids = {t.teacher_id for t in self.teachers}
        for course in self.courses:
            if course.teacher_id not in valid_ids:
                raise ValueError(
                    f"Course '{course.name}' has unknown teacher_id={course.teacher_id}. "
                    f"Valid IDs: {sorted(valid_ids)}"
                )
        return self

    @model_validator(mode="after")
    def validate_lab_room_exists(self) -> "TimetableInput":
        has_lab_room = any(r.room_type == RoomType.LAB for r in self.rooms)
        needs_lab    = any(c.is_lab for c in self.courses)
        if needs_lab and not has_lab_room:
            raise ValueError("Lab courses exist but no lab room has been defined.")
        return self