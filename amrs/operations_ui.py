"""Class administration, attendance policy and redacted operational diagnostics."""

from datetime import date

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QLabel,
    QMessageBox,
    QSpinBox,
    QVBoxLayout,
)

from . import academic, db
from .gui import action, field, fill, form_cell, load_combo, table, text_hint
from .hardware_ui import AsyncPanel


class ClassesPanel(AsyncPanel):
    def __init__(self, user, parent=None):
        super().__init__(user, parent)
        self.rows = []
        self.edit_id = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            text_hint(
                "Group courses into academic classes and sections. Course-level enrollment remains the attendance eligibility boundary."
            )
        )
        self.table = table(["Class", "Section", "Department", "Semester", "Year"])
        self.table.setMinimumHeight(200)
        self.table.itemSelectionChanged.connect(self.selected)
        layout.addWidget(self.table)
        self.name = field("Class name")
        self.section = field("e.g. A")
        self.department = QComboBox()
        self.semester = QSpinBox()
        self.semester.setRange(1, 16)
        self.year = QSpinBox()
        self.year.setRange(1990, 2200)
        self.year.setValue(date.today().year)
        grid = QGridLayout()
        for i, (label, widget) in enumerate(
            (
                ("Class name", self.name),
                ("Section", self.section),
                ("Department", self.department),
                ("Semester", self.semester),
                ("Academic year", self.year),
            )
        ):
            grid.addWidget(form_cell(label, widget), i // 2, i % 2)
        layout.addLayout(grid)
        buttons = QGridLayout()
        for i, (caption, fn) in enumerate(
            (
                ("Save class", self.save),
                ("Clear form", self.clear),
                ("Remove class", self.remove),
                ("Refresh classes", self.refresh),
            )
        ):
            buttons.addWidget(action(caption, fn), i // 2, i % 2)
        layout.addLayout(buttons)
        self.course = QComboBox()
        layout.addWidget(form_cell("Course to link to the selected class", self.course))
        layout.addWidget(action("Assign course to class", self.assign))
        layout.addWidget(self.notice)
        layout.addStretch()
        self.refresh()

    def refresh(self):
        self.submit(
            lambda: (
                academic.classes(self.user),
                db.departments(),
                db.courses(self.user),
            ),
            self.display,
        )

    def display(self, result):
        self.rows, depts, courses = result
        fill(
            self.table,
            self.rows,
            ["class_name", "section_name", "dept_name", "semester", "academic_year"],
        )
        load_combo(self.department, depts, lambda r: r["dept_name"], "dept_id")
        load_combo(
            self.course,
            courses,
            lambda r: r["course_code"] + " — " + r["course_name"],
            "course_id",
        )

    def selected(self):
        i = self.table.currentRow()
        if 0 <= i < len(self.rows):
            row = self.rows[i]
            self.edit_id = row["class_id"]
            self.name.setText(row["class_name"])
            self.section.setText(row["section_name"])
            self.department.setCurrentIndex(self.department.findData(row["dept_id"]))
            self.semester.setValue(row["semester"])
            self.year.setValue(row["academic_year"])

    def clear(self):
        self.edit_id = None
        self.name.clear()
        self.section.clear()
        self.table.clearSelection()

    def save(self):
        args = (
            self.user,
            self.name.text(),
            self.department.currentData(),
            self.semester.value(),
            self.section.text(),
            self.year.value(),
            self.edit_id,
        )
        self.submit(
            lambda: academic.save_class(*args), lambda _: (self.clear(), self.refresh())
        )

    def assign(self):
        class_id, course = self.edit_id, self.course.currentData()
        if not class_id or not course:
            self.notice.setText("Select a saved class and a course first.")
            return
        self.submit(lambda: academic.assign_course(self.user, class_id, course))

    def remove(self):
        class_id = self.edit_id
        if not class_id:
            self.notice.setText("Select a saved class first.")
            return
        if (
            QMessageBox.question(
                self,
                "Remove class",
                "Remove this class grouping? Course enrollment and attendance will be preserved.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.submit(
            lambda: academic.delete_class(self.user, class_id),
            lambda _: (self.clear(), self.refresh()),
        )


class OperationsPanel(AsyncPanel):
    def __init__(self, user, parent=None):
        super().__init__(user, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(
            text_hint(
                "Institution settings apply to report interpretation and teacher correction permissions. They do not rewrite historical attendance status."
            )
        )
        self.minimum = QSpinBox()
        self.minimum.setRange(0, 100)
        self.edit_days = QSpinBox()
        self.edit_days.setRange(0, 365)
        self.late = QCheckBox("Include late records in attendance %")
        grid = QGridLayout()
        grid.addWidget(form_cell("Minimum attendance (%)", self.minimum), 0, 0)
        grid.addWidget(
            form_cell("Teacher correction window (days)", self.edit_days), 0, 1
        )
        layout.addLayout(grid)
        layout.addWidget(self.late)
        grid = QGridLayout()
        for i, (caption, fn) in enumerate(
            (
                ("Save settings", self.save_policy),
                ("Refresh audit", self.refresh),
                ("Check diagnostics", self.diagnostics),
            )
        ):
            grid.addWidget(action(caption, fn), i // 2, i % 2)
        layout.addLayout(grid)
        layout.addWidget(action("Export safe diagnostics", self.export_diagnostics))
        self.diagnostic = QLabel("Diagnostics have not been run.")
        self.diagnostic.setObjectName("helperText")
        self.diagnostic.setWordWrap(True)
        layout.addWidget(self.diagnostic)
        self.audit = table(["Time", "Role", "Action", "Record", "Detail"])
        self.audit.setMinimumHeight(250)
        layout.addWidget(self.audit)
        layout.addWidget(self.notice)
        self.refresh()

    def refresh(self):
        self.submit(
            lambda: (academic.get_policy(self.user), db.audit_records(self.user)),
            self.display,
        )

    def display(self, result):
        policy, audit = result
        self.minimum.setValue(int(policy["minimum_percent"]))
        self.edit_days.setValue(policy["editing_days"])
        self.late.setChecked(policy["late_counts_present"])
        fill(
            self.audit,
            audit,
            ["created_at", "actor_role", "action", "entity_id", "detail"],
        )

    def save_policy(self):
        values = {
            "minimum_percent": self.minimum.value(),
            "editing_days": self.edit_days.value(),
            "late_counts_present": self.late.isChecked(),
        }
        self.submit(
            lambda: academic.save_policy(self.user, values), lambda _: self.refresh()
        )

    def diagnostics(self):
        def inspect():
            import importlib.util

            from .face import DETECTOR, RECOGNIZER
            from .migrations.runner import require_current

            with db.connection() as connection:
                require_current(connection)
                connection.cursor().execute("SELECT 1 FROM dual")
            return (
                "Oracle: connected • Schema: current • "
                + (
                    "Face models: available"
                    if DETECTOR.is_file() and RECOGNIZER.is_file()
                    else "Face models: missing — run python tools/fetch_models.py"
                )
                + " • Camera library: "
                + ("available" if importlib.util.find_spec("cv2") else "missing")
                + " • Physical camera and Gmail delivery: not tested by this diagnostic."
            )

        self.submit(inspect, self.diagnostic.setText)

    def export_diagnostics(self):
        from .diagnostics import export

        path, _ = QFileDialog.getSaveFileName(
            self, "Export diagnostics", "AMRS-diagnostics.zip", "ZIP (*.zip)"
        )
        if path:
            self.submit(
                lambda: export(path),
                lambda _: self.notice.setText(
                    "Safe diagnostics exported. Passwords, face templates and database records are excluded."
                ),
            )


class MyClassesPanel(AsyncPanel):
    def __init__(self, user, parent=None):
        super().__init__(user, parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.profile = QLabel(user.get("full_name", "") + " • " + user.get("email", ""))
        self.profile.setObjectName("helperText")
        self.profile.setWordWrap(True)
        layout.addWidget(self.profile)
        layout.addWidget(
            text_hint(
                "Only your assigned or enrolled courses are listed. Class groupings appear after an administrator assigns courses to sections."
            )
        )
        self.courses = table(["Code", "Course"])
        self.courses.setMinimumHeight(180)
        layout.addWidget(self.courses)
        self.classes = table(["Class", "Section", "Semester", "Year"])
        self.classes.setMinimumHeight(180)
        layout.addWidget(self.classes)
        layout.addWidget(action("Refresh my profile & classes", self.refresh))
        layout.addWidget(self.notice)
        self.refresh()

    def refresh(self):
        def read():
            return (
                db.courses(self.user),
                academic.classes(self.user),
                db.student_profile(self.user)
                if self.user["role"] == "STUDENT"
                else None,
            )

        def display(result):
            courses, classes, profile = result
            fill(self.courses, courses, ["course_code", "course_name"])
            fill(
                self.classes,
                classes,
                ["class_name", "section_name", "semester", "academic_year"],
            )
            if profile:
                self.profile.setText(
                    self.user.get("full_name", "")
                    + " • "
                    + str(profile.get("roll_number", ""))
                    + " • "
                    + str(profile.get("email") or self.user.get("email", ""))
                )

        self.submit(read, display)
