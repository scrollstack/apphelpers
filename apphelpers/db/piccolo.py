from contextlib import asynccontextmanager
from functools import wraps
from typing import List, Optional, Set, Type, cast

from piccolo.engine import engine_finder
from piccolo.engine.postgres import PostgresEngine
from piccolo.table import Table, create_db_tables_sync, drop_db_tables_sync


@asynccontextmanager
async def connection_pool_lifespan(engine: Optional[PostgresEngine] = None, **kwargs):
    if engine := engine or cast(PostgresEngine, engine_finder()):
        print("db: starting connection pool")
        await engine.start_connection_pool(**kwargs)
        yield
        print("db: closing connection pool")
        await engine.close_connection_pool()


@asynccontextmanager
async def dbtransaction_ctx(engine: Optional[PostgresEngine] = None, allow_nested=True):
    if engine := engine or cast(PostgresEngine, engine_finder()):
        async with engine.transaction(allow_nested=allow_nested):
            yield


def dbtransaction(engine: Optional[PostgresEngine] = None, allow_nested=True):
    def wrapper(f):
        @wraps(f)
        async def f_wrapped(*args, **kw):
            async with dbtransaction_ctx(engine, allow_nested=allow_nested):
                return await f(*args, **kw)

        return f_wrapped

    return wrapper


class BaseTable(Table):
    @classmethod
    def all_column_names(cls) -> Set[str]:
        return {col._meta.name for col in cls._meta.columns}


def get_sub_tables(basetable: Type[Table]) -> List[Type[Table]]:
    tables = []
    for subtable in basetable.__subclasses__():
        tables.append(subtable)
        tables.extend(get_sub_tables(subtable))
    return tables


def setup_db(tables: List[Type[Table]]):
    create_db_tables_sync(*tables, if_not_exists=True)


def setup_db_from_basetable(basetable: Type[Table]):
    tables = get_sub_tables(basetable)
    setup_db(tables)


def destroy_db(tables: List[Type[Table]]):
    drop_db_tables_sync(*tables)


def destroy_db_from_basetable(basetable: Type[Table]):
    tables = get_sub_tables(basetable)
    destroy_db(tables)
