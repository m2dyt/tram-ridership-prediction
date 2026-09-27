from tram.infrastructure.settings import Settings
from tram.infrastructure.database import make_engine, session_factory
from sqlalchemy import text

settings = Settings()
print('Connected to DB URL:', settings.database_url.get_secret_value())
engine = make_engine(settings.database_url.get_secret_value())
with session_factory(engine)() as session:
    tables = session.execute(text("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name;
    """)).fetchall()
    print('Tables found:', [t[0] for t in tables])
    for t in tables:
        count = session.execute(text(f'SELECT count(*) FROM "{t[0]}"')).scalar()
        print(f'Table {t[0]}: {count} rows')
