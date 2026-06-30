import oracledb
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from config.settings import SOURCE_CONFIG_DB, SOURCE_SP_DB, TARGET_DB
from db.connection_manager import ConnectionManager
from repositories.config_repository import ConfigRepository
from repositories.process_repository import ProcessRepository
from repositories.process_step_repository import ProcessStepRepository
from repositories.process_definition_repository import ProcessDefinitionRepository
from repositories.control_repository import ControlRepository
from services.extraction_service import ExtractionService
from services.load_service import LoadService

MAX_RETRIES = 3

oracledb.init_oracle_client(
    lib_dir=r"C:\Program Files\Oracle\instantclient_23_0"
)

# ══════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════

def _execute_root_step(
    step,
    cuenta,
    process_run_id,
    dias,
    control_repo,
    step_repo,
    extraction_service,
    load_service,
    target_conn,
    is_last_step = False
):
    print(f"\n[ROOT STEP] order={step['order']} proc={step['procedure']}")

    existing_items = control_repo.get_retryable_items(process_run_id)
    is_resume = False
    entity_to_item = {}
    
    if existing_items:
        print("[ROOT] Proceso reanudado: se detectaron registros de control previos")
        entity_to_item = existing_items
        is_resume = True
    
    if is_resume:
        sample_entities = list(entity_to_item.keys())
        if sample_entities:
            if control_repo.is_step_success(process_run_id, sample_entities[0], step["order"]):
                print(f"[ROOT] ¡SALTO DE SEGURIDAD! El paso {step['order']} ({step['procedure']}) ya fue procesado con éxito anteriormente.")
                return sample_entities, entity_to_item

    columns, rows = extraction_service.extract_by_account(
        cuenta,
        step["package"],
        step["procedure"],
        {"dias": dias}
    )
    print(f"[ROOT] filas obtenidas: {len(rows)} | columnas: {columns}")
    
    entity_ids = extraction_service.extract_ids(rows, "NRO_CAMION", columns)
    control_repo.update_expected_rows(process_run_id, len(entity_ids))

    if not is_resume:
        print("[ROOT] Antes create_process_items")
        entity_to_item = control_repo.create_process_items(
            process_run_id, cuenta, entity_ids
        )
        print("[ROOT] Después create_process_items")
        if not entity_to_item:
            raise Exception("No se crearon items en tabla de control")

    hist_table = step["tabla_destino"]
    inserted = load_service.load_to_hist(
        table=hist_table,
        columns=columns,
        rows=rows,
        conflict_strategy=step["conflict_strategy"],
        pk_column=step.get("pk_column"),  # Pasa la llave limpia mapeada
        extra_fields={
            "COD_CUENTA": cuenta,
            "PROCESS_ID": process_run_id
        }
    )
    print(f"[ROOT] {hist_table}: {inserted} registros insertados")
    print("[ROOT] iniciando preparación masiva de steps")

    start_batch = []
    finish_batch = []

    for idx, entity_id in enumerate(entity_ids, start=1):
        item_id = entity_to_item.get(entity_id)

        if is_resume:
            if control_repo.is_step_success(process_run_id, entity_id, step["order"]):
                continue

        start_batch.append({
            "process_id": process_run_id,
            "item_id":    item_id,
            "entity_id":  entity_id,
            "step_order": step["order"],
            "step_name":  step["procedure"]
        })

        finish_batch.append({
            "status":         "OK",
            "rows_processed": 1,
            "error_msg":      None,
            "status_chk":     "OK",
            "process_id":      process_run_id,
            "entity_id":      entity_id,
            "step_order":     step["order"]
        })

    if start_batch:
        print(f"[ROOT] Registrando masivamente el inicio de {len(start_batch)} steps...")
        step_repo.start_step(None, None, start_batch, None, None)
        
        print(f"[ROOT] Registrando masivamente el fin de {len(finish_batch)} steps...")
        step_repo.finish_step(None, finish_batch, None, None, 0, None)

    if is_last_step:
        for entity_id in entity_ids:
            control_repo.finalize_process_item(process_run_id, entity_id)

    print("[ROOT] fin registro masivo de steps")
    target_conn.commit()
    
    return entity_ids, entity_to_item


