class ConfigRepository:

    def __init__(self, connection):
        self.connection = connection

    def get_active_accounts(self):
        """
        Devuelve cuentas activas.
        """
        sql = """
            SELECT COD_CUENTA
            FROM ARCH_SCHEMA_CONFIG
            WHERE FLG_ACTIVO = 1
        """

        cursor = self.connection.cursor()
        cursor.execute(sql)

        return [row[0] for row in cursor.fetchall()]

    def get_due_processes(self):
        """
        Devuelve procesos pendientes de ejecutar.
        """
        sql = """
            SELECT
                COD_CUENTA,
                ID_PROCESO,
                DIAS_RETENCION,
                FRECUENCIA,
                HORA_EJECUCION,
                PROXIMA_EJECUCION
            FROM ARCH_SCHEMA_PROCESS
            WHERE FLG_ACTIVO = 1
              AND PROXIMA_EJECUCION <= SYSDATE
            ORDER BY PROXIMA_EJECUCION
        """

        cursor = self.connection.cursor()
        cursor.execute(sql)

        return cursor.fetchall()