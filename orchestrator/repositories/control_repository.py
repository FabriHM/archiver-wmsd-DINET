class ControlRepository:

    def __init__(self, connection):
        self.connection = connection

    # ==========================
    # CREATE PROCESS CONTROL
    # ==========================
    def create_process_control(
        self,
        process_name,
        cod_cuenta,
        tabla_origen,
        fecha_filtro,
        intentos=1
    ):
        sql = """
            INSERT INTO ARCH_PROCESS_CONTROL (
                PROCESS_NAME,
                COD_CUENTA,
                TABLA_ORIGEN,
                FECHA_FILTRO,
                FECHA_INICIO,
                ESTADO,
                INTENTOS
            )
            VALUES (
                :1, :2, :3, :4, SYSDATE, 'RUNNING', :5
            )
            RETURNING PROCESS_ID INTO :6
        """
        cursor = self.connection.cursor()
        try:
            process_id_var = cursor.var(int)
            cursor.execute(sql, [
                process_name,
                cod_cuenta,
                tabla_origen,
                fecha_filtro,
                intentos,
                process_id_var
            ])
            self.connection.commit()
            return process_id_var.getvalue()[0]
        finally:
            cursor.close()

    # ==========================
    # FINISH PROCESS CONTROL
    # ==========================
    def finish_process_control(self, process_run_id, estado):
        sql = """
            UPDATE ARCH_PROCESS_CONTROL
            SET ESTADO    = :1,
                FECHA_FIN = SYSDATE
            WHERE PROCESS_ID = :2
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [estado, process_run_id])
            self.connection.commit()
        finally:
            cursor.close()

    # ==========================
    # GET OPEN PROCESS
    # ==========================
    def get_open_process(self, process_name, cod_cuenta):
        sql = """
            SELECT PROCESS_ID
            FROM ARCH_PROCESS_CONTROL
            WHERE PROCESS_NAME = :1
              AND COD_CUENTA   = :2
              AND ESTADO IN ('RUNNING', 'ERROR', 'COMPLETADO_CON_ERRORES')
            ORDER BY PROCESS_ID DESC
            FETCH FIRST 1 ROWS ONLY
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [process_name, cod_cuenta])
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            cursor.close()

    # ==========================
    # GET LAST ATTEMPT
    # ==========================
    def get_last_attempt(self, process_name, cod_cuenta):
        sql = """
            SELECT NVL(MAX(INTENTOS), 0)
            FROM ARCH_PROCESS_CONTROL
            WHERE PROCESS_NAME = :1
              AND COD_CUENTA   = :2
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [process_name, cod_cuenta])
            row = cursor.fetchone()
            return row[0] if row else 0
        finally:
            cursor.close()

    # ==========================
    # CREATE PROCESS ITEMS
    # ==========================
    def create_process_items(self, process_run_id, cod_cuenta, entity_ids):

        print("[DEBUG] create_process_items inicio")

        cursor = self.connection.cursor()

        try:

            # ==========================
            # EXISTENTES
            # ==========================
            sql_select = """
                SELECT ENTITY_ID, ITEM_ID
                FROM ARCH_PROCESS_ITEM
                WHERE PROCESS_ID = :1
            """

            print("[DEBUG] ejecutando select existentes")
            cursor.execute(sql_select, [process_run_id])

            existing = {row[0]: row[1] for row in cursor.fetchall()}

            print(f"[DEBUG] existentes encontrados: {len(existing)}")

            item_map = dict(existing)

            # ==========================
            # NUEVOS
            # ==========================
            nuevos = [
                entity_id
                for entity_id in entity_ids
                if entity_id not in existing
            ]

            print(f"[DEBUG] entity_ids recibidos: {len(entity_ids)}")
            print(f"[DEBUG] items nuevos a insertar: {len(nuevos)}")

            if not nuevos:
                return item_map

            sql_insert = """
                INSERT INTO ARCH_PROCESS_ITEM
                (
                    PROCESS_ID,
                    ENTITY_ID,
                    ESTADO,
                    INTENTOS,
                    COD_CUENTA,
                    FECHA_INICIO
                )
                VALUES
                (
                    :1,
                    :2,
                    'PENDIENTE',
                    0,
                    :3,
                    SYSDATE
                )
            """

            data = [
                (
                    process_run_id,
                    entity_id,
                    cod_cuenta
                )
                for entity_id in nuevos
            ]

            print("[DEBUG] ejecutando inserción masiva")

            cursor.executemany(
                sql_insert,
                data
            )

            self.connection.commit()

            print(
                f"[DEBUG] insertados masivamente: {len(nuevos)}"
            )

            # ==========================
            # RECARGAR MAPA
            # ==========================
            cursor.execute(sql_select, [process_run_id])

            item_map = {
                row[0]: row[1]
                for row in cursor.fetchall()
            }

            print(
                f"[DEBUG] total items (existentes + nuevos): {len(item_map)}"
            )

            return item_map

        except Exception as e:

            self.connection.rollback()

            print(f"[ERROR] create_process_items: {e}")

            raise

        finally:
            cursor.close()

    # ==========================
    # GET EXISTING ITEMS
    # ==========================
    def get_existing_items(self, process_id):
        sql = """
            SELECT ENTITY_ID, ITEM_ID
            FROM ARCH_PROCESS_ITEM
            WHERE PROCESS_ID = :1
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [process_id])
            return {row[0]: row[1] for row in cursor.fetchall()}
        finally:
            cursor.close()

    # ==========================
    # GET RETRYABLE ITEMS (nivel item)
    # Usado para reanudación del proceso completo
    # ==========================
    def get_retryable_items(self, process_id, max_retries=3):
        """
        Devuelve items que NO están RECHAZADOS ni PROCESADOS.
        BUG ORIGINAL: faltaba el parámetro :2 (max_retries) en execute().
        """
        sql = """
            SELECT ITEM_ID, ENTITY_ID
            FROM ARCH_PROCESS_ITEM
            WHERE PROCESS_ID = :1
              AND ESTADO NOT IN ('PROCESADO', 'RECHAZADO')
              AND NVL(INTENTOS, 0) < :2
            ORDER BY ENTITY_ID
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [process_id, max_retries])   # ← FIX: pasaba [process_id] sin max_retries
            return {row[1]: row[0] for row in cursor.fetchall()}
        finally:
            cursor.close()

    # ==========================
    # GET RETRYABLE STEP ITEMS (nivel step)
    # Filtra entidades que necesitan ejecutar un step específico
    # ==========================
    def get_retryable_step_items(self, process_id, step_order, max_retries=3):
        """
        Devuelve entidades que deben ejecutar el step indicado:
          - Entidades no RECHAZADAS
          - Cuyo step aún no existe (PENDIENTE) 
            O cuyo step está en ERROR y tiene reintentos disponibles.

        BUG ORIGINAL: la query usaba named binds (:process_id, :step_order, etc.)
        pero repetía :step_order dos veces → ORA-01036.
        FIX: usar posicionales con alias únicos o pasar dict con claves únicas.
        """
        sql = """
            SELECT i.ENTITY_ID, i.ITEM_ID
            FROM ARCH_PROCESS_ITEM i
            WHERE i.PROCESS_ID = :process_id
            AND i.ESTADO <> 'RECHAZADO'

            -- VALIDAR STEP ANTERIOR
            AND (
                    :step_order = 1
                    OR EXISTS (
                        SELECT 1
                        FROM ARCH_PROCESS_ITEM_STEP p
                        WHERE p.PROCESS_ID = i.PROCESS_ID
                        AND p.ENTITY_ID  = i.ENTITY_ID
                        AND p.STEP_ORDER = :prev_step
                        AND p.STATUS     = 'OK'
                    )
            )

            AND (
                -- step no existe
                NOT EXISTS (
                    SELECT 1
                    FROM ARCH_PROCESS_ITEM_STEP s
                    WHERE s.PROCESS_ID = i.PROCESS_ID
                        AND s.ENTITY_ID  = i.ENTITY_ID
                        AND s.STEP_ORDER = :step_order
                )

                OR

                -- step con error reintentable
                EXISTS (
                    SELECT 1
                    FROM ARCH_PROCESS_ITEM_STEP s
                    WHERE s.PROCESS_ID  = i.PROCESS_ID
                        AND s.ENTITY_ID   = i.ENTITY_ID
                        AND s.STEP_ORDER  = :step_order
                        AND s.STATUS      = 'ERROR'
                        AND NVL(s.INTENTOS,0) < :max_retries
                )
            )

            ORDER BY i.ENTITY_ID
        """

        cursor = self.connection.cursor()
        try:
            # Named binds: Oracle acepta que :step_order aparezca N veces
            # siempre que el dict contenga esa clave UNA sola vez.
            cursor.execute(sql, {
                "process_id":  process_id,
                "step_order":  step_order,
                "prev_step":   step_order - 1,
                "max_retries": max_retries
            })
            return {row[0]: row[1] for row in cursor.fetchall()}
        finally:
            cursor.close()

    # ==========================
    # UPDATE PROCESS ITEM
    # ==========================
    def update_process_item(
        self,
        process_id,
        entity_id,
        estado,
        mensaje_error=None
    ):
        """
        BUG ORIGINAL: el SQL tenía :3 como placeholder de INTENTOS pero
        el execute no pasaba ese valor (el print mostraba 5 valores, el SQL
        esperaba 5 pero sin el parámetro correcto → ORA-01008).
        FIX: INTENTOS se maneja solo en ARCH_PROCESS_ITEM_STEP.finish_step.
             Aquí solo actualizamos ESTADO, MENSAJE_ERROR y FECHA_FIN.
             Si el estado es RECHAZADO, también seteamos FECHA_FIN.
        """
        sql = """
            UPDATE ARCH_PROCESS_ITEM
            SET
                ESTADO        = :1,
                MENSAJE_ERROR = :2,
                FECHA_FIN     = SYSDATE
            WHERE PROCESS_ID = :3
              AND ENTITY_ID  = :4
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [
                estado,
                mensaje_error,
                process_id,
                entity_id
            ])
            # No commit aquí: el caller (orquestador) hace commit global
        finally:
            cursor.close()

    # ==========================
    # FINALIZE PROCESS ITEM (marca PROCESADO si todos los steps son OK)
    # ==========================
    def finalize_process_item(self, process_id, entity_id):
        sql = """
            UPDATE ARCH_PROCESS_ITEM
            SET
                ESTADO        = 'PROCESADO',
                MENSAJE_ERROR = NULL,
                FECHA_FIN     = SYSDATE
            WHERE PROCESS_ID = :1
              AND ENTITY_ID  = :2
              AND NOT EXISTS (
                  SELECT 1
                  FROM ARCH_PROCESS_ITEM_STEP
                  WHERE PROCESS_ID = :1
                    AND ENTITY_ID  = :2
                    AND STATUS    <> 'OK'
              )
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [process_id, entity_id])
            self.connection.commit()
        finally:
            cursor.close()

    # ==========================
    # IS ENTITY REJECTED
    # ==========================
    def is_item_rejected(self, process_id, entity_id):
        sql = """
            SELECT 1
            FROM ARCH_PROCESS_ITEM
            WHERE PROCESS_ID = :1
              AND ENTITY_ID  = :2
              AND ESTADO     = 'RECHAZADO'
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [process_id, entity_id])
            return cursor.fetchone() is not None
        finally:
            cursor.close()

    # Alias para compatibilidad
    def is_entity_rejected(self, process_id, entity_id):
        return self.is_item_rejected(process_id, entity_id)

    # ==========================
    # IS STEP SUCCESS
    # ==========================
    def is_step_success(self, process_id, entity_id, step_order):
        sql = """
            SELECT 1
            FROM ARCH_PROCESS_ITEM_STEP
            WHERE PROCESS_ID = :1
              AND ENTITY_ID  = :2
              AND STEP_ORDER = :3
              AND STATUS     = 'OK'
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [process_id, entity_id, step_order])
            return cursor.fetchone() is not None
        finally:
            cursor.close()

    # ==========================
    # WRITE LOG
    # ==========================
    def write_log(self, process_run_id, cod_cuenta, nivel, mensaje, item_id=None):
        """
        BUG ORIGINAL: no había commit después del INSERT → los logs se perdían
        si había rollback posterior.
        FIX: commit inmediato en logs para garantizar trazabilidad incluso ante errores.
        """
        sql = """
            INSERT INTO ARCH_PROCESS_LOG (
                PROCESS_ID,
                COD_CUENTA,
                NIVEL,
                MENSAJE,
                ITEM_ID,
                FECHA
            )
            VALUES (:1, :2, :3, :4, :5, SYSDATE)
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [
                process_run_id,
                cod_cuenta,
                nivel,
                mensaje[:3900] if mensaje else mensaje,   # evitar ORA-01461 en mensajes largos
                item_id
            ])
            self.connection.commit()   # ← FIX: commit inmediato para no perder logs en rollback
        finally:
            cursor.close()

    # ==========================
    # GET PENDING ITEMS
    # ==========================
    def get_pending_items(self, process_id):
        sql = """
            SELECT ENTITY_ID
            FROM ARCH_PROCESS_ITEM
            WHERE PROCESS_ID = :1
              AND ESTADO IN ('PENDIENTE', 'ERROR')
              AND NVL(INTENTOS, 0) < 3
            ORDER BY ITEM_ID
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [process_id])
            return [r[0] for r in cursor.fetchall()]
        finally:
            cursor.close()

    # ==========================
    # GET ITEM ID
    # ==========================
    def get_item_id(self, process_id, entity_id):
        sql = """
            SELECT ITEM_ID
            FROM ARCH_PROCESS_ITEM
            WHERE PROCESS_ID = :1
              AND ENTITY_ID  = :2
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [process_id, entity_id])
            row = cursor.fetchone()
            return row[0] if row else None
        finally:
            cursor.close()

    # ==========================
    # HAS ERRORS
    # ==========================
    def has_errors(self, process_id):
        sql = """
            SELECT COUNT(*)
            FROM ARCH_PROCESS_ITEM
            WHERE PROCESS_ID = :1
              AND ESTADO IN ('ERROR', 'RECHAZADO')
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [process_id])
            return cursor.fetchone()[0] > 0
        finally:
            cursor.close()

    # ==========================
    # UPDATE EXPECTED ROWS
    # ==========================
    def update_expected_rows(self, process_id, total):
        sql = """
            UPDATE ARCH_PROCESS_CONTROL
            SET REGISTROS_ESPERADOS = :1
            WHERE PROCESS_ID = :2
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [total, process_id])
            self.connection.commit()
        finally:
            cursor.close()

    # ==========================
    # UPDATE INSERTED ROWS
    # ==========================
    def update_inserted_rows(self, process_id):
        sql = """
            UPDATE ARCH_PROCESS_CONTROL
            SET REGISTROS_INSERTADOS = (
                SELECT COUNT(*)
                FROM ARCH_PROCESS_ITEM
                WHERE PROCESS_ID = :1
                  AND ESTADO = 'PROCESADO'
            )
            WHERE PROCESS_ID = :1
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [process_id])
            self.connection.commit()
        finally:
            cursor.close()

    # ==========================
    # UPDATE PROCESS METADATA
    # ==========================
    def update_process_metadata(self, process_id, tabla_origen, fecha_filtro):
        sql = """
            UPDATE ARCH_PROCESS_CONTROL
            SET TABLA_ORIGEN = :1,
                FECHA_FILTRO = :2
            WHERE PROCESS_ID = :3
        """
        cursor = self.connection.cursor()
        try:
            cursor.execute(sql, [tabla_origen, fecha_filtro, process_id])
            self.connection.commit()
        finally:
            cursor.close()