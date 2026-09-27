from tram.infrastructure.settings import Settings
from tram.infrastructure.database import make_engine, session_factory
from tram.infrastructure.repository import SqlRepository
from tram.infrastructure.runtime import SystemClock, SignedCursor
from tram.application.service import ReadService

settings = Settings()
engine = make_engine(settings.database_url.get_secret_value())
sessions = session_factory(engine)
reads = ReadService(SqlRepository(sessions), SystemClock(), SignedCursor("unused-cli-cursor-" * 3))

# Case 1: query with route_id
q1 = {
    'dataset_revision_id': 'competition-data-v1',
    'observation_profile_id': 'competition-boardings-route-day',
    'route_id': 'hackathon-1',
    'from': '2025-01-01T00:00:00+03:00',
    'to': '2025-01-10T00:00:00+03:00',
    'limit': 10
}
res1 = reads.observations(q1)
print("q1 items count:", len(res1['items']))

# Case 2: query without route_id
q2 = {
    'dataset_revision_id': 'competition-data-v1',
    'observation_profile_id': 'competition-boardings-route-day',
    'from': '2025-01-01T00:00:00+03:00',
    'to': '2025-01-10T00:00:00+03:00',
    'limit': 10
}
res2 = reads.observations(q2)
print("q2 items count:", len(res2['items']))
