import hashlib
import json

from sqlalchemy import func, insert, select

from tram.application.errors import ApplicationError
from tram.application.mapping import spatial_from_document
from tram.domain.time import parse_time
from tram.infrastructure.database import DatasetRow, NetworkRow, ObservationRow, SeriesRow
from tram.infrastructure.repository import point_columns


def canonical(document):
    return json.dumps(
        document, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode()


class SqlDatasetWriter:
    def __init__(self, sessions):
        self.sessions = sessions

    def publish(self, manifest, records, now):
        revision = manifest["capabilities"]["dataset_revision_id"]
        network = manifest["network"]
        digest = hashlib.sha256(canonical(manifest) + b"\n")
        with self.sessions.begin() as session:
            if session.bind.dialect.name == "postgresql":
                for scope in sorted(("dataset:" + revision, "network:" + network["id"])):
                    key = int.from_bytes(hashlib.sha256(scope.encode()).digest()[:8], signed=True)
                    session.execute(select(func.pg_advisory_xact_lock(key)))
            existing = session.get(DatasetRow, revision)
            known_network = session.get(NetworkRow, network["id"])
            if known_network and known_network.document != network:
                raise ApplicationError(
                    "VALIDATION_ERROR", "Network revision already exists with different content"
                )
            if not existing:
                if not known_network:
                    session.add(NetworkRow(id=network["id"], document=network))
                    session.flush()
                dataset = DatasetRow(
                    id=revision,
                    network_id=network["id"],
                    published_at=now,
                    manifest_hash="pending",
                    document={k: v for k, v in manifest.items() if k not in ("network", "series")},
                )
                session.add(dataset)
                session.flush()
                for item in manifest["series"]:
                    spatial = spatial_from_document(item["spatial"])
                    session.add(
                        SeriesRow(
                            dataset_id=revision,
                            profile_id=item["profile_id"],
                            series_key=spatial.canonical,
                            route_id=spatial.route_id,
                            document=item,
                        )
                    )
                session.flush()
            batch = []
            for record in records:
                digest.update(canonical(record) + b"\n")
                if existing:
                    continue
                batch.append(
                    {
                        "dataset_id": revision,
                        "profile_id": record["profile_id"],
                        "available_at": parse_time(record["available_at"]),
                        **point_columns(record["point"]),
                    }
                )
                if len(batch) == 500:
                    session.execute(insert(ObservationRow), batch)
                    batch.clear()
            if existing:
                if existing.manifest_hash != digest.hexdigest():
                    raise ApplicationError(
                        "VALIDATION_ERROR", "Dataset revision already exists with different content"
                    )
                return False
            if batch:
                session.execute(insert(ObservationRow), batch)
            dataset.manifest_hash = digest.hexdigest()
            return True
