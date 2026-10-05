"""Storage for screenshot records. SQLite (local, default) or MongoDB Atlas.

Every record keeps a back-reference to the real file (`path`, `filename`),
so a search result can always open the original screenshot.
Only text is stored here, never the image itself.
"""
import sqlite3

import config

FIELDS = ("id", "path", "filename", "taken_at", "indexed_at",
          "title", "description", "text_seen", "tags")


class SqliteStore:
    name = "SQLite (local file)"

    def __init__(self):
        con = self._con()
        con.execute(
            "CREATE TABLE IF NOT EXISTS shots (id TEXT PRIMARY KEY, path TEXT UNIQUE, "
            "filename TEXT, taken_at TEXT, indexed_at TEXT, title TEXT, description TEXT, "
            "text_seen TEXT, tags TEXT)"
        )
        con.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS shots_fts USING fts5"
            "(id UNINDEXED, title, description, text_seen, tags)"
        )
        con.commit()
        con.close()

    def _con(self):  # a fresh connection per call keeps it safe across threads
        return sqlite3.connect(config.SQLITE_PATH)

    def _query(self, sql, args=()):
        con = self._con()
        try:
            cur = con.execute(sql, args)
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        finally:
            con.close()

    def exists(self, path):
        return bool(self._query("SELECT 1 FROM shots WHERE path=?", (str(path),)))

    def add(self, r):
        con = self._con()
        try:
            con.execute("INSERT OR REPLACE INTO shots VALUES (?,?,?,?,?,?,?,?,?)",
                        tuple(r[k] for k in FIELDS))
            con.execute("DELETE FROM shots_fts WHERE id=?", (r["id"],))
            con.execute("INSERT INTO shots_fts VALUES (?,?,?,?,?)",
                        (r["id"], r["title"], r["description"], r["text_seen"], r["tags"]))
            con.commit()
        finally:
            con.close()

    def get(self, shot_id):
        rows = self._query("SELECT * FROM shots WHERE id=?", (str(shot_id),))
        return rows[0] if rows else None

    def _date_sql(self, since, until, args, prefix=""):
        sql = ""
        if since:
            sql += f" AND {prefix}taken_at >= ?"
            args.append(since)
        if until:
            sql += f" AND {prefix}taken_at <= ?"
            args.append(until)
        return sql

    def search(self, words, since=None, until=None, limit=8):
        words = [w for w in words if w]
        if not words:
            return self.recent(since, until, limit)
        args = [" OR ".join(f'"{w}"' for w in words)]
        sql = ("SELECT s.* FROM shots_fts JOIN shots s ON s.id = shots_fts.id "
               "WHERE shots_fts MATCH ?")
        sql += self._date_sql(since, until, args, "s.")
        sql += " ORDER BY bm25(shots_fts) LIMIT ?"
        args.append(limit)
        return self._query(sql, args)

    def recent(self, since=None, until=None, limit=10):
        args = []
        sql = "SELECT * FROM shots WHERE 1=1" + self._date_sql(since, until, args)
        sql += " ORDER BY taken_at DESC, indexed_at DESC LIMIT ?"
        args.append(limit)
        return self._query(sql, args)

    def all(self):
        return self._query("SELECT * FROM shots")

    def count(self):
        return self._query("SELECT COUNT(*) AS n FROM shots")[0]["n"]


class MongoStore:
    name = "MongoDB Atlas (text descriptions only)"

    def __init__(self, uri):
        from pymongo import MongoClient

        self.col = MongoClient(uri, serverSelectionTimeoutMS=20000)[config.MONGODB_DB]["shots"]
        self.col.create_index("id", unique=True)
        self.col.create_index("path", unique=True)
        self.col.create_index(
            [("title", "text"), ("description", "text"), ("text_seen", "text"), ("tags", "text")],
            name="shots_text",
        )

    def exists(self, path):
        return self.col.count_documents({"path": str(path)}, limit=1) > 0

    def add(self, r):
        self.col.replace_one({"id": r["id"]}, dict(r), upsert=True)

    def get(self, shot_id):
        return self.col.find_one({"id": str(shot_id)}, {"_id": 0})

    @staticmethod
    def _dates(q, since, until):
        d = {}
        if since:
            d["$gte"] = since
        if until:
            d["$lte"] = until
        if d:
            q["taken_at"] = d
        return q

    def search(self, words, since=None, until=None, limit=8):
        words = [w for w in words if w]
        if not words:
            return self.recent(since, until, limit)
        q = self._dates({"$text": {"$search": " ".join(words)}}, since, until)  # space = OR
        cur = (self.col.find(q, {"_id": 0, "score": {"$meta": "textScore"}})
               .sort([("score", {"$meta": "textScore"})]).limit(limit))
        return list(cur)

    def recent(self, since=None, until=None, limit=10):
        q = self._dates({}, since, until)
        return list(self.col.find(q, {"_id": 0}).sort("taken_at", -1).limit(limit))

    def all(self):
        return list(self.col.find({}, {"_id": 0}))

    def count(self):
        return self.col.count_documents({})


def get_store():
    return MongoStore(config.MONGODB_URI) if config.MONGODB_URI else SqliteStore()
