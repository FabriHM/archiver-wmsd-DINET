import os

PROJECT_PATH = "ARCHIVER"  # tu carpeta existente

structure = {
    "config": ["settings.py", "logging_config.py"],
    "core": ["orchestrator.py", "state_machine.py", "exceptions.py"],
    "db": ["oracle_source.py", "oracle_target.py", "connection_manager.py"],
    "repositories": [
        "schema_repository.py",
        "process_repository.py",
        "control_repository.py",
        "metadata_repository.py"
    ],
    "services": [
        "extraction_service.py",
        "transformation_service.py",
        "load_service.py",
        "process_service.py"
    ],
    "sp": ["sp_executor.py"],
    "models": ["process.py", "schema.py", "control.py"],
    "utils": ["logger.py", "date_utils.py", "sql_builder.py"],
    "tests": ["test_extraction.py", "test_load.py"]
}

root_files = ["main.py", "requirements.txt", "README.md"]

def create_structure():
    base = PROJECT_PATH

    # crear carpetas y archivos internos
    for folder, files in structure.items():
        folder_path = os.path.join(base, folder)
        os.makedirs(folder_path, exist_ok=True)

        for file in files:
            file_path = os.path.join(folder_path, file)
            if not os.path.exists(file_path):
                open(file_path, "w", encoding="utf-8").close()

    # archivos raíz
    for file in root_files:
        file_path = os.path.join(base, file)
        if not os.path.exists(file_path):
            open(file_path, "w", encoding="utf-8").close()

    print(f"Estructura creada dentro de '{PROJECT_PATH}'")

if __name__ == "__main__":
    create_structure()