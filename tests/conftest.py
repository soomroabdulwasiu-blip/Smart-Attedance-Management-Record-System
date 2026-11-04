"""Keep one Qt application alive through the suite and finish workers before teardown."""
import os
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
test_artifacts=Path(__file__).resolve().parents[1]/'artifacts'
os.environ.setdefault('AMRS_CONFIG_FILE',str(test_artifacts/'no-private-config.json'))
os.environ.setdefault('AMRS_DATA_DIR',str(test_artifacts/'test-runtime'))
os.environ.setdefault('AMRS_LOG_DIR',str(test_artifacts/'test-logs'))
import pytest
from PySide6.QtCore import QCoreApplication, QEvent, QThreadPool
from PySide6.QtWidgets import QApplication
import shiboken6


@pytest.fixture(scope='session', autouse=True)
def qt_application_lifetime():
    if os.getenv('AMRS_TEST_ORACLE')=='1':
        import re
        runtime=os.getenv('AMRS_DB_USERNAME','');owner=os.getenv('AMRS_DB_SCHEMA','')
        assert re.fullmatch(r'AMRST_R_[A-F0-9]{10}',runtime) and re.fullmatch(r'AMRST_M_[A-F0-9]{10}',owner) and runtime[8:]==owner[8:], 'Oracle tests require the disposable native runner; production targets are refused.'
    app = QApplication.instance() or QApplication([])
    yield app
    assert QThreadPool.globalInstance().waitForDone(5000), 'A background task did not finish.'
    for widget in app.topLevelWidgets():
        widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    # Destroy Qt while Python and its callbacks are still alive, not at interpreter exit.
    shiboken6.delete(app)
