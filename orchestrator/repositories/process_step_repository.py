class ProcessStepRepository:

    def __init__(self, connection):
        self.connection = connection

    # ==========================================
    # START STEP (Soporta Individual y Lote)
    # ==========================================
    def start_step(
        self,
        process_id,
        item_id,
        entity_id,
        step_order,
        step_name
    ):
        """
        MERGE: si el step no existe lo crea con INTENTOS=0 y STATUS=STARTED.
        Soporta procesamiento masivo si 'entity_id' es una lista de diccionarios.
        """
        sql = """
            MERGE INTO ARCH_PROCESS_ITEM_STEP t
            USING (
                SELECT
                    :process_id AS PROCESS_ID,
                    :entity_id  AS ENTITY_ID,
                    :step_order AS STEP_ORDER
                FROM dual
            ) s
            ON (
                t.PROCESS_ID = s.PROCESS_ID
                AND t.ENTITY_ID = s.ENTITY_ID
                AND t.STEP_ORDER = s.STEP_ORDER
            )
            WHEN MATCHED THEN
                UPDATE SET
                    STATUS     = 'STARTED',
                    ERROR_MSG  = NULL,
                    START_TIME = SYSDATE,
                    END_TIME   = NULL
            WHEN NOT MATCHED THEN
                INSERT (
                    PROCESS_ID, ITEM_ID, ENTITY_ID,
                    STEP_ORDER, STEP_NAME, STATUS,
                    INTENTOS, START_TIME
                )
                VALUES (
                    :process_id, :item_id, :entity_id,
                    :step_order, :step_name, 'STARTED',
                    0, SYSDATE
                )
        """
        cursor = self.connection.cursor()
        try:
            # Si entity_id viene como lista, significa que mandamos el lote preparado desde el main
            if isinstance(entity_id, list):
                cursor.executemany(sql, entity_id)
            else:
                # Mantiene la compatibilidad individual original
                cursor.execute(sql, {
                    "process_id": process_id,
                    "item_id":    item_id,
                    "entity_id":  entity_id,
                    "step_order": step_order,
                    "step_name":  step_name
                })
        finally:
            cursor.close()

    # ==========================================
    # FINISH STEP (Soporta Individual y Lote)
    # ==========================================
    def finish_step(
        self,
        process_id,
        entity_id,
        step_order,
        status,
        rows_processed=0,
        error_msg=None
    ):
        """
        Única fuente de verdad para INTENTOS.
        Soporta procesamiento masivo si 'entity_id' es una lista de diccionarios.
        """
        sql = """
            UPDATE ARCH_PROCESS_ITEM_STEP
            SET
                STATUS         = :status,
                ROWS_PROCESSED = :rows_processed,
                ERROR_MSG      = :error_msg,
                END_TIME       = SYSDATE,
                INTENTOS       = INTENTOS + CASE WHEN :status_chk = 'ERROR' THEN 1 ELSE 0 END
            WHERE PROCESS_ID = :process_id
              AND ENTITY_ID  = :entity_id
              AND STEP_ORDER = :step_order
        """
        cursor = self.connection.cursor()
        try:
            if isinstance(entity_id, list):
                cursor.executemany(sql, entity_id)
            else:
                cursor.execute(sql, {
                    "status":         status,
                    "rows_processed": rows_processed,
                    "error_msg":      error_msg,
                    "status_chk":     status,
                    "process_id":     process_id,
                    "entity_id":      entity_id,
                    "step_order":     step_order
                })
        finally:
            cursor.close()

    # ==========================================
    # GET LAST SUCCESSFUL STEP
    # ==========================================
    def get_last_successful_step(self, process_id, entity_id):
        sql = """
            SELECT NVL(MAX(STEP_ORDER), 0)
            FROM ARCH_PROCESS_ITEM_STEP
            WHERE PROCESS_ID = :1
              AND ENTITY_ID  = :2
              AND STATUS     = 'OK'
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [process_id, entity_id])
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            cursor.close()

    # ==========================================
    # REACHED MAX RETRIES
    # ==========================================
    def reached_max_retries(
        self,
        process_id,
        entity_id,
        step_order,
        max_retries=3
    ):
        sql = """
            SELECT NVL(INTENTOS, 0)
            FROM ARCH_PROCESS_ITEM_STEP
            WHERE PROCESS_ID = :1
              AND ENTITY_ID  = :2
              AND STEP_ORDER = :3
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [process_id, entity_id, step_order])
            row = cursor.fetchone()
            return row is not None and row[0] >= max_retries
        finally:
            cursor.close()