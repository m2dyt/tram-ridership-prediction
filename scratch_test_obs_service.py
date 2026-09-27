from tram.infrastructure.settings import Settings
from tram.infrastructure.database import make_engine, session_factory
from tram.infrastructure.repository import SqlRepository
from tram.infrastructure.runtime import SystemClock, SignedCursor
from tram.application.service import ReadService

settings = Settings()
engine = make_engine(settings.database_url.get_secret_value())
sessions = session_factory(engine)
reads = ReadService(SqlRepository(sessions), SystemClock(), SignedCursor("unused-cli-cursor-" * 3))

q = {
    'dataset_revision_id': 'competition-data-v1',
    'observation_profile_id': 'competition-boardings-route-day',
    'route_id': 'hackathon-1',
    'from': '2025-01-01T00:00:00+03:00',
    'to': '2025-01-10T00:00:00+03:00',
    'limit': 10
}

res = reads.observations(q)
print("reads.observations returned:")
print("Items count:", len(res.get("items", [])))
if res.get("items"):
    print("First item:", res["items"][0])
else:
    print("Full result:", res)
