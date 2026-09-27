from tram.infrastructure.settings import Settings
from tram.infrastructure.database import make_engine, session_factory
from sqlalchemy import text

settings = Settings()
engine = make_engine(settings.database_url.get_secret_value())

with session_factory(engine)() as session:
    cols = session.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='dataset_revisions'")).fetchall()
    print("dataset_revisions columns:", cols)

    rows = session.execute(text("SELECT * FROM dataset_revisions")).fetchall()
    print("dataset_revisions rows:", rows)

    net_cols = session.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='network_revisions'")).fetchall()
    print("network_revisions columns:", net_cols)

    net_rows = session.execute(text("SELECT * FROM network_revisions")).fetchall()
    print("network_revisions rows:", net_rows)
