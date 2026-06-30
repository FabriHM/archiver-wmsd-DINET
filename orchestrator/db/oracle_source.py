from config.settings import ORACLE_DSN
from db.connection_manager import ConnectionManager


class OracleSource:

    def __init__(self, user: str, password: str):
        self.conn_manager = ConnectionManager(
            user=user,
            password=password,
            dsn=ORACLE_DSN
        )

    def get_connection(self):
        return self.conn_manager.get_connection()