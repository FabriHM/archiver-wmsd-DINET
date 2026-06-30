from config.settings import SOURCE_CONFIG_DB
from db.connection_manager import ConnectionManager

def test_source():
    conn_manager = ConnectionManager()

    conn_manager.create_pool(
        "source",
        SOURCE_CONFIG_DB
    )

    conn = conn_manager.get_connection("source")

    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM dual")

    result = cursor.fetchone()
    print("SOURCE OK:", result)

    cursor.close()
    conn_manager.release(conn)
    conn_manager.close_all()

if __name__ == "__main__":
    test_source()