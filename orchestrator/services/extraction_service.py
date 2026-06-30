from sp.sp_executor import SPExecutor


class ExtractionService:

    def __init__(self, connection_manager):
        self.connection_manager = connection_manager

    def extract_by_account(
        self,
        cuenta,
        package,
        procedure,
        input_params=None
    ):
        """
        Ejecuta SP sobre el schema de la cuenta.
        """

        source_conn = self.connection_manager.get_connection("source")

        try:
            if input_params is None:
                input_params = {}

            cursor = source_conn.cursor()

            cursor.execute(
                f"ALTER SESSION SET CURRENT_SCHEMA = {cuenta}"
            )

            print(f"Schema cambiado a {cuenta}")

            cursor.close()

            executor = SPExecutor(source_conn)

            columns, rows = executor.execute_cursor_sp(
                package=package,
                procedure=procedure,
                input_params=input_params
            )

            if rows is None:
                rows = []

            if not rows:
                print(f"[WARN] SP {procedure} no retornó datos")
                return [], []

            return columns, rows

        finally:
            source_conn.close()

    def extract_ids(self, rows, column_name, columns):

        if column_name not in columns:
            return []

        idx = columns.index(column_name)

        if not rows:
            return []

        return [row[idx] for row in rows]