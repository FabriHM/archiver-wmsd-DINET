class LoadService:

    def __init__(self, connection_manager):
        self.connection_manager = connection_manager

    def load_to_hist(
        self,
        table,
        columns,
        rows,
        extra_fields=None,
        conflict_strategy="IGNORE",
        pk_column=None,
        batch_size=5000
    ):
        if not rows:
            print("No hay datos para insertar")
            return 0

        target_conn = self.connection_manager.get_connection("target")

        try:
            cursor = target_conn.cursor()

            # =========================
            # COLUMNAS FINALES
            # =========================
            final_columns = [c.upper() for c in columns]

            if extra_fields:
                final_columns.extend([k.upper() for k in extra_fields.keys()])

            cols_sql = ",".join(final_columns)
            binds_sql = ",".join([f":{i+1}" for i in range(len(final_columns))])

            strategy = conflict_strategy.strip().upper()

            # =========================
            # PK COLUMN (SIMPLE O COMPUESTA)
            # =========================
            pk_cols = []
            if pk_column:
                pk_cols = [
                    c.strip().upper()
                    for c in pk_column.split(",")
                    if c.strip()
                ]

            # =========================
            # STRATEGY: IGNORE
            # =========================
            if strategy == "IGNORE":
                sql_block = f"""
                BEGIN
                    INSERT INTO {table} ({cols_sql})
                    VALUES ({binds_sql});
                EXCEPTION
                    WHEN DUP_VAL_ON_INDEX THEN
                        NULL;
                END;
                """

            # =========================
            # STRATEGY: UPDATE (MERGE)
            # =========================
            elif strategy == "UPDATE":

                if not pk_cols:
                    raise Exception(f"PK_COLUMN no definido para tabla {table}")

                using_binds = ", ".join(
                    [f":{i+1} AS {col}" for i, col in enumerate(final_columns)]
                )

                join_cond = " AND ".join(
                    [f"t.{c} = s.{c}" for c in pk_cols]
                )

                update_cols = [
                    c for c in final_columns
                    if c not in pk_cols
                ]

                update_set = ", ".join(
                    [f"t.{c} = s.{c}" for c in update_cols]
                ) if update_cols else ""

                insert_vals = ", ".join(
                    [f"s.{c}" for c in final_columns]
                )

                sql_block = f"""
                MERGE INTO {table} t
                USING (SELECT {using_binds} FROM DUAL) s
                ON ({join_cond})
                WHEN MATCHED THEN
                    UPDATE SET {update_set}
                WHEN NOT MATCHED THEN
                    INSERT ({cols_sql})
                    VALUES ({insert_vals})
                """
            
            # =========================
            # STRATEGY: FAIL / DEFAULT
            # =========================
            else:
                sql_block = f"""
                INSERT INTO {table} ({cols_sql})
                VALUES ({binds_sql})
                """

            # =========================
            # EJECUCIÓN MASIVA
            # =========================
            total = 0

            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]

                batch_values = []

                for row in batch:
                    values = list(row)

                    if extra_fields:
                        values.extend(extra_fields.values())

                    batch_values.append(values)

                try:
                    cursor.executemany(sql_block, batch_values)
                except Exception as e:
                    raise Exception(str(e))

                total += len(batch)

                print(
                    f"Procesados {total} registros en {table} "
                    f"bajo estrategia {strategy}"
                )

            target_conn.commit()
            return {
                "inserted": total,
                "status": "OK"
            }

        finally:
            target_conn.close()