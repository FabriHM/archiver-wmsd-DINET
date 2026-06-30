from dataclasses import dataclass


@dataclass
class OracleConfig:
    user: str
    password: str
    dsn: str


# ==========================
# ORIGEN - CONFIG (W4WCOM)
# ==========================
SOURCE_CONFIG_DB = OracleConfig(
    user="W4WCOM",
    password="D1ne7com",
    dsn="""
    (DESCRIPTION =
        (ADDRESS = (PROTOCOL = TCP)(HOST = 172.16.163.16)(PORT = 1521))
        (CONNECT_DATA =
            (SERVER = DEDICATED)
            (SERVICE_NAME = WMSD_CORE)
        )
    )

    """
)


# ==========================
# ORIGEN - SP (W4WSYS)
# ==========================
SOURCE_SP_DB = OracleConfig(
    user="W4WSYS",
    password="D1ne7sys",
    dsn="""
    (DESCRIPTION =
        (ADDRESS = (PROTOCOL = TCP)(HOST = 172.16.163.16)(PORT = 1521))
        (CONNECT_DATA =
            (SERVER = DEDICATED)
            (SERVICE_NAME = WMSD_CORE)
        )
    )
    """
)


# ==========================
# DESTINO (W4WSYS)
# ==========================
TARGET_DB = OracleConfig(
    user="W4WSYS_ARCH",
    password="D1ne7sys",
    dsn="""
    (DESCRIPTION =
        (ADDRESS = (PROTOCOL = TCP)(HOST = 172.16.163.16)(PORT = 1521))
        (CONNECT_DATA =
            (SERVER = DEDICATED)
            (SERVICE_NAME = WMSD_CORE)
        )
    )
    """
)