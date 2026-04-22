"""002 cableado: equipo, patch_panel, puerto_terminal, cable, jumper, empalme_fibra, endpoint, traza

Revision ID: 002
Revises: 001
Create Date: 2026-04-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB, INET, MACADDR, BYTEA

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── equipo (adapta cliente_id a INTEGER legacy) ────────────────────────
    op.create_table(
        'equipo',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('cliente_id', sa.Integer(),
                  sa.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sitio_id', UUID(as_uuid=True),
                  sa.ForeignKey('sitio.id'), nullable=True),
        sa.Column('cuarto_id', UUID(as_uuid=True),
                  sa.ForeignKey('cuarto.id'), nullable=True),
        sa.Column('gabinete_id', UUID(as_uuid=True),
                  sa.ForeignKey('gabinete.id'), nullable=True),
        sa.Column('categoria', sa.Text(), nullable=False),
        sa.Column('tipo', sa.Text(), nullable=False),
        sa.Column('marca', sa.Text()),
        sa.Column('modelo', sa.Text()),
        sa.Column('serie', sa.Text()),
        sa.Column('nombre', sa.Text(), nullable=False),
        sa.Column('hostname', sa.Text()),
        sa.Column('mac', MACADDR()),
        sa.Column('ip_gestion', INET()),
        sa.Column('firmware', sa.Text()),
        sa.Column('poe_watt', sa.Integer()),
        sa.Column('puertos_total', sa.Integer()),
        sa.Column('fecha_compra', sa.Date()),
        sa.Column('codigo_rack', sa.Text()),
        sa.Column('notas', sa.Text()),
        sa.CheckConstraint(
            "categoria IN ('activo_red','activo_final')",
            name='chk_equipo_categoria'
        ),
        sa.CheckConstraint(
            "tipo IN ('switch','router','firewall','ap','servidor','ups','pc','laptop',"
            "'impresora','telefono_ip','nvr','dvr','camara','pbx','reloj_marcador',"
            "'ont','convertidor_medios','otro')",
            name='chk_equipo_tipo'
        ),
        sa.CheckConstraint(
            "codigo_rack IS NULL OR codigo_rack ~ '^[A-Z]$'",
            name='chk_equipo_codigo_rack'
        ),
    )
    op.create_index('idx_equipo_cliente', 'equipo', ['cliente_id'])
    op.create_index('idx_equipo_gabinete', 'equipo', ['gabinete_id'])

    # ── patch_panel (nuevo, UUID, bajo gabinete) ────────────────────────────
    op.create_table(
        'patch_panel',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('gabinete_id', UUID(as_uuid=True),
                  sa.ForeignKey('gabinete.id', ondelete='CASCADE'), nullable=False),
        sa.Column('codigo', sa.Text(), nullable=False),
        sa.Column('tipo', sa.Text(), nullable=False),
        sa.Column('categoria', sa.Text()),
        sa.Column('puertos_total', sa.Integer(), nullable=False),
        sa.Column('fabricante', sa.Text()),
        sa.Column('modelo', sa.Text()),
        sa.CheckConstraint(
            "tipo IN ('cobre','fibra')",
            name='chk_patch_panel_tipo'
        ),
        sa.UniqueConstraint('gabinete_id', 'codigo', name='uq_patch_panel_gabinete_codigo'),
    )
    op.create_index('idx_patch_panel_gabinete', 'patch_panel', ['gabinete_id'])

    # ── puerto_terminal (polimórfico) ───────────────────────────────────────
    op.create_table(
        'puerto_terminal',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('tipo', sa.Text(), nullable=False),
        sa.Column('patch_panel_id', UUID(as_uuid=True),
                  sa.ForeignKey('patch_panel.id', ondelete='CASCADE'), nullable=True),
        sa.Column('equipo_id', UUID(as_uuid=True),
                  sa.ForeignKey('equipo.id', ondelete='CASCADE'), nullable=True),
        sa.Column('faceplate_cuarto_id', UUID(as_uuid=True),
                  sa.ForeignKey('cuarto.id'), nullable=True),
        sa.Column('numero', sa.Integer()),
        sa.Column('etiqueta_norm', sa.Text(), nullable=False),
        sa.Column('etiqueta_display', sa.Text()),
        sa.Column('velocidad_mbps', sa.Integer()),
        sa.Column('modo', sa.Text()),
        sa.Column('poe_habilitado', sa.Boolean(), server_default='false'),
        sa.Column('poe_watt', sa.Integer()),
        sa.Column('estado_admin', sa.Text()),
        sa.Column('notas', sa.Text()),
        sa.CheckConstraint(
            "tipo IN ('faceplate','patch_panel_port','switch_port','router_port',"
            "'ont_port','sfp_port','fiber_odf_port')",
            name='chk_puerto_tipo'
        ),
        sa.CheckConstraint(
            "modo IN ('access','trunk','hybrid','routed') OR modo IS NULL",
            name='chk_puerto_modo'
        ),
        sa.CheckConstraint(
            "estado_admin IN ('up','down','noshut','shut') OR estado_admin IS NULL",
            name='chk_puerto_estado'
        ),
        sa.CheckConstraint(
            "(patch_panel_id IS NOT NULL)::int + (equipo_id IS NOT NULL)::int "
            "+ (faceplate_cuarto_id IS NOT NULL)::int = 1",
            name='chk_puerto_un_parent'
        ),
    )
    op.create_index('idx_puerto_pp', 'puerto_terminal', ['patch_panel_id', 'numero'])
    op.create_index('idx_puerto_eq', 'puerto_terminal', ['equipo_id', 'numero'])
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_puerto_etq ON puerto_terminal (etiqueta_norm)"
    )

    # ── cable ──────────────────────────────────────────────────────────────
    op.create_table(
        'cable',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('codigo', sa.Text(), nullable=False, unique=True),
        sa.Column('tipo', sa.Text(), nullable=False),
        sa.Column('longitud_m', sa.Numeric(6, 2)),
        sa.Column('color', sa.Text()),
        sa.Column('ruta_fisica', sa.Text()),
        sa.Column('fecha_instalacion', sa.Date()),
        sa.Column('extremo_a_puerto_id', UUID(as_uuid=True),
                  sa.ForeignKey('puerto_terminal.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('extremo_b_puerto_id', UUID(as_uuid=True),
                  sa.ForeignKey('puerto_terminal.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('certificacion_pdf', sa.Text()),
        sa.Column('notas', sa.Text()),
        sa.CheckConstraint(
            "tipo IN ('utp_cat5e','utp_cat6','utp_cat6a','utp_cat7',"
            "'fibra_sm','fibra_mm_om1','fibra_mm_om3','fibra_mm_om4','coaxial','otro')",
            name='chk_cable_tipo'
        ),
        sa.CheckConstraint(
            'extremo_a_puerto_id <> extremo_b_puerto_id',
            name='chk_cable_extremos_distintos'
        ),
    )
    op.create_index('idx_cable_a', 'cable', ['extremo_a_puerto_id'])
    op.create_index('idx_cable_b', 'cable', ['extremo_b_puerto_id'])

    # ── jumper ─────────────────────────────────────────────────────────────
    op.create_table(
        'jumper',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('gabinete_id', UUID(as_uuid=True),
                  sa.ForeignKey('gabinete.id', ondelete='CASCADE'), nullable=False),
        sa.Column('codigo', sa.Text()),
        sa.Column('longitud_cm', sa.Integer()),
        sa.Column('color', sa.Text()),
        sa.Column('tipo', sa.Text()),
        sa.Column('extremo_a_puerto_id', UUID(as_uuid=True),
                  sa.ForeignKey('puerto_terminal.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('extremo_b_puerto_id', UUID(as_uuid=True),
                  sa.ForeignKey('puerto_terminal.id', ondelete='RESTRICT'), nullable=False),
        sa.CheckConstraint(
            "tipo IN ('utp','fibra') OR tipo IS NULL",
            name='chk_jumper_tipo'
        ),
        sa.CheckConstraint(
            'extremo_a_puerto_id <> extremo_b_puerto_id',
            name='chk_jumper_extremos_distintos'
        ),
    )
    op.create_index('idx_jumper_a', 'jumper', ['extremo_a_puerto_id'])
    op.create_index('idx_jumper_b', 'jumper', ['extremo_b_puerto_id'])

    # ── empalme_fibra ──────────────────────────────────────────────────────
    op.create_table(
        'empalme_fibra',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('odf_origen_id', UUID(as_uuid=True),
                  sa.ForeignKey('puerto_terminal.id'), nullable=False),
        sa.Column('odf_destino_id', UUID(as_uuid=True),
                  sa.ForeignKey('puerto_terminal.id'), nullable=False),
        sa.Column('conector', sa.Text()),
        sa.Column('hilos_totales', sa.Integer()),
        sa.Column('hilos_fusionados', sa.Integer()),
        sa.Column('hilos_detalle', JSONB()),
        sa.Column('atenuacion_db', sa.Numeric(5, 2)),
        sa.Column('fecha_fusion', sa.Date()),
        sa.Column('reporte_otdr_pdf', sa.Text()),
        sa.CheckConstraint(
            "conector IN ('SC-UPC','SC-APC','LC-UPC','LC-APC','ST','FC') OR conector IS NULL",
            name='chk_empalme_conector'
        ),
    )

    # ── endpoint ───────────────────────────────────────────────────────────
    op.create_table(
        'endpoint',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('cliente_id', sa.Integer(),
                  sa.ForeignKey('clients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('sitio_id', UUID(as_uuid=True),
                  sa.ForeignKey('sitio.id'), nullable=True),
        sa.Column('equipo_id', UUID(as_uuid=True),
                  sa.ForeignKey('equipo.id'), nullable=True),
        sa.Column('tipo', sa.Text(), nullable=False),
        sa.Column('nombre', sa.Text(), nullable=False),
        sa.Column('hostname', sa.Text()),
        sa.Column('ip', INET()),
        sa.Column('mac', MACADDR()),
        sa.Column('faceplate_puerto_id', UUID(as_uuid=True),
                  sa.ForeignKey('puerto_terminal.id'), nullable=True),
        sa.Column('habitacion', sa.Text()),
        sa.Column('extension_pbx', sa.Text()),
        sa.Column('office_license', sa.Text()),
        sa.Column('notas', sa.Text()),
        sa.CheckConstraint(
            "tipo IN ('pc','laptop','telefono_ip','camara','ap','impresora',"
            "'nvr','dvr','tv','sensor','reloj_marcador','tablet','otro')",
            name='chk_endpoint_tipo'
        ),
    )
    op.create_index('idx_endpoint_cliente', 'endpoint', ['cliente_id'])
    op.create_index('idx_endpoint_ip', 'endpoint', ['ip'])
    op.create_index('idx_endpoint_mac', 'endpoint', ['mac'])
    op.execute(
        "CREATE INDEX idx_endpoint_host ON endpoint (lower(hostname)) WHERE hostname IS NOT NULL"
    )

    # ── traza (cache hop-by-hop) ───────────────────────────────────────────
    op.create_table(
        'traza',
        sa.Column('id', UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('uuid_generate_v4()')),
        sa.Column('endpoint_id', UUID(as_uuid=True),
                  sa.ForeignKey('endpoint.id', ondelete='CASCADE'), nullable=False),
        sa.Column('hops', JSONB(), nullable=False),
        sa.Column('resumen', sa.Text()),
        sa.Column('hops_count', sa.Integer()),
        sa.Column('calculado_en', sa.TIMESTAMP(timezone=True),
                  server_default=sa.text('now()')),
    )
    op.create_index('idx_traza_endpoint', 'traza', ['endpoint_id'])


def downgrade() -> None:
    op.drop_table('traza')
    op.drop_table('endpoint')
    op.drop_table('empalme_fibra')
    op.drop_table('jumper')
    op.drop_table('cable')
    op.drop_table('puerto_terminal')
    op.drop_table('patch_panel')
    op.drop_table('equipo')
