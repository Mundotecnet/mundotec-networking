#!/usr/bin/env python3
"""Seed de datos demo para desarrollo — MundoTec Networking. Idempotente."""
import sys, os, uuid, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

engine = create_engine(os.getenv("DATABASE_URL"))
Session = sessionmaker(bind=engine)

def _uid(): return str(uuid.uuid4())

def seed(reset=False):
    db = Session()
    try:
        if reset:
            print("Limpiando datos demo...")
            db.execute(text("DELETE FROM clients WHERE name = 'DEMO - Clínica San José'"))
            db.commit()
            print("  ✓ Datos demo eliminados")

        cli = db.execute(text("SELECT id FROM clients WHERE name = 'DEMO - Clínica San José'")).scalar()
        if not cli:
            db.execute(text("""
                INSERT INTO clients (name, email, phone, address, contact)
                VALUES ('DEMO - Clínica San José','admin@clinicasj.cr','2200-0000','San José, Costa Rica','Gerencia TI')
            """))
            db.flush()
            cli = db.execute(text("SELECT id FROM clients WHERE name = 'DEMO - Clínica San José'")).scalar()
            print(f"  ✓ Cliente demo id={cli}")

        sitio_id = db.execute(text("SELECT id::text FROM sitio WHERE cliente_id=:cid AND nombre='Sede Central'"), {"cid": cli}).scalar()
        if not sitio_id:
            sitio_id = _uid()
            db.execute(text("INSERT INTO sitio (id, cliente_id, nombre, direccion, latitud, longitud) VALUES (:id,:cid,'Sede Central','Av. Central, San José',9.9281,-84.0907)"), {"id": sitio_id, "cid": cli})
            print("  ✓ Sitio 'Sede Central'")

        edif_id = db.execute(text("SELECT id::text FROM edificio WHERE sitio_id=:sid AND codigo='A'"), {"sid": sitio_id}).scalar()
        if not edif_id:
            edif_id = _uid()
            db.execute(text("INSERT INTO edificio (id, sitio_id, codigo, nombre, piso_default) VALUES (:id,:sid,'A','Torre Médica',1)"), {"id": edif_id, "sid": sitio_id})

        cuartos_def = [("A", 1, "MDF Principal"), ("B", 2, "IDF Piso 2"), ("C", 3, "IDF Piso 3")]
        cuarto_ids = {}
        for cod, piso, nom in cuartos_def:
            cuid = db.execute(text("SELECT id::text FROM cuarto WHERE edificio_id=:eid AND codigo=:cod"), {"eid": edif_id, "cod": cod}).scalar()
            if not cuid:
                cuid = _uid()
                db.execute(text("INSERT INTO cuarto (id, edificio_id, piso, codigo, nombre) VALUES (:id,:eid,:p,:cod,:nom)"), {"id": cuid, "eid": edif_id, "p": piso, "cod": cod, "nom": nom})
                print(f"  ✓ Cuarto '{nom}'")
            cuarto_ids[cod] = cuid

        gab_ids = {}
        for cc, ci in cuarto_ids.items():
            gid = db.execute(text("SELECT id::text FROM gabinete WHERE cuarto_id=:cid AND codigo='A'"), {"cid": ci}).scalar()
            if not gid:
                gid = _uid()
                db.execute(text("INSERT INTO gabinete (id, cuarto_id, codigo, nombre, unidades_rack) VALUES (:id,:cid,'A','Rack Principal',42)"), {"id": gid, "cid": ci})
            gab_ids[cc] = gid

        for cc, nom, tipo, cat, marca, mod, ip, rack in [
            ("A","SW-CORE-01","switch","activo_red","Cisco","C9300-48P","192.168.1.1","A"),
            ("A","FW-01","firewall","activo_red","Fortinet","FG-100F","192.168.1.254","B"),
            ("B","SW-DIST-P2","switch","activo_red","Cisco","C2960X-24","192.168.1.2","A"),
            ("C","SW-DIST-P3","switch","activo_red","Cisco","C2960X-24","192.168.1.3","A"),
        ]:
            eid = db.execute(text("SELECT id::text FROM equipo WHERE nombre=:nom AND cliente_id=:cid"), {"nom": nom, "cid": cli}).scalar()
            if not eid:
                eid = _uid()
                db.execute(text("""INSERT INTO equipo (id,cliente_id,sitio_id,cuarto_id,gabinete_id,nombre,tipo,categoria,marca,modelo,ip_gestion,codigo_rack)
                    VALUES (:id,:cid,:sid,:cuid,:gid,:nom,:tipo,:cat,:marca,:mod,:ip,:rack)"""),
                    {"id":eid,"cid":cli,"sid":sitio_id,"cuid":cuarto_ids[cc],"gid":gab_ids[cc],"nom":nom,"tipo":tipo,"cat":cat,"marca":marca,"mod":mod,"ip":ip,"rack":rack})
                print(f"  ✓ Equipo '{nom}'")

        pp_id = db.execute(text("SELECT id::text FROM patch_panel WHERE gabinete_id=:gid AND codigo='A'"), {"gid": gab_ids["A"]}).scalar()
        if not pp_id:
            pp_id = _uid()
            db.execute(text("INSERT INTO patch_panel (id,gabinete_id,codigo,tipo,categoria,puertos_total) VALUES (:id,:gid,'A','cobre','Cat6',24)"), {"id": pp_id, "gid": gab_ids["A"]})
            for i in range(1, 25):
                db.execute(text("INSERT INTO puerto_terminal (id,tipo,patch_panel_id,numero,etiqueta_norm) VALUES (:id,'patch_panel_port',:pp,:num,:etq) ON CONFLICT (etiqueta_norm) DO NOTHING"),
                    {"id": _uid(), "pp": pp_id, "num": i, "etq": f"PP-1-A-A-A-A-{i:02d}"})
            print("  ✓ Patch Panel A con 24 puertos")

        eps = [("PC-ADM-01","pc","192.168.10.10","Consultorio 101"),("PC-ADM-02","pc","192.168.10.11","Consultorio 102"),
               ("IP-PHONE-101","telefono_ip","192.168.20.10","Consultorio 101"),("NVR-CCTV-01","nvr","192.168.30.10","Sala de Servidores"),("AP-LOBBY","ap","192.168.40.10","Lobby Principal")]
        for nom, tipo, ip, hab in eps:
            if not db.execute(text("SELECT id FROM endpoint WHERE nombre=:nom AND cliente_id=:cid"), {"nom":nom,"cid":cli}).scalar():
                db.execute(text("INSERT INTO endpoint (id,cliente_id,sitio_id,nombre,tipo,ip,habitacion) VALUES (:id,:cid,:sid,:nom,:tipo,:ip,:hab)"),
                    {"id":_uid(),"cid":cli,"sid":sitio_id,"nom":nom,"tipo":tipo,"ip":ip,"hab":hab})
        print(f"  ✓ {len(eps)} endpoints demo")

        for vid, nom, col in [(10,"Administrativa","#4A9EFF"),(20,"VoIP","#F0A500"),(30,"CCTV","#E94E77"),(40,"WiFi Guest","#3FB950"),(100,"Gestión","#8B949E")]:
            if not db.execute(text("SELECT id FROM vlan WHERE cliente_id=:cid AND vlan_id=:vid"), {"cid":cli,"vid":vid}).scalar():
                db.execute(text("INSERT INTO vlan (id,cliente_id,sitio_id,vlan_id,nombre,color_hex) VALUES (:id,:cid,:sid,:vid,:nom,:col)"),
                    {"id":_uid(),"cid":cli,"sid":sitio_id,"vid":vid,"nom":nom,"col":col})
        print("  ✓ 5 VLANs demo")

        vlan10 = db.execute(text("SELECT id::text FROM vlan WHERE cliente_id=:cid AND vlan_id=10"), {"cid":cli}).scalar()
        if vlan10 and not db.execute(text("SELECT id FROM subred WHERE sitio_id=:sid AND cidr='192.168.10.0/24'"), {"sid":sitio_id}).scalar():
            db.execute(text("INSERT INTO subred (id,sitio_id,vlan_id,cidr,gateway,tipo,descripcion) VALUES (:id,:sid,:vid,'192.168.10.0/24','192.168.10.1','lan','Red Administrativa')"),
                {"id":_uid(),"sid":sitio_id,"vid":vlan10})
            print("  ✓ Subred 192.168.10.0/24")

        if not db.execute(text("SELECT id FROM credencial WHERE cliente_id=:cid AND servicio='SW-CORE-01 SSH'"), {"cid":cli}).scalar():
            from services.crypto import encrypt as encrypt_password
            db.execute(text("INSERT INTO credencial (id,cliente_id,servicio,usuario,password_cifrado,url) VALUES (:id,:cid,'SW-CORE-01 SSH','admin',:pw,'ssh://192.168.1.1')"),
                {"id":_uid(),"cid":cli,"pw":encrypt_password("Cisco@2026!")})
            print("  ✓ Credencial SW-CORE-01 SSH")

        if not db.execute(text("SELECT id FROM licencia WHERE cliente_id=:cid AND producto='Microsoft 365 Business'"), {"cid":cli}).scalar():
            db.execute(text("INSERT INTO licencia (id,cliente_id,producto,tipo,activaciones_max,activaciones_usadas,fecha_vencimiento,proveedor) VALUES (:id,:cid,'Microsoft 365 Business','Business Premium',50,23,'2027-01-15','Microsoft')"),
                {"id":_uid(),"cid":cli})
            print("  ✓ Licencia Microsoft 365")

        if not db.execute(text("SELECT id FROM wan WHERE sitio_id=:sid"), {"sid":sitio_id}).scalar():
            db.execute(text("INSERT INTO wan (id,sitio_id,isp,producto,ip_publica,ancho_banda_mbps,observaciones) VALUES (:id,:sid,'Cabletica','Fibra 500/500','200.100.50.10',500,'Principal')"),
                {"id":_uid(),"sid":sitio_id})
            print("  ✓ WAN Cabletica 500 Mbps")

        db.commit()
        print(f"\n✓ Seed completado — cliente demo id={cli}")
    except Exception as e:
        db.rollback()
        print(f"ERROR: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    seed(reset=args.reset)
