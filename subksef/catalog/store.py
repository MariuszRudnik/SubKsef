import sqlite3
import sys
from pathlib import Path

from subksef.invoice.epp import CatalogItem


def database_path() -> Path:
    if getattr(sys, "frozen", False):
        root = Path(sys.executable).resolve().parent
    else:
        root = Path(__file__).resolve().parents[2]
    return root / "data" / "towary.sqlite"


def import_goods(
    items: tuple[CatalogItem, ...] | list[CatalogItem],
    path: Path | None = None,
) -> tuple[int, int]:
    with _connect(path) as connection:
        before = _count(connection)
        connection.executemany(
            """
            INSERT OR IGNORE INTO towary (kod, nazwa, cena_netto, cena_brutto)
            VALUES (?, ?, ?, ?)
            """,
            [
                (item.code, item.name, item.net_price, item.gross_price)
                for item in items
            ],
        )
        added = _count(connection) - before
    return added, len(items) - added


def save_replacement(
    invoice_number: str,
    document: int,
    line_index: int,
    source_name: str,
    source_code: str,
    item: CatalogItem,
    path: Path | None = None,
    manual: bool = True,
) -> None:
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO podmiany (
                numer_faktury, dokument, pozycja, nazwa_faktury, kod_faktury, kod, nazwa, stan
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice_number,
                document,
                line_index,
                source_name,
                source_code,
                item.code,
                item.name,
                "reczna" if manual else "auto",
            ),
        )


def skip_replacement(
    invoice_number: str,
    document: int,
    line_index: int,
    source_name: str,
    source_code: str,
    path: Path | None = None,
) -> None:
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO podmiany (
                numer_faktury, dokument, pozycja, nazwa_faktury, kod_faktury, kod, nazwa, stan
            )
            VALUES (?, ?, ?, ?, ?, '', '', 'pominieta')
            """,
            (invoice_number, document, line_index, source_name, source_code),
        )


def delete_replacement(
    invoice_number: str,
    document: int,
    line_index: int,
    path: Path | None = None,
) -> None:
    with _connect(path) as connection:
        connection.execute(
            """
            DELETE FROM podmiany
            WHERE numer_faktury = ? AND dokument = ? AND pozycja = ?
            """,
            (invoice_number, document, line_index),
        )


def list_replacements(
    invoice_number: str,
    document: int = 0,
    path: Path | None = None,
) -> dict[int, CatalogItem]:
    return {
        line_index: item
        for line_index, (state, item) in list_states(invoice_number, document, path).items()
        if state != "pominieta"
    }


def list_states(
    invoice_number: str,
    document: int = 0,
    path: Path | None = None,
) -> dict[int, tuple[str, CatalogItem]]:
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT pozycja, stan, kod, nazwa
            FROM podmiany
            WHERE numer_faktury = ? AND dokument = ?
            """,
            (invoice_number, document),
        ).fetchall()
    return {
        int(line_index): (
            state,
            CatalogItem(code=code, name=name, net_price="", gross_price=""),
        )
        for line_index, state, code, name in rows
    }


def delete_good(code: str, path: Path | None = None) -> None:
    with _connect(path) as connection:
        connection.execute("DELETE FROM towary WHERE kod = ?", (code,))


def list_goods(query: str = "", path: Path | None = None) -> tuple[CatalogItem, ...]:
    needle = query.strip()
    statement = """
        SELECT kod, nazwa, cena_netto, cena_brutto
        FROM towary
    """
    parameters: tuple[str, ...] = ()
    if needle:
        statement += " WHERE matches(kod, nazwa, ?)"
        parameters = (needle,)
    statement += " ORDER BY kod"
    with _connect(path) as connection:
        rows = connection.execute(statement, parameters).fetchall()
    return tuple(
        CatalogItem(code=code, name=name, net_price=net, gross_price=gross)
        for code, name, net, gross in rows
    )


def _connect(path: Path | None) -> sqlite3.Connection:
    database = path or database_path()
    database.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    connection.create_function("matches", 3, _matches)
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS towary (
            kod TEXT PRIMARY KEY,
            nazwa TEXT NOT NULL,
            cena_netto TEXT NOT NULL,
            cena_brutto TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS podmiany (
            numer_faktury TEXT NOT NULL,
            dokument INTEGER NOT NULL,
            pozycja INTEGER NOT NULL,
            nazwa_faktury TEXT NOT NULL,
            kod_faktury TEXT NOT NULL,
            kod TEXT NOT NULL,
            nazwa TEXT NOT NULL,
            stan TEXT NOT NULL DEFAULT 'reczna',
            PRIMARY KEY (numer_faktury, dokument, pozycja)
        )
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(podmiany)")}
    if "stan" not in columns:
        connection.execute("ALTER TABLE podmiany ADD COLUMN stan TEXT NOT NULL DEFAULT 'reczna'")
    return connection


def _matches(code: str, name: str, needle: str) -> int:
    folded = needle.casefold()
    return int(folded in code.casefold() or folded in name.casefold())


def _count(connection: sqlite3.Connection) -> int:
    row = connection.execute("SELECT COUNT(*) FROM towary").fetchone()
    return int(row[0]) if row else 0
