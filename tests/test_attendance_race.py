from datetime import date
from types import SimpleNamespace
import oracledb
from amrs import db

def test_concurrent_checkin_duplicate_retries_update():
    class Cursor:
        def __init__(self):self.calls=[];self.rowcount=1
        def execute(self,sql,params):
            self.calls.append(sql)
            if sql==db.UPSERT_ATTENDANCE:raise oracledb.IntegrityError(SimpleNamespace(code=1))
        def fetchone(self):return (1,)
    cur=Cursor();db._mark(cur,{'role':'TEACHER','user_id':'T'},'C','S',date.today(),'PRESENT','FACE',.9)
    assert len(cur.calls)==3 and 'UPDATE attendance SET' in cur.calls[-1]

def test_other_integrity_errors_are_not_silenced():
    class Cursor:
        def execute(self,sql,params):
            if sql==db.UPSERT_ATTENDANCE:raise oracledb.IntegrityError(SimpleNamespace(code=2291))
        def fetchone(self):return (1,)
    import pytest
    with pytest.raises(oracledb.IntegrityError):db._mark(Cursor(),{'role':'TEACHER','user_id':'T'},'C','S',date.today(),'PRESENT','FACE',.9)
