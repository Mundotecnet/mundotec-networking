#!/usr/bin/env python3
"""
Migra datos legacy (clients + rooms) al nuevo schema multi-sitio.

Estrategia:
  clients  → sitio   (1 sitio por cliente, nombre igual)
  rooms    → cuarto  (1 edificio "Principal" por sitio, todos los rooms como cuartos)

Idempotente: si ya existe un sitio/cuarto para ese cliente/room no lo duplica.

Uso:
  python scripts/migrar_datos_legacy.py [--dry-run]
"""
import sys
import os
import argparse
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DB_URL = os.getenv("DATABASE_URL")
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)


def migrar(dry_run: bool = False):
    session = Session()
    try:
        clientes = session.execute(text("SELECT id, name, email, phone, address, contact FROM clients ORDER BY id")).fetchall()
        print(f"Clientes encontrados: {len(clientes)}")

        totales = {"sitios": 0, "edificios": 0, "cuartos": 0, "omitidos": 0}

        for c in clientes:
            nombre_sitio = (c.name or f"Cliente {c.id}").strip()

            # ── Verificar si ya existe sitio para este cliente ──
            existe_sitio = session.execute(
                text("SELECT id FROM sitio WHERE cliente_id = :cid AND nombre = :nom"),
                {"cid": c.id, "nom": nombre_sitio}
            ).fetchone()

            if existe_sitio:
                sitio_id = existe_sitio.id
                print(f"  [SKIP] Sitio '{nombre_sitio}' ya existe → {sitio_id}")
                totales["omitidos"] += 1
            else:
                sitio_id = str(uuid.uuid4())
                if not dry_run:
                    session.execute(text("""
                        INSERT INTO sitio (id, cliente_id, nombre, direccion)
                        VALUES (:id, :cid, :nombre, :dir)
                    """), {
                        "id": sitio_id,
                        "cid": c.id,
                        "nombre": nombre_sitio,
                        "dir": c.address,
                    })
                print(f"  [NUEVO] Sitio '{nombre_sitio}' (cliente_id={c.id})")
                totales["sitios"] += 1

            # ── Edificio "Principal" por defecto ──
            existe_edif = session.execute(
                text("SELECT id FROM edificio WHERE sitio_id = :sid AND codigo = 'A'"),
                {"sid": sitio_id}
            ).fetchone()

            if existe_edif:
                edificio_id = existe_edif.id
            else:
                edificio_id = str(uuid.uuid4())
                if not dry_run:
                    session.execute(text("""
                        INSERT INTO edificio (id, sitio_id, codigo, nombre, piso_default)
                        VALUES (:id, :sid, 'A', 'Principal', 1)
                    """), {"id": edificio_id, "sid": sitio_id})
                print(f"    [NUEVO] Edificio 'A - Principal'")
                totales["edificios"] += 1

            # ── Rooms → Cuartos ──
            rooms = session.execute(
                text("SELECT id, name, location FROM rooms WHERE client_id = :cid ORDER BY id"),
                {"cid": c.id}
            ).fetchall()

            for idx, r in enumerate(rooms, start=1):
                existe_cuarto = session.execute(
                    text("SELECT id FROM cuarto WHERE room_legacy_id = :rid"),
                    {"rid": r.id}
                ).fetchone()

                if existe_cuarto:
                    print(f"      [SKIP] Cuarto room_id={r.id} '{r.name}' ya migrado")
                    totales["omitidos"] += 1
                    continue

                codigo = chr(ord('A') + (idx - 1)) if idx <= 26 else str(idx)
                nombre = (r.name or f"Cuarto {r.id}").strip()[:100]

                if not dry_run:
                    cuarto_id = str(uuid.uuid4())
                    session.execute(text("""
                        INSERT INTO cuarto (id, edificio_id, room_legacy_id, piso, codigo, nombre, descripcion)
                        VALUES (:id, :eid, :rid, 1, :cod, :nom, :desc)
                    """), {
                        "id": cuarto_id,
                        "eid": edificio_id,
                        "rid": r.id,
                        "cod": codigo,
                        "nom": nombre,
                        "desc": r.location,
                    })
                print(f"      [NUEVO] Cuarto '{codigo}' → '{nombre}' (room_id={r.id})")
                totales["cuartos"] += 1

        if not dry_run:
            session.commit()
            print(f"\n✓ Migración completada.")
        else:
            print(f"\n[DRY-RUN] No se escribió nada.")

        print(f"  Sitios creados:    {totales['sitios']}")
        print(f"  Edificios creados: {totales['edificios']}")
        print(f"  Cuartos creados:   {totales['cuartos']}")
        print(f"  Omitidos (ya existían): {totales['omitidos']}")

    except Exception as e:
        session.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Simula sin escribir en BD")
    args = parser.parse_args()
    migrar(dry_run=args.dry_run)
