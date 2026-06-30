import oracledb


class ConnectionManager:

    def __init__(self):
        self.pools = {}

    def create_pool(self, name, config):
        """
        Crea un pool Oracle y lo registra.
        """

        if name in self.pools:
            return

        pool = oracledb.create_pool(
            user=config.user,
            password=config.password,
            dsn=config.dsn,
            min=1,
            max=10,
            increment=1,
            timeout=300,
            wait_timeout=60
        )

        self.pools[name] = pool
        print(f"Pool creado: {name}")

    def get_connection(self, name):
        """
        Obtiene una conexión del pool.
        """

        if name not in self.pools:
            raise Exception(f"Pool no existe: {name}")

        return self.pools[name].acquire()

    def release(self, conn):
        """
        Devuelve conexión al pool.
        """
        if conn:
            conn.close()

    def close_all(self):
        """
        Cierra todos los pools.
        """
        for name, pool in self.pools.items():
            pool.close()
            print(f"Pool cerrado: {name}")