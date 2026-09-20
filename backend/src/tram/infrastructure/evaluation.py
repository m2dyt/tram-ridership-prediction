from sqlalchemy import insert, select

from tram.domain.time import parse_time
from tram.infrastructure.database import EvaluationPointRow, EvaluationRow, ObservationRow
from tram.infrastructure.repository import point_columns


class SqlEvaluationStore:
    def __init__(self, sessions, contract):
        self.sessions, self.contract = sessions, contract

    def actuals(self, dataset, profile, spatial, window, available):
        with self.sessions() as session:
            rows = session.scalars(
                select(ObservationRow).where(
                    ObservationRow.dataset_id == dataset,
                    ObservationRow.profile_id == profile,
                    ObservationRow.series_key == spatial.canonical,
                    ObservationRow.interval_start >= window.start,
                    ObservationRow.interval_end <= window.end,
                    ObservationRow.available_at <= available,
                )
            )
            return {row.interval_start: row.document for row in rows}

    def save(self, report, points):
        self.contract.validate("EvaluationReport", report)
        summary = report["summary"]
        with self.sessions.begin() as session:
            session.add(
                EvaluationRow(
                    id=summary["id"],
                    dataset_id=summary["dataset_revision_id"],
                    profile_id=summary["profile"]["id"],
                    horizon=summary["profile"]["horizon"],
                    model_id=summary["model"]["id"],
                    status=summary["status"],
                    created_at=parse_time(summary["created_at"]),
                    document=report,
                )
            )
            session.flush()
            batch = []
            for point in points:
                self.contract.validate("EvaluationPoint", point)
                batch.append(
                    {
                        "evaluation_id": summary["id"],
                        "fold_id": point["fold_id"],
                        **point_columns(point),
                    }
                )
                if len(batch) == 500:
                    session.execute(insert(EvaluationPointRow), batch)
                    batch.clear()
            if batch:
                session.execute(insert(EvaluationPointRow), batch)
