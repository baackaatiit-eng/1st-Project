import sqlite3
import threading
import time


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.lock = threading.Lock()
        self.db.executescript("""
        create table if not exists projects(id integer primary key, owner integer, name text, spec text, created real);
        create table if not exists builds(id integer primary key, project_id integer, status text, summary text,
            zip_path text, started real, finished real);
        create table if not exists logs(id integer primary key, build_id integer, ts real, line text);
        """)

    def _x(self, q, a=()):
        with self.lock:
            c = self.db.execute(q, a)
            self.db.commit()
            return c

    def add_project(self, owner, name, spec):
        return self._x("insert into projects(owner,name,spec,created) values(?,?,?,?)", (owner, name, spec, time.time())).lastrowid

    def add_build(self, pid):
        return self._x("insert into builds(project_id,status,started) values(?,?,?)", (pid, "running", time.time())).lastrowid

    def log(self, bid, line):
        self._x("insert into logs(build_id,ts,line) values(?,?,?)", (bid, time.time(), line))

    def finish(self, bid, status, summary, zip_path=None):
        self._x("update builds set status=?,summary=?,zip_path=?,finished=? where id=?", (status, summary, zip_path, time.time(), bid))

    def projects(self, owner=None):
        q, a = ("select id,name,created from projects", ())
        if owner is not None:
            q, a = q + " where owner=?", (owner,)
        return self._x(q + " order by id desc", a).fetchall()

    def builds(self, pid):
        return self._x("select id,status,summary,zip_path from builds where project_id=? order by id desc", (pid,)).fetchall()

    def get_build(self, bid):
        return self._x("select id,project_id,status,summary,zip_path from builds where id=?", (bid,)).fetchone()

    def logs(self, bid):
        return [r[0] for r in self._x("select line from logs where build_id=? order by id", (bid,)).fetchall()]
