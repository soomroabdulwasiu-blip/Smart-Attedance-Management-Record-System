import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication
from amrs.gui import Login

def test_role_labels_and_login_fields_are_cleared():
    app=QApplication.instance() or QApplication([])
    w=Login()
    for role,expected in [('ADMIN','Email / Username'),('TEACHER','Email / Username'),('STUDENT','Email / Roll number')]:
        w.select_role(role)
        assert w.identity_label.text()==expected
        assert not w.identity.text() and not w.pw.text()
        expected_hint = 'Enter Student Email Address or Roll No' if role == 'STUDENT' else f'Enter {role.title()} Email Address'
        assert w.identity.placeholderText() == expected_hint
        assert w.pw.placeholderText() == f'Enter {role.title()} Password'
        w.identity.setText('previous-user');w.pw.setText('secret')
        w.show_roles()
        assert not w.identity.text() and not w.pw.text()
    w.select_role('ADMIN');w.identity.setText('previous-user');w.pw.setText('secret');w.select_role('TEACHER')
    assert not w.identity.text() and not w.pw.text()
    w.close()