def _execute_child_step(
    step,
    cuenta,
    process_run_id,
    cm,
    extraction_service,
    load_service,
    is_last_step=False
):
    print(f"\n[CHILD STEP] order={step['order']} proc={step['procedure']}")

    init_conn = cm.get_connection("target")
    try:
        temp_control_repo = ControlRepository(init_conn)
        pending_ids = temp_control_repo.get_retryable_step_items(
            process_run_id,
            step["order"]
        )
    finally:
        cm.release(init_conn)

    if not pending_ids:
        print(f"[CHILD] No hay entidades pendientes para step {step['order']}")
        return

    MAX_WORKERS = 8
    print(f"[CHILD] Procesando {len(pending_ids)} entidades con {MAX_WORKERS} hilos")

    def process_worker(entity_id, item_id):

        thread_conn = cm.get_connection("target")
        t_control_repo = ControlRepository(thread_conn)
        t_step_repo = ProcessStepRepository(thread_conn)

        success = False

        try:
            if t_control_repo.is_item_rejected(process_run_id, entity_id):
                print(f"[CHILD] entity={entity_id} RECHAZADO (skip)")
                return

            if t_control_repo.is_step_success(process_run_id, entity_id, step["order"]):
                print(f"[CHILD] entity={entity_id} ya procesado")
                return

            for attempt in range(1, MAX_RETRIES + 1):

                try:
                    print(f"[CHILD] entity={entity_id} intento {attempt}")

                    t_step_repo.start_step(
                        process_run_id,
                        item_id,
                        entity_id,
                        step["order"],
                        step["procedure"]
                    )
                    thread_conn.commit()

                    # =========================
                    # EXTRACCIÓN
                    # =========================
                    input_params = {
                        step["param_value"].lower(): entity_id
                    }

                    cols, partial_rows = extraction_service.extract_by_account(
                        cuenta,
                        step["package"],
                        step["procedure"],
                        input_params
                    )

                    # =========================
                    # CARGA
                    # =========================
                    result = load_service.load_to_hist(
                        table=step["tabla_destino"],
                        columns=cols,
                        rows=partial_rows,
                        conflict_strategy=step["conflict_strategy"],
                        pk_column=step.get("pk_column"),
                        extra_fields={
                            "COD_CUENTA": cuenta,
                            "PROCESS_ID": process_run_id
                        }
                    )

                    inserted = result["inserted"]

                    # =========================
                    # OK
                    # =========================
                    t_step_repo.finish_step(
                        process_run_id,
                        entity_id,
                        step["order"],
                        "OK",
                        rows_processed=inserted
                    )

                    t_control_repo.write_log(
                        process_run_id,
                        cuenta,
                        "INFO",
                        f"OK entity={entity_id} rows={inserted}",
                        item_id
                    )

                    thread_conn.commit()
                    success = True
                    break

                except Exception as exc:

                    error_msg = str(exc)
                    strategy = step["conflict_strategy"].upper()

                    # =========================
                    # IGNORE
                    # =========================
                    if "ORA-00001" in error_msg and strategy == "IGNORE":
                        print(f"[IGNORE] entity={entity_id}")

                        t_step_repo.finish_step(
                            process_run_id,
                            entity_id,
                            step["order"],
                            "OK",
                            rows_processed=0
                        )

                        thread_conn.commit()
                        success = True
                        break

                    # =========================
                    # UPDATE (fallback OK)
                    # =========================
                    elif "ORA-00001" in error_msg and strategy == "UPDATE":
                        print(f"[UPDATE] entity={entity_id} tratado como OK")

                        t_step_repo.finish_step(
                            process_run_id,
                            entity_id,
                            step["order"],
                            "OK",
                            rows_processed=0
                        )

                        thread_conn.commit()
                        success = True
                        break

                    # =========================
                    # FAIL (solo esta entidad muere)
                    # =========================
                    elif "ORA-00001" in error_msg and strategy == "FAIL":
                        print(f"[FAIL] entity={entity_id} detenido")

                        t_step_repo.finish_step(
                            process_run_id,
                            entity_id,
                            step["order"],
                            "ERROR",
                            rows_processed=0,
                            error_msg=error_msg
                        )

                        t_control_repo.update_process_item(
                            process_run_id,
                            entity_id,
                            "RECHAZADO",
                            error_msg
                        )

                        thread_conn.commit()
                        break

                    # =========================
                    # OTROS ERRORES
                    # =========================
                    print(f"[ERROR] entity={entity_id} intento {attempt}: {error_msg}")

                    t_step_repo.finish_step(
                        process_run_id,
                        entity_id,
                        step["order"],
                        "ERROR",
                        rows_processed=0,
                        error_msg=error_msg
                    )

                    thread_conn.commit()

                    if attempt >= MAX_RETRIES:
                        t_control_repo.update_process_item(
                            process_run_id,
                            entity_id,
                            "RECHAZADO",
                            error_msg
                        )
                        break

            if success and is_last_step:
                t_control_repo.finalize_process_item(process_run_id, entity_id)
                thread_conn.commit()

        finally:
            cm.release(thread_conn)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [
            executor.submit(process_worker, entity_id, item_id)
            for entity_id, item_id in pending_ids.items()
        ]

        for future in as_completed(futures):
            try:
                future.result()
            except Exception as e:
                print(f"[THREAD ERROR] {e}")
# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    print("Thin mode:", oracledb.is_thin_mode())

    cm = ConnectionManager()
    cm.create_pool("config", SOURCE_CONFIG_DB)
    cm.create_pool("source", SOURCE_SP_DB)
    cm.create_pool("target", TARGET_DB)
    print("Pools creados")

    config_conn = cm.get_connection("config")
    target_conn = cm.get_connection("target")

    try:
        config_repo     = ConfigRepository(config_conn)
        process_repo    = ProcessRepository(config_conn)
        definition_repo = ProcessDefinitionRepository(config_conn)
        control_repo    = ControlRepository(target_conn)
        step_repo       = ProcessStepRepository(target_conn)
        extraction_svc  = ExtractionService(cm)
        load_svc        = LoadService(cm)

        accounts = config_repo.get_active_accounts()
        print("Cuentas:", accounts)

        for cuenta in accounts:
            print(f"\n{'='*60}")
            print(f"CUENTA: {cuenta}")

            processes = process_repo.get_active_processes(cuenta)
            print("Procesos:", processes)

            for process in processes:
                process_id   = process["id"]
                process_name = process["name"]

                process_run_id = control_repo.get_open_process(
                    process_name, cuenta
                )
                if process_run_id:
                    print(f"[REANUDAR] RUN_ID={process_run_id}")
                else:
                    last_attempt   = control_repo.get_last_attempt(process_name, cuenta)
                    process_run_id = control_repo.create_process_control(
                        process_name, cuenta, None, None, last_attempt + 1
                    )

                print(f"\nProceso: {process_name} | RUN_ID: {process_run_id}")

                try:
                    dias = process_repo.get_retention_days(cuenta, process_id)
                    print(f"Días retención: {dias}")

                    steps = definition_repo.get_process_steps(process_id)
                    print("\n=== STEPS CARGADOS ===")
                    for s in steps:
                        # Asignamos temporalmente el valor del parámetro (ej: NRO_CAMION) como pk_column.
                        # Si agregas la columna física a la tabla de control, puedes cambiar esto por s['KEY_COLUMN']
                        print(
                            f"order={s['order']} | "
                            f"proc={s['procedure']} | "
                            f"table={s['tabla_destino']} | "
                            f"pk={s['pk_column']}"
                        )
                    
                    if not steps:
                        raise Exception(f"No hay steps definidos para proceso {process_id}")

                    root_step    = steps[0]
                    tabla_origen = root_step["table"]
                    fecha_filtro = datetime.now() - timedelta(days=dias)

                    control_repo.update_process_metadata(
                        process_run_id, tabla_origen, fecha_filtro
                    )

                    for step in steps:
                        print(f"\n{'='*60}")
                        print(f"STEP order={step['order']} | {step['procedure']} | type={step['param_type']}")
                        is_last_step = step["order"] == steps[-1]["order"]
                        
                        if step["param_type"] == "RETENTION_DAYS":
                            _execute_root_step(
                                step, cuenta, process_run_id, dias,
                                control_repo, step_repo,
                                extraction_svc, load_svc,
                                target_conn, is_last_step
                            )

                        elif step["param_type"] == "FROM_PREVIOUS":
                            _execute_child_step(
                                step, cuenta, process_run_id,
                                cm, extraction_svc, load_svc, is_last_step
                            )

                        else:
                            print(f"[WARN] param_type desconocido: {step['param_type']}")

                    control_repo.update_inserted_rows(process_run_id)

                    final_status = (
                        "COMPLETADO_CON_ERRORES"
                        if control_repo.has_errors(process_run_id)
                        else "COMPLETADO"
                    )
                    control_repo.finish_process_control(process_run_id, final_status)
                    print(f"\n[OK] Proceso {process_name} → {final_status}")

                    process_repo.update_next_execution(cuenta, process_id)

                except Exception as exc:
                    control_repo.finish_process_control(process_run_id, "ERROR")
                    control_repo.write_log(
                        process_run_id, cuenta, "ERROR",
                        f"ERROR FATAL proceso {process_name}: {exc}",
                        None
                    )
                    print(f"[ERROR FATAL] {exc}")

    finally:
        config_conn.close()
        target_conn.close()
        cm.close_all()
        print("\nPools cerrados")

if __name__ == "__main__":
    main()