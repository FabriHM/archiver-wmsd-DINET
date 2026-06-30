from config.settings import ORACLE_DEST_DSN
from db.connection_manager import ConnectionManager


class OracleTarget:

    def __init__(self, user: str, password: str):
        self.conn_manager = ConnectionManager(
            user=user,
            password=password,
            dsn=ORACLE_DEST_DSN
        )

    def get_connection(self):
        return self.conn_manager.get_connection()