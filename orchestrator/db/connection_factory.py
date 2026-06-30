from config.settings import SOURCE_CONFIG_DB, TARGET_DB
from db.connection_manager import ConnectionManager


class ConnectionFactory:

    @staticmethod
    def get_origin_connection(user, password):
        return ConnectionManager(user, password, SOURCE_CONFIG_DB)

    @staticmethod
    def get_target_connection(user, password):
        return ConnectionManager(user, password, TARGET_DB)