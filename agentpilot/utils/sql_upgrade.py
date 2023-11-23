from agentpilot.utils import sql
from packaging import version


class SQLUpgrade:
    def __init__(self):
        pass

    def v0_1_0(self):
        # Add new tables
        sql.execute("""
            CREATE TABLE "roles" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL,
                "config"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        sql.execute("""
            CREATE TABLE "functions" (
                "id"	INTEGER,
                "name"	TEXT NOT NULL DEFAULT '' UNIQUE,
                "config"	TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY("id" AUTOINCREMENT)
            )""")
        sql.execute("""
            CREATE TABLE "contexts_members" (
                "id"	INTEGER,
                "context_id"	INTEGER NOT NULL,
                "agent_id"	INTEGER NOT NULL,
                "agent_config"	TEXT NOT NULL DEFAULT '{}',
                "ordr"	INTEGER NOT NULL DEFAULT 0,
                "loc_x"	INTEGER NOT NULL DEFAULT 0,
                "loc_y"	INTEGER NOT NULL DEFAULT 0,
                "del"	INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY("agent_id") REFERENCES "agents"("id") ON DELETE CASCADE,
                PRIMARY KEY("id" AUTOINCREMENT),
                FOREIGN KEY("context_id") REFERENCES "contexts"("id") ON DELETE CASCADE
            )""")
        sql.execute("""
            CREATE TABLE "contexts_members_inputs" (
                "id"	INTEGER,
                "member_id"	INTEGER NOT NULL,
                "input_member_id"	INTEGER,
                "type"	INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY("id" AUTOINCREMENT),
                FOREIGN KEY("member_id") REFERENCES "contexts_members"("id") ON DELETE CASCADE,
                FOREIGN KEY("input_member_id") REFERENCES "contexts_members"("id") ON DELETE CASCADE
            )""")
        # Alter table and add foreign key to contexts_messages
        # FOREIGN KEY("context_id") REFERENCES "contexts"("id") ON DELETE CASCADE
        sql.execute("""
            CREATE TABLE "contexts_messages_new" (
                "id"	INTEGER,
                "unix"	INTEGER NOT NULL DEFAULT (CAST(strftime('%s', 'now') AS TYPE_NAME)),
                "context_id"	INTEGER,
                "member_id"	INTEGER,
                "role"	TEXT,
                "msg"	TEXT,
                "embedding_id"	INTEGER,
                "del"	INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY("member_id") REFERENCES "contexts_members"("id") ON DELETE CASCADE,
                PRIMARY KEY("id" AUTOINCREMENT),
                FOREIGN KEY("context_id") REFERENCES "contexts"("id") ON DELETE CASCADE
            )""")
        sql.execute("""
            INSERT INTO contexts_messages_new (id, unix, context_id, member_id, role, msg, embedding_id, del)
            SELECT id, unix, context_id, member_id, role, msg, embedding_id, del
            FROM contexts_messages""")
        sql.execute("""
            DROP TABLE contexts_messages""")
        sql.execute("""
            ALTER TABLE contexts_messages_new RENAME TO contexts_messages""")

        return '0.1.0'

    def upgrade(self, current_version):
        current_version = version.parse(current_version)
        if current_version < version.parse("0.1.0"):
            return self.v0_1_0()
        else:
            return str(current_version)


upgrade_script = SQLUpgrade()
versions = ['0.0.8', '0.1.0']
