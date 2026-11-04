import contextlib, uuid
from datetime import date
import oracledb
from amrs import db
from amrs.gui import MainWindow, Login
from PySide6.QtWidgets import QApplication
import os

app=QApplication.instance() or QApplication([])
c=oracledb.connect(user='AMRS',password=os.environ['AMRS_DB_PASSWORD'],dsn='localhost:1521/FREEPDB1')
@contextlib.contextmanager
def shared(): yield c
db.connection=shared
x=uuid.uuid4().hex[:8].upper()
try:
    email='q'+x+'@example.test'
    db.signup_teacher('Temporary Teacher',email,'Testing-123','Department')
    teacher=db.login('TEACHER',email,'Testing-123')
    matching=db.add_student('Matching Student','A'+x,'','',1,1,2025)
    different=db.add_student('Different Student','B'+x,'','',1,2,2025)
    db.add_course('Q'+x,'Temporary Course',3,1,teacher['user_id'],1)
    course=db.one('SELECT course_id FROM courses WHERE course_code=:code',{'code':'Q'+x})['course_id']
    db.enroll_all_students(course)
    students=db.course_students(course);ids={s['student_id'] for s in students}
    assert matching in ids and different not in ids
    db.mark_attendance(teacher,course,matching,date.today(),'PRESENT','MANUAL')
    w=MainWindow(teacher,Login());w.mark_course.setCurrentIndex(w.mark_course.findData(course));w.refresh_camera_roster()
    assert 'Present / late: 1' in w.camera_roster_summary.text()
    assert 'Temporary Course' in w.camera_session.text() and 'Temporary Course' in w.qr_session.text()
    assert any(w.camera_roster.item(i,0).text()=='A'+x for i in range(w.camera_roster.rowCount()))
    w.close()
    print('PASS: filtered enrollment, selected session context and live roster')
finally:
    c.rollback();c.close();print('Temporary records rolled back')
