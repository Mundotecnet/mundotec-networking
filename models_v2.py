"""
Modelos v2 — jerarquía multi-sitio.
Conviven con las tablas legacy (models.py) durante la migración incremental.
"""
import uuid
from sqlalchemy import (
    Column, Integer, String, Text, Numeric, UniqueConstraint,
    ForeignKey, ForeignKeyConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from database import Base


def _uuid():
    return str(uuid.uuid4())


class Sitio(Base):
    """Sucursal / sede de un cliente."""
    __tablename__ = "sitio"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
                server_default="uuid_generate_v4()")
    # FK al cliente legacy (clients.id INTEGER) durante la transición
    cliente_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    nombre = Column(Text, nullable=False)
    direccion = Column(Text)
    latitud = Column(Numeric(9, 6))
    longitud = Column(Numeric(9, 6))
    zona_horaria = Column(Text, default="America/Costa_Rica")

    __table_args__ = (
        UniqueConstraint("cliente_id", "nombre", name="uq_sitio_cliente_nombre"),
    )

    edificios = relationship("Edificio", back_populates="sitio", cascade="all, delete-orphan", lazy="select")
    cliente = relationship("Client", foreign_keys=[cliente_id], lazy="select")


class Edificio(Base):
    """Edificio dentro de un sitio."""
    __tablename__ = "edificio"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
                server_default="uuid_generate_v4()")
    sitio_id = Column(UUID(as_uuid=True), ForeignKey("sitio.id", ondelete="CASCADE"), nullable=False)
    codigo = Column(Text, nullable=False)       # "A", "B"
    nombre = Column(Text, nullable=False)
    piso_default = Column(Integer)

    __table_args__ = (
        UniqueConstraint("sitio_id", "codigo", name="uq_edificio_sitio_codigo"),
    )

    sitio = relationship("Sitio", back_populates="edificios", lazy="select")
    cuartos = relationship("Cuarto", back_populates="edificio", cascade="all, delete-orphan", lazy="select")


class Cuarto(Base):
    """Cuarto de comunicaciones."""
    __tablename__ = "cuarto"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
                server_default="uuid_generate_v4()")
    edificio_id = Column(UUID(as_uuid=True), ForeignKey("edificio.id", ondelete="CASCADE"), nullable=False)
    # Enlace al cuarto legacy para migración incremental
    room_legacy_id = Column(Integer, ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True)
    piso = Column(Integer, nullable=False)
    codigo = Column(Text, nullable=False)       # "A", "B"
    nombre = Column(Text, nullable=False)
    descripcion = Column(Text)

    __table_args__ = (
        UniqueConstraint("edificio_id", "piso", "codigo", name="uq_cuarto_edificio_piso_codigo"),
    )

    edificio = relationship("Edificio", back_populates="cuartos", lazy="select")
    gabinetes = relationship("Gabinete", back_populates="cuarto", cascade="all, delete-orphan", lazy="select")


class Gabinete(Base):
    """Rack/gabinete dentro de un cuarto."""
    __tablename__ = "gabinete"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4,
                server_default="uuid_generate_v4()")
    cuarto_id = Column(UUID(as_uuid=True), ForeignKey("cuarto.id", ondelete="CASCADE"), nullable=False)
    codigo = Column(Text, nullable=False)       # "A", "B"
    nombre = Column(Text)
    ubicacion = Column(Text)                    # "frente pared norte"
    unidades_rack = Column(Integer)

    __table_args__ = (
        UniqueConstraint("cuarto_id", "codigo", name="uq_gabinete_cuarto_codigo"),
    )

    cuarto = relationship("Cuarto", back_populates="gabinetes", lazy="select")
