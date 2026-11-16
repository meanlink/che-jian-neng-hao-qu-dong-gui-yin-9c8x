from sqlalchemy import String, JSON, Double, Integer, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
class SourceBatch(Base):
    __tablename__ = 'source_batches'
    id: Mapped[int] = mapped_column(primary_key=True)
    channel: Mapped[str] = mapped_column(String(20), index=True)
    stream: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(160), default='')
    records: Mapped[list] = mapped_column(JSON)
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default='active', index=True)
    created_by: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[float] = mapped_column(Double)
    __table_args__ = (UniqueConstraint('channel', 'stream', 'version'),)
class MergeSample(Base):
    __tablename__ = 'merge_samples'
    id: Mapped[int] = mapped_column(primary_key=True)
    line: Mapped[str] = mapped_column(String(40), index=True)
    day: Mapped[str] = mapped_column(String(10))
    values: Mapped[dict] = mapped_column(JSON, default=dict)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    content_checksum: Mapped[str] = mapped_column(String(64), default='')
    published_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    published_dataset_id: Mapped[int | None] = mapped_column(ForeignKey('datasets.id'), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default='pending_fill')
    updated_at: Mapped[float] = mapped_column(Double)
    __table_args__ = (UniqueConstraint('line', 'day'),)
class Arbitration(Base):
    __tablename__ = 'arbitrations'
    id: Mapped[int] = mapped_column(primary_key=True)
    line: Mapped[str] = mapped_column(String(40))
    day: Mapped[str] = mapped_column(String(10))
    field: Mapped[str] = mapped_column(String(20))
    chosen_value: Mapped[float] = mapped_column(Double)
    reason: Mapped[str] = mapped_column(String(300))
    basis: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default='valid')
    decided_by: Mapped[str] = mapped_column(String(150))
    decided_at: Mapped[float] = mapped_column(Double)
    confirmed_at: Mapped[float] = mapped_column(Double)
    __table_args__ = (UniqueConstraint('line', 'day', 'field'),)
class MergeTask(Base):
    __tablename__ = 'merge_tasks'
    id: Mapped[int] = mapped_column(primary_key=True)
    line: Mapped[str] = mapped_column(String(40))
    day: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[float] = mapped_column(Double)
    __table_args__ = (Index('ix_merge_tasks_key', 'line', 'day'),)
class PublishRecord(Base):
    __tablename__ = 'publish_records'
    id: Mapped[int] = mapped_column(primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey('datasets.id'))
    line: Mapped[str] = mapped_column(String(40), index=True)
    group_checksum: Mapped[str] = mapped_column(String(64))
    basis: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[str] = mapped_column(String(150))
    created_at: Mapped[float] = mapped_column(Double)
