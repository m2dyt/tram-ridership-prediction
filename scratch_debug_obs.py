from tram.infrastructure.settings import Settings
from tram.infrastructure.database import make_engine, session_factory
from tram.infrastructure.repository import SqlRepository, parse_time, ObservationRow, filtered_points
from sqlalchemy import select

settings = Settings()
engine = make_engine(settings.database_url.get_secret_value())
sessions = session_factory(engine)
repo = SqlRepository(sessions)

revision = "competition-data-v1"
profile = "competition-boardings-route-day"
query = {
    "from": "2025-01-01T00:00:00+03:00",
    "to": "2025-01-10T00:00:00+03:00",
    "route_id": "hackathon-1"
}

with sessions() as session:
    stmt = select(ObservationRow).where(
        ObservationRow.dataset_id == revision, ObservationRow.profile_id == profile
    )
    print("Total rows without filters:", len(list(session.scalars(stmt))))
    
    stmt_filtered = filtered_points(stmt, ObservationRow, query)
    res = list(session.scalars(stmt_filtered))
    print("Filtered rows count:", len(res))
    if res:
        print("First row:", res[0].document)
    else:
        # Check why it's empty
        print("interval_start filter:", parse_time(query["from"]))
        sample_row = session.scalars(stmt.where(ObservationRow.route_id == "hackathon-1")).first()
        if sample_row:
            print("sample row interval_start:", repr(sample_row.interval_start))
            print("sample row interval_end:", repr(sample_row.interval_end))
            print("parse_time('from'):", repr(parse_time(query["from"])))
            print("sample_row.interval_start >= parse_time('from'):", sample_row.interval_start >= parse_time(query["from"]))
            print("sample_row.interval_end <= parse_time('to'):", sample_row.interval_end <= parse_time(query["to"]))
