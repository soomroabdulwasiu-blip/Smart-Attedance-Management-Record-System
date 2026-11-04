import os,contextlib,uuid,tempfile
from pathlib import Path
from datetime import date
import oracledb
from PySide6.QtWidgets import QApplication
from amrs import db,gui,settings
app=QApplication([]);app.setStyleSheet(gui.STYLE);errors=[];gui.error=lambda p,e:errors.append(str(e));gui.alert=lambda *a:None
c=oracledb.connect(user='AMRS',password=os.environ['AMRS_DB_PASSWORD'],dsn='localhost:1521/FREEPDB1');old_settings=settings.SETTINGS_PATH
@contextlib.contextmanager
def shared():yield c
db.connection=shared;x=uuid.uuid4().hex[:8].upper()
try:
 with tempfile.TemporaryDirectory(dir='work') as tmp:
  settings.SETTINGS_PATH=Path(tmp)/'ui_settings.json';teacher_email='t'+x+'@example.test';student_email='s'+x+'@example.test'
  db.signup_teacher('Temporary Teacher',teacher_email,'Testing-123','Software Engineering');db.signup_student('Temporary Student',student_email,'Testing-123','T'+x,1,1,2025)
  teacher=db.login('TEACHER',teacher_email,'Testing-123');student=db.login('STUDENT','T'+x,'Testing-123');db.add_course('T'+x,'Temporary Course',3,1,teacher['user_id'],1)
  course=db.one('SELECT course_id FROM courses WHERE course_code=:code',{'code':'T'+x})['course_id'];db.enroll_student(course,student['user_id']);db.mark_attendance(teacher,course,student['user_id'],date.today(),'PRESENT','FACE',.9)
  login=gui.Login();tw=gui.MainWindow(teacher,login);tw.resize(950,650);tw.show();app.processEvents()
  assert tw.page_titles[0]=='Dashboard' and [v.text() for v in tw.dashboard_values]==['1','1','1'],errors
  assert tw.camera_mirror.isChecked() is True
  for i in range(tw.tabs.count()):tw.select_tab(i);app.processEvents();assert tw.tabs.widget(i).horizontalScrollBar().maximum()==0
  tw.close();sw=gui.MainWindow(student,login);sw.resize(950,650);sw.show();app.processEvents()
  assert [v.text() for v in sw.dashboard_values]==['1','100.0%','1'],errors
  assert sw.dashboard_table.rowCount()==1
  for i in range(sw.tabs.count()):sw.select_tab(i);app.processEvents();assert sw.tabs.widget(i).horizontalScrollBar().maximum()==0
  sw.close();assert not errors,errors
  print('PASS: teacher/student live dashboard metrics, mirror default and responsive navigation')
finally:settings.SETTINGS_PATH=old_settings;c.rollback();c.close();print('Temporary dashboard records rolled back')
