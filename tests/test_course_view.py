from dataclasses import replace
import unittest
from course_view import group_courses, display_time
from date_picker import month_shift, parse_day
from ucas_api import Course


class PresentationTests(unittest.TestCase):
    def course(self, code='1234567', signed=False, name='新中特', begin='2026-11-11 08:30:00'):
        return Course(code, name, begin, '2026-11-11 12:00:00', signed)

    def test_repeated_ids_merge_but_preserve_signed_state(self):
        groups = group_courses([self.course(), self.course(signed=True), self.course()])
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0].records), 1)
        self.assertEqual(groups[0].state, '已签到')

    def test_distinct_ids_preserved_with_partial_state(self):
        group = group_courses([self.course(), self.course('1234568', True)])[0]
        self.assertEqual([r.code for r in group.records], ['1234567', '1234568'])
        self.assertEqual(group.state, '已签 1/2')

    def test_same_name_different_time_or_different_name_not_merged(self):
        groups = group_courses([self.course(), self.course(begin='2026-11-11 13:30:00'), self.course(name='自然辩证法')])
        self.assertEqual(len(groups), 3)

    def test_uuid_variants_are_the_same_attendance_target(self):
        a = self.course('abcdef12123456789abc123456789abc')
        b = replace(a, code='ABCDEF12-1234-5678-9ABC-123456789ABC')
        self.assertEqual(len(group_courses([a,b])[0].records), 1)

    def test_display_time_and_calendar_boundaries(self):
        self.assertEqual(display_time('2026-11-11 08:30:00'), '08:30')
        self.assertEqual(display_time('上课时间待定'), '上课时间待定')
        self.assertEqual(month_shift(2026, 1, -1), (2025, 12))
        self.assertEqual(month_shift(2026, 12, 1), (2027, 1))
        self.assertEqual(parse_day('20240229').day, 29)
