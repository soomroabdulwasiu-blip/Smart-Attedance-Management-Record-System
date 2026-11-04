import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from amrs import gui

def test_attendance_status_colors_do_not_change_values():
    app=QApplication.instance() or QApplication([])
    table=gui.table(['Status','Face'])
    gui.fill(table,[{'status':'PRESENT','face_status':'Enrolled'},{'status':'ABSENT','face_status':'Not enrolled'}],['status','face_status'])
    assert table.item(0,0).text()=='PRESENT' and table.item(1,0).text()=='ABSENT'
    assert table.item(0,0).foreground().color()!=table.item(1,0).foreground().color()
