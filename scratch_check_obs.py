from tram.infrastructure.settings import Settings
from tram.infrastructure.database import make_engine, session_factory
from sqlalchemy import text

settings = Settings()
engine = make_engine(settings.database_url.get_secret_value())
with session_factory(engine)() as session:
    res = session.execute(text("""
        SELECT count(*), min(interval_start), max(interval_end), route_id 
        FROM observations 
        WHERE dataset_id = 'competition-data-v1'
        GROUP BY route_id
    """)).fetchall()
    print("Competition observations grouped by route:")
    for r in res:
        print(r)
    
    sample = session.execute(text("""
        SELECT interval_start, interval_end, document 
        FROM observations 
        WHERE dataset_id = 'competition-data-v1' AND route_id = 'hackathon-1'
        LIMIT 3
    """)).fetchall()
    print("Sample hackathon-1 observations:")
    for s in sample:
        print(s[0], s[1], s[2])
