import oracledb


class SPExecutor:

    def __init__(self, connection):
        self.connection = connection

    def execute_cursor_sp(
        self,
        package: str,
        procedure: str,
        input_params: dict
    ):

        cursor = self.connection.cursor()
        out_cursor_real = None

        try:
            print(f"[SP] {package}.{procedure} → params: {list(input_params.keys())}")

            # ── variables de salida ──────────────────────────────────────
            out_cursor   = cursor.var(oracledb.CURSOR)
            out_err_code = cursor.var(oracledb.NUMBER)
            out_err_msg  = cursor.var(str)

            # ── construir binds de entrada con nombres seguros ───────────
            bind_dict = {}
            call_parts = []

            for idx, (key, value) in enumerate(input_params.items()):
                bind_name = f"in_{idx}"          # :in_0, :in_1 …  (nunca colisiona)
                bind_dict[bind_name] = value
                call_parts.append(f":{bind_name}")

            # ── bind de salida ───────────────────────────────────────────
            bind_dict["out_cur"]  = out_cursor
            bind_dict["out_code"] = out_err_code
            bind_dict["out_msg"]  = out_err_msg

            call_parts.extend([":out_cur", ":out_code", ":out_msg"])

            # ── bloque PL/SQL ────────────────────────────────────────────
            plsql = (
                f"BEGIN\n"
                f"    {package}.{procedure}(\n"
                f"        {', '.join(call_parts)}\n"
                f"    );\n"
                f"END;"
            )

            print(f"[SP] PL/SQL:\n{plsql}")
            print(f"[SP] bind keys: {list(bind_dict.keys())}")

            cursor.execute(plsql, bind_dict)   # ← dict named-bind: sin ORA-01036/01008

            # ── leer salidas ─────────────────────────────────────────────
            error_code = out_err_code.getvalue()
            error_msg  = out_err_msg.getvalue()

            print(f"[SP] error_code={error_code} | error_msg={error_msg}")

            if error_code is not None and error_code != 0:
                raise Exception(f"SP Error {int(error_code)}: {error_msg}")

            # ── leer cursor ──────────────────────────────────────────────
            out_cursor_real = out_cursor.getvalue()

            if out_cursor_real is None:
                print("[WARN] SP retornó cursor None")
                return [], []

            if out_cursor_real.description is None:
                print("[WARN] Cursor sin columnas (sin filas o SP vacío)")
                return [], []

            columns = [c[0] for c in out_cursor_real.description]

            out_cursor_real.arraysize = 1000
            rows = out_cursor_real.fetchall() or []

            print(f"[SP] filas obtenidas: {len(rows)}")
            return columns, rows

        finally:
            if out_cursor_real is not None:
                try:
                    out_cursor_real.close()
                except Exception:
                    pass
            cursor.close()