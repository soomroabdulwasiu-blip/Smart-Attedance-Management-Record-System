"""Run presentation reads in workers, then render from a strict memory snapshot."""

from functools import wraps

from . import db
from .presentation_data import prefetch


def background_read(fn, name):
    @wraps(fn)
    def run(window, *args, **kwargs):
        if (
            not getattr(window, "_async_mode", False)
            or not hasattr(window, "_action_tasks")
            or getattr(window, "_applying_snapshot", False)
        ):
            return fn(window, *args, **kwargs)
        query = None
        if name in ("refresh_dashboard", "refresh_admin"):
            query = lambda: prefetch(window.user)
        elif name == "refresh_students":
            query = db.students
        elif name == "refresh_teachers":
            query = db.teachers
        elif name == "refresh_resets":
            query = db.pending_resets
        elif name == "refresh_signups":
            query = lambda: db.pending_teacher_signups(window.user)
        elif name == "refresh_correction_requests":
            query = lambda: db.correction_requests(window.user)
        elif name == "refresh_history":
            course = window.history_courses.currentData()
            start = (
                window.history_from.date().toPython()
                if window.history_range.isChecked()
                else None
            )
            end = (
                window.history_to.date().toPython()
                if window.history_range.isChecked()
                else None
            )
            query = lambda: db.attendance(window.user, course, start, end)
        elif name in ("load_roster", "refresh_camera_roster"):
            course = window.mark_course.currentData()
            day = window.day.date().toPython()
            query = lambda: (
                (
                    db.course_students(course),
                    db.session_attendance(window.user, course, day),
                )
                if course
                else None
            )
        elif name == "generate_report":
            course = window.report_course.currentData()
            query = lambda: db.course_summary(window.user, course) if course else None
        elif name in ("course_table_selected", "edit_course"):
            i = window.course_table.currentRow()
            course = (
                window.admin_course.currentData()
                if name == "edit_course"
                else (
                    window.course_rows[i]["course_id"]
                    if 0 <= i < len(window.course_rows)
                    else None
                )
            )
            query = lambda: (
                db.one("SELECT * FROM courses WHERE course_id=:id", {"id": course})
                if course
                else None
            )
        elif name == "student_selected":
            i = window.students_table.currentRow()
            sid = (
                window.student_rows[i]["student_id"]
                if 0 <= i < len(window.student_rows)
                else None
            )
            query = lambda: (
                db.one("SELECT * FROM students WHERE student_id=:id", {"id": sid})
                if sid
                else None
            )
        if query is None:
            return fn(window, *args, **kwargs)
        generations = getattr(window, "_read_generations", {})
        window._read_generations = generations
        generation = generations.get(name, 0) + 1
        generations[name] = generation

        def read():
            if name in ("refresh_dashboard", "refresh_admin"):
                return query()
            with db.capture_reads() as snapshot:
                query()
            return snapshot

        def render(snapshot):
            if generations.get(name) != generation:
                return
            window._applying_snapshot = True
            try:
                with db.use_reads(snapshot):
                    fn(window, *args, **kwargs)
            finally:
                window._applying_snapshot = False

        return window.submit_action(read, render, message="View updated.")

    return run


def install(window_class):
    for name in (
        "refresh_dashboard",
        "refresh_students",
        "refresh_teachers",
        "refresh_resets",
        "refresh_signups",
        "refresh_admin",
        "refresh_correction_requests",
        "refresh_history",
        "load_roster",
        "refresh_camera_roster",
        "generate_report",
        "course_table_selected",
        "edit_course",
        "student_selected",
    ):
        setattr(window_class, name, background_read(getattr(window_class, name), name))
