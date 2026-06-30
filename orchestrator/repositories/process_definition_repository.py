class ProcessDefinitionRepository:

    def __init__(self, connection):
        self.connection = connection

    def get_process_steps(self, process_id):
        sql = """
            SELECT
                ORDEN_EJECUCION,
                NOMBRE_TABLA_ORIGEN,
                NOMBRE_PACKAGE,
                NOMBRE_SP_EXPORT,
                PARAM_TYPE,
                PARAM_VALUE,
                TABLA_DESTINO,
                CONFLICT_STRATEGY,
                PK_COLUMN
            FROM ARCHIVO_PROCESO_DET
            WHERE ID_PROCESO = :1
              AND FLG_ACTIVO = 1
            ORDER BY ORDEN_EJECUCION
        """

        cursor = self.connection.cursor()
        cursor.execute(sql, [process_id])

        rows = cursor.fetchall()

        return [
            {
                "order": r[0],
                "table": r[1],
                "package": r[2],
                "procedure": r[3],
                "param_type": r[4],
                "param_value": r[5],
                "tabla_destino": r[6],
                "conflict_strategy": r[7] if r[7] else "IGNORE",
                "pk_column": r[8]
            }
            for r in rows
        ]