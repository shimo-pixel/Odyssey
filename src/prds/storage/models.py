import json
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text, Float, Integer
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    phase: Mapped[str] = mapped_column(String(32), default="pending")
    current_period: Mapped[int] = mapped_column(Integer, default=0)
    total_periods: Mapped[int] = mapped_column(Integer, default=0)
    alive_agents: Mapped[int] = mapped_column(Integer, default=0)
    total_agents: Mapped[int] = mapped_column(Integer, default=0)
    progress_pct: Mapped[float] = mapped_column(Float, default=0.0)
    input_json: Mapped[str] = mapped_column(Text, default="{}")
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
