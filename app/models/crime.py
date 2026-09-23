from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class IucrCode(Base):
    __tablename__ = "iucr_codes"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    primary_type: Mapped[str] = mapped_column(String(100), nullable=False)
    secondary_desc: Mapped[str] = mapped_column(String(200), nullable=False)
    index_crime: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PoliceDistrict(Base):
    __tablename__ = "police_districts"

    code: Mapped[str] = mapped_column(String(10), primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class CommunityArea(Base):
    __tablename__ = "community_areas"

    code: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


class Crime(Base):
    __tablename__ = "crimes"
    __table_args__ = (
        Index("ix_crimes_occurred_at", "occurred_at"),
        Index("ix_crimes_primary_type", "primary_type"),
        Index("ix_crimes_primary_type_occurred_at", "primary_type", "occurred_at"),
        Index("ix_crimes_district_code", "district_code"),
        Index("ix_crimes_community_area_code", "community_area_code"),
        Index("ix_crimes_arrest", "arrest"),
        Index("ix_crimes_case_number", "case_number"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    # NOT unique: a single police case_number can span multiple crime records (e.g.
    # a multi-victim incident produces one row per victim, same case_number). This
    # was discovered ingesting the real dataset: 20 of 263,841 rows in the 2023 data
    # share a case_number with another row. `id` is the true unique row identifier.
    case_number: Mapped[str] = mapped_column(String(20), nullable=False)
    occurred_at: Mapped[DateTime] = mapped_column(DateTime, nullable=False)
    block: Mapped[str] = mapped_column(String(100), nullable=True)
    iucr_code: Mapped[str] = mapped_column(String(10), ForeignKey("iucr_codes.code"), nullable=True)
    primary_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=True)
    location_description: Mapped[str] = mapped_column(String(100), nullable=True)
    arrest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    domestic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    beat: Mapped[str] = mapped_column(String(10), nullable=True)
    district_code: Mapped[str] = mapped_column(
        String(10), ForeignKey("police_districts.code"), nullable=True
    )
    ward: Mapped[int] = mapped_column(Integer, nullable=True)
    community_area_code: Mapped[int] = mapped_column(
        Integer, ForeignKey("community_areas.code"), nullable=True
    )
    fbi_code: Mapped[str] = mapped_column(String(10), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=True)
    longitude: Mapped[float] = mapped_column(Float, nullable=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

    iucr: Mapped["IucrCode"] = relationship(viewonly=True)
    district: Mapped["PoliceDistrict"] = relationship(viewonly=True)
    community_area: Mapped["CommunityArea"] = relationship(viewonly=True)
