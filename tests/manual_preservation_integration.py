import os,contextlib,uuid
from datetime import date
import oracledb
from PySide6.QtWidgets import QApplication
from amrs import db,gui
app=QApplication([]);app.setStyleSheet(gui.STYLE);errors=[];gui.alert=lambda *a:None;gui.error=lambda p,e:errors.append(str(e))
c=oracledb.connect(user='AMRS',password=os.environ['AMRS_DB_PASSWORD'],dsn='localhost:1521/FREEPDB1')
@contextlib.contextmanager
def shared():yield c
db.connection=shared;x=uuid.uuid4().hex[:8].upper()
try:
 email='t'+x+'@example.test';db.signup_teacher('Temp Teacher',email,'Testing-123','Software Engineering');teacher=db.login('TEACHER',email,'Testing-123')
 one=db.add_student('Temp One','A'+x,'','',1,1,2025);two=db.add_student('Temp Two','B'+x,'','',1,1,2025)
 db.add_course('T'+x,'Temporary',3,1,teacher['user_id'],1);course=db.one('SELECT course_id FROM courses WHERE course_code=:code',{'code':'T'+x})['course_id'];db.enroll_student(course,one);db.enroll_student(course,two)
 db.mark_attendance(teacher,course,one,date.today(),'PRESENT','FACE',0.95)
 w=gui.MainWindow(teacher,gui.Login());w.mark_course.setCurrentIndex(w.mark_course.findData(course));w.load_roster()
 assert w.roster.cellWidget(0,2).currentText()=='PRESENT' and w.roster.cellWidget(1,2).currentText()=='Not marked'
 w.roster.cellWidget(1,2).setCurrentText('ABSENT');w.save_roster();assert not errors,errors
 rec=db.attendance(teacher,course);by_id={r['student_id']:r for r in rec}
 assert by_id[one]['status']=='PRESENT' and by_id[one]['check_in_method']=='FACE'
 assert by_id[two]['status']=='ABSENT' and by_id[two]['check_in_method']=='MANUAL'
 try:db.mark_bulk(teacher,course,date.today(),[(one,'ABSENT'),('not-enrolled','PRESENT')])
 except ValueError:pass
 else:raise AssertionError('Invalid enrollment was accepted')
 assert {r['student_id']:r for r in db.attendance(teacher,course)}[one]['status']=='PRESENT'
 w.save_roster();assert errors and 'no new or changed' in errors[-1];errors.clear()
 # A concurrent authorized manual edit must make this form's earlier snapshot stale.
 # Repeated automated check-ins intentionally preserve the previously saved result.
 w.roster.cellWidget(0,2).setCurrentText('ABSENT');db.mark_attendance(teacher,course,one,date.today(),'LATE','MANUAL')
 w.save_roster();assert errors and 'changed after loading' in errors[-1]
 assert {r['student_id']:r for r in db.attendance(teacher,course)}[one]['status']=='LATE'
 print('PASS: manual form preloads Face/QR records, saves only edits, preserves existing attendance method');w.close()
finally:c.rollback();c.close();print('Temporary test data rolled back')
