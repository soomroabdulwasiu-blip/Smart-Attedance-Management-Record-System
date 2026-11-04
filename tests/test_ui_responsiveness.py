import os,time
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QTimer,QEventLoop
from PySide6.QtWidgets import QApplication,QWidget
import pytest
from amrs import gui,db,face

@pytest.fixture(scope='module')
def app():return QApplication.instance() or QApplication([])

def run_events(ms):
    loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()

def test_login_does_not_block_ui(app,monkeypatch):
    events=[]
    def slow_login(*args):time.sleep(.4);return {'role':'STUDENT','user_id':'T','full_name':'Test','email':'test@example.com'}
    class DummyMain(QWidget):
        def __init__(self,user,parent):super().__init__();events.append('success')
    monkeypatch.setattr(db,'login',slow_login);monkeypatch.setattr(gui,'MainWindow',DummyMain)
    from amrs import presentation_data
    monkeypatch.setattr(presentation_data,'prefetch',lambda user:{})
    w=gui.Login();w.show();w.select_role('STUDENT');w.identity.setText('test@example.com');w.pw.setText('password');w.login()
    assert not w.pages.isEnabled();QTimer.singleShot(80,lambda:events.append('heartbeat'));run_events(900)
    assert events==['heartbeat','success'] and w.pages.isEnabled() and w._login_task is None
    w.main.close();w.close()

def test_batch_runs_in_background_and_cancels_remaining(app,monkeypatch):
    monkeypatch.setattr(db,'students',lambda:[{'student_id':'S1','roll_number':'R1','full_name':'Test','face_enrolled':0}])
    events=[];monkeypatch.setattr(gui,'alert',lambda parent,msg,*a:events.append(msg))
    class FakeEngine:
        def save_reference(self,sid,path):time.sleep(.25)
    monkeypatch.setattr(face,'FaceEngine',FakeEngine)
    from amrs import privacy
    monkeypatch.setattr(privacy,'record_consent',lambda *a:None)
    d=gui.BatchEnrollment(None);d.consent.setChecked(True);d.entries=[('S1','Test','a'),('S2','Test','b'),('S3','Test','c')];d.tab.setRowCount(3);d.show();d.run_batch();heartbeat=[]
    QTimer.singleShot(80,lambda:heartbeat.append(True));QTimer.singleShot(350,d.reject);run_events(1300)
    assert heartbeat and not d.worker.isRunning() and d.worker.cancelled and d.close_button.isEnabled()
    assert events and 'cancelled' in events[-1] and d.tab.item(0,2).text()=='Enrolled'
    d.close()
