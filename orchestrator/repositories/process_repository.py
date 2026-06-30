from datetime import datetime, timedelta

class ProcessRepository:

    def __init__(self, connection):
        self.connection = connection

    def get_active_processes(self, cuenta):

        # Modificamos el WHERE para que permita registros donde PROXIMA_EJECUCION sea NULL
        sql = """
            SELECT
                A.ID_PROCESO,
                B.NOMBRE_PROCESO
            FROM ARCH_SCHEMA_PROCESS A
            JOIN ARCHIVO_PROCESO_CAB B ON A.ID_PROCESO = B.ID_PROCESO
            WHERE A.COD_CUENTA = :1
            AND A.FLG_ACTIVO = 1
            AND (A.PROXIMA_EJECUCION IS NULL OR A.PROXIMA_EJECUCION <= SYSDATE)
            ORDER BY A.ID_PROCESO
        """

        cursor = self.connection.cursor()
        cursor.execute(sql, [cuenta])
        rows = cursor.fetchall()

        print(f"[DEBUG] {cuenta} procesos elegibles: {rows}")
        return [
            {
                "id": r[0],
                "name": r[1]
            }
            for r in rows
        ]
    
    def get_retention_days(self, cuenta, process_id):

        sql = """
            SELECT DIAS_RETENCION
            FROM ARCH_SCHEMA_PROCESS
            WHERE COD_CUENTA = :1
            AND ID_PROCESO = :2
        """

        cursor = self.connection.cursor()
        cursor.execute(sql, [cuenta, process_id])

        row = cursor.fetchone()

        return row[0]
    
    def update_next_execution(self, cuenta, process_id):

        # 1. Leer configuración actual
        sql = """
            SELECT frecuencia,
                hora_ejecucion,
                dia_semana,
                dia_mes
            FROM w4wcom.arch_schema_process
            WHERE cod_cuenta = :1
            AND id_proceso = :2
        """

        cur = self.connection.cursor()
        cur.execute(sql, [cuenta, process_id])

        row = cur.fetchone()

        if not row:
            raise Exception(
                f"No existe configuración para {cuenta}-{process_id}"
            )

        frecuencia, hora_ejecucion, dia_semana, dia_mes = row

        # 2. Parsear hora
        hora, minuto = map(int, hora_ejecucion.split(":"))

        now = datetime.now()

        # 3. Calcular próxima ejecución
        if frecuencia == "DAILY":

            next_run = now + timedelta(days=1)
            next_run = next_run.replace(
                hour=hora,
                minute=minuto,
                second=0,
                microsecond=0
            )

        elif frecuencia == "WEEKLY":

            target_day = dia_semana - 1

            days_ahead = target_day - now.weekday()

            if days_ahead <= 0:
                days_ahead += 7

            next_run = now + timedelta(days=days_ahead)

            next_run = next_run.replace(
                hour=hora,
                minute=minuto,
                second=0,
                microsecond=0
            )

        elif frecuencia == "MONTHLY":

            next_month = now.month + 1
            next_year = now.year

            if next_month > 12:
                next_month = 1
                next_year += 1

            next_run = datetime(
                next_year,
                next_month,
                dia_mes,
                hora,
                minuto
            )

        else:
            raise Exception(
                f"Frecuencia no soportada: {frecuencia}"
            )

        # 4. Actualizar tabla
        update_sql = """
            UPDATE w4wcom.arch_schema_process
            SET ultima_ejecucion = SYSDATE,
                proxima_ejecucion = :1
            WHERE cod_cuenta = :2
            AND id_proceso = :3
        """

        cur.execute(
            update_sql,
            [next_run, cuenta, process_id]
        )

        self.connection.commit()

        print(
            f"[SCHEDULER] {cuenta}-{process_id} "
            f"next_run={next_run}"
        )