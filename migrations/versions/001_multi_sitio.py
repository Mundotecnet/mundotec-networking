"""001 multi-sitio: sitio, edificio, cuarto, gabinete

Revision ID: 001
Revises:
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Extensiones requeridas por el nuevo schema
    op.execute("CREATE EXTENSION IF NOT EXISTS \"pgcrypto\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"citext\"")

    # ── sitio (sucursal/sede bajo un cliente) ──────────────────────────────
    op.create_table(
        'sitio',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('cliente_id', sa.Integer(),
                  sa.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('nombre', sa.Text(), nullable=False),
        sa.Column('direccion', sa.Text()),
        sa.Column('latitud', sa.Numeric(9, 6)),
        sa.Column('longitud', sa.Numeric(9, 6)),
        sa.Column('zona_horaria', sa.Text(), server_default='America/Costa_Rica'),
        sa.UniqueConstraint('cliente_id', 'nombre', name='uq_sitio_cliente_nombre'),
    )
    op.create_index('idx_sitio_cliente', 'sitio', ['cliente_id'])

    # ── edificio ───────────────────────────────────────────────────────────
    op.create_table(
        'edificio',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('sitio_id', UUID(as_uuid=True),
                  sa.ForeignKey('sitio.id', ondelete='CASCADE'), nullable=False),
        sa.Column('codigo', sa.Text(), nullable=False),
        sa.Column('nombre', sa.Text(), nullable=False),
        sa.Column('piso_default', sa.Integer()),
        sa.UniqueConstraint('sitio_id', 'codigo', name='uq_edificio_sitio_codigo'),
    )

    # ── cuarto (cuarto de comunicaciones) ──────────────────────────────────
    op.create_table(
        'cuarto',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('edificio_id', UUID(as_uuid=True),
                  sa.ForeignKey('edificio.id', ondelete='CASCADE'), nullable=False),
        # Enlace opcional al cuarto legacy (rooms) para migración incremental
        sa.Column('room_legacy_id', sa.Integer(),
                  sa.ForeignKey('rooms.id', ondelete='SET NULL'), nullable=True),
        sa.Column('piso', sa.Integer(), nullable=False),
        sa.Column('codigo', sa.Text(), nullable=False),
        sa.Column('nombre', sa.Text(), nullable=False),
        sa.Column('descripcion', sa.Text()),
        sa.UniqueConstraint('edificio_id', 'piso', 'codigo', name='uq_cuarto_edificio_piso_codigo'),
    )
    op.create_index('idx_cuarto_edificio', 'cuarto', ['edificio_id'])

    # ── gabinete ───────────────────────────────────────────────────────────
    op.create_table(
        'gabinete',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('cuarto_id', UUID(as_uuid=True),
                  sa.ForeignKey('cuarto.id', ondelete='CASCADE'), nullable=False),
        sa.Column('codigo', sa.Text(), nullable=False),
        sa.Column('nombre', sa.Text()),
        sa.Column('ubicacion', sa.Text()),
        sa.Column('unidades_rack', sa.Integer()),
        sa.UniqueConstraint('cuarto_id', 'codigo', name='uq_gabinete_cuarto_codigo'),
    )
    op.create_index('idx_gabinete_cuarto', 'gabinete', ['cuarto_id'])


def downgrade() -> None:
    op.drop_table('gabinete')
    op.drop_table('cuarto')
    op.drop_table('edificio')
    op.drop_table('sitio')
