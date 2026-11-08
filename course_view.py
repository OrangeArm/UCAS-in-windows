# SPDX-License-Identifier: AGPL-3.0-or-later
"""Presentation-only grouping; distinct attendance IDs remain independently selectable."""
from dataclasses import dataclass, replace
from ucas_api import ApiError, sign_parameter


def code_key(code):
    try:
        return sign_parameter(code)
    except ApiError:
        return ('invalid', code.strip())


@dataclass(frozen=True)
class CourseGroup:
    name: str
    begin: str
    end: str
    records: tuple

    @property
    def state(self):
        signed = sum(c.signed for c in self.records)
        if signed == len(self.records):
            return '已签到'
        if signed:
            return f'已签 {signed}/{len(self.records)}'
        return '未签到'


def group_courses(courses):
    grouped = {}
    for course in courses:
        key = (course.name.strip(), course.begin.strip(), course.end.strip())
        records = grouped.setdefault(key, {})
        identity = code_key(course.code)
        if not course.code.strip():
            identity = ('missing', len(records))
        existing = records.get(identity)
        # Repeated copies of the same ID must never create repeated submissions.
        records[identity] = replace(course, signed=course.signed or bool(existing and existing.signed))
    return [CourseGroup(name, begin, end, tuple(records.values()))
            for (name, begin, end), records in grouped.items()]


def display_time(value):
    """Omit the date already shown by the date selector, preserve unusual server text."""
    from datetime import datetime
    for pattern in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%H:%M:%S', '%H:%M'):
        try:
            return datetime.strptime(value, pattern).strftime('%H:%M')
        except ValueError:
            pass
    return value
