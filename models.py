from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, ForeignKey,
    Text, LargeBinary, JSON
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=True)
    role = Column(String(20), default="readonly", nullable=False)
    auth_provider = Column(String(20), default="local", nullable=False)
    google_id = Column(String(255), unique=True, nullable=True)
    google_email = Column(String(255), nullable=True)
    google_picture = Column(String(500), nullable=True)
    google_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    audit_logs = relationship(
        "AuditLog", back_populates="user",
        foreign_keys="AuditLog.user_id", lazy="select"
    )
    backups = relationship(
        "BackupFile", back_populates="uploader",
        foreign_keys="BackupFile.uploaded_by", lazy="select"
    )
    confirmed_ports = relationship(
        "PatchPort", back_populates="confirmed_by_user",
        foreign_keys="PatchPort.confirmed_by", lazy="select"
    )


class Client(Base):
    __tablename__ = "clients"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    contact = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    label_format = Column(String(30), default="edificio_cuarto_rack", nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    rooms = relationship("Room", back_populates="client", cascade="all, delete-orphan", lazy="select")
    buildings = relationship("Building", back_populates="client", cascade="all, delete-orphan", lazy="select")
    audit_logs = relationship(
        "AuditLog", back_populates="client",
        foreign_keys="AuditLog.client_id", lazy="select"
    )
    projects = relationship("Project", back_populates="client", lazy="select")


class Building(Base):
    __tablename__ = "buildings"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    letter = Column(String(1), nullable=False)
    address = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    client = relationship("Client", back_populates="buildings")
    rooms = relationship("Room", back_populates="building", cascade="all, delete-orphan", lazy="select")


class Room(Base):
    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=True)
    letter = Column(String(1), nullable=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    switch_model = Column(String(100), nullable=True)
    switch_mac = Column(String(50), nullable=True)
    switch_ip = Column(String(50), nullable=True)
    ap_model = Column(String(100), nullable=True)
    ap_mac = Column(String(50), nullable=True)
    ap_ip = Column(String(50), nullable=True)
    patch_label_format = Column(String(20), default="simple", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    client = relationship("Client", back_populates="rooms")
    building = relationship("Building", back_populates="rooms")
    patch_panels = relationship("PatchPanel", back_populates="room", cascade="all, delete-orphan", lazy="select")
    devices = relationship("Device", back_populates="room", cascade="all, delete-orphan", lazy="select")
    vlans = relationship("Vlan", back_populates="room", cascade="all, delete-orphan", lazy="select")
    connections = relationship("Connection", back_populates="room", cascade="all, delete-orphan", lazy="select")
    cabinets = relationship("Cabinet", back_populates="room", cascade="all, delete-orphan", lazy="select")


class Cabinet(Base):
    __tablename__ = "cabinets"

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    letter = Column(String(1), nullable=False)
    rack_units = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    room = relationship("Room", back_populates="cabinets")
    patch_panels = relationship("PatchPanel", back_populates="cabinet",
                                cascade="all, delete-orphan", lazy="select")
    devices = relationship("Device", back_populates="cabinet", lazy="select")


class Vlan(Base):
    __tablename__ = "vlans"

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    vlan_id = Column(Integer, nullable=False)
    name = Column(String(100), nullable=False)
    subnet = Column(String(50), nullable=True)
    gateway = Column(String(50), nullable=True)
    dhcp = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)

    room = relationship("Room", back_populates="vlans")
    patch_ports = relationship("PatchPort", back_populates="vlan", foreign_keys="PatchPort.vlan_id", lazy="select")
    device_ports = relationship("DevicePort", back_populates="vlan", foreign_keys="DevicePort.vlan_id", lazy="select")


class PatchPanel(Base):
    __tablename__ = "patch_panels"

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    cabinet_id = Column(Integer, ForeignKey("cabinets.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(100), nullable=False)
    brand = Column(String(100), nullable=True)
    model = Column(String(100), nullable=True)
    floor = Column(Integer, nullable=False, default=1)
    building = Column(String(1), nullable=True)
    room_letter = Column(String(1), nullable=False, default="A")
    panel_letter = Column(String(1), nullable=False, default="A")
    rack_id = Column(String(5), nullable=True)
    format = Column(String(20), default="simple", nullable=False)
    notes = Column(Text, nullable=True)

    room = relationship("Room", back_populates="patch_panels")
    cabinet = relationship("Cabinet", back_populates="patch_panels")
    ports = relationship(
        "PatchPort", back_populates="patch_panel",
        cascade="all, delete-orphan",
        order_by="PatchPort.number", lazy="select"
    )


class PatchPort(Base):
    __tablename__ = "patch_ports"

    id = Column(Integer, primary_key=True)
    patch_panel_id = Column(Integer, ForeignKey("patch_panels.id", ondelete="CASCADE"), nullable=False)
    number = Column(Integer, nullable=False)
    label = Column(String(50), nullable=True)

    status = Column(String(20), default="sin_revisar", nullable=False)
    completeness_status = Column(String(20), default="sin_revisar", nullable=False)
    confirmed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    confirmation_notes = Column(Text, nullable=True)

    node_type = Column(String(20), nullable=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    node_description = Column(Text, nullable=True)
    node_mac = Column(String(50), nullable=True)
    node_ip = Column(String(50), nullable=True)
    vlan_id = Column(Integer, ForeignKey("vlans.id", ondelete="SET NULL"), nullable=True)
    notes = Column(Text, nullable=True)

    # FK to DevicePort — use_alter to handle circular dependency
    switch_port_id = Column(
        Integer,
        ForeignKey("device_ports.id", ondelete="SET NULL", use_alter=True, name="fk_pp_switch_port"),
        nullable=True
    )

    patch_panel = relationship("PatchPanel", back_populates="ports")
    device = relationship("Device", foreign_keys=[device_id], lazy="select")
    vlan = relationship("Vlan", back_populates="patch_ports", foreign_keys=[vlan_id])
    confirmed_by_user = relationship(
        "User", back_populates="confirmed_ports", foreign_keys=[confirmed_by], lazy="select"
    )
    switch_port = relationship(
        "DevicePort", foreign_keys=[switch_port_id],
        back_populates="patch_ports_linked", lazy="select"
    )


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    cabinet_id = Column(Integer, ForeignKey("cabinets.id", ondelete="SET NULL"), nullable=True)
    category = Column(String(20), nullable=False)
    name = Column(String(255), nullable=False)
    device_type = Column(String(30), nullable=False)
    brand = Column(String(100), nullable=False, default="")
    model = Column(String(100), nullable=False, default="")
    serial = Column(String(100), nullable=True)
    mac = Column(String(50), nullable=True)
    ip = Column(String(50), nullable=True)
    hostname = Column(String(100), nullable=True)
    admin_port = Column(String(50), nullable=True)
    port_count = Column(Integer, default=0, nullable=False)
    username_encrypted = Column(Text, nullable=True)
    password_encrypted = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    room = relationship("Room", back_populates="devices")
    cabinet = relationship("Cabinet", back_populates="devices")
    ports = relationship(
        "DevicePort", back_populates="device",
        cascade="all, delete-orphan",
        foreign_keys="DevicePort.device_id", lazy="select"
    )
    backups = relationship(
        "BackupFile", back_populates="device",
        cascade="all, delete-orphan", lazy="select"
    )


class DevicePort(Base):
    __tablename__ = "device_ports"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    port_number = Column(String(20), nullable=False)
    port_label = Column(String(100), nullable=True)
    vlan_id = Column(Integer, ForeignKey("vlans.id", ondelete="SET NULL"), nullable=True)
    port_mode = Column(String(20), nullable=True)
    poe_enabled = Column(Boolean, default=False)
    status = Column(String(20), default="libre", nullable=False)
    speed = Column(String(20), nullable=True)

    patch_port_id = Column(Integer, ForeignKey("patch_ports.id", ondelete="SET NULL"), nullable=True)
    end_device_id = Column(Integer, ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    end_description = Column(Text, nullable=True)
    end_mac = Column(String(50), nullable=True)
    end_ip = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)

    device = relationship("Device", back_populates="ports", foreign_keys=[device_id])
    vlan = relationship("Vlan", back_populates="device_ports", foreign_keys=[vlan_id])
    end_device = relationship("Device", foreign_keys=[end_device_id], lazy="select")
    connected_patch_port = relationship(
        "PatchPort", foreign_keys=[patch_port_id], lazy="select"
    )
    patch_ports_linked = relationship(
        "PatchPort", foreign_keys="PatchPort.switch_port_id",
        back_populates="switch_port", lazy="select"
    )


class BackupFile(Base):
    __tablename__ = "backup_files"

    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_content = Column(LargeBinary, nullable=False)
    file_size = Column(Integer, nullable=False)
    version = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    uploaded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    device = relationship("Device", back_populates="backups")
    uploader = relationship("User", back_populates="backups", foreign_keys=[uploaded_by])


class Connection(Base):
    __tablename__ = "connections"

    id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    description = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    node_a_type = Column(String(20), nullable=False)
    node_a_id = Column(Integer, nullable=False)
    node_b_type = Column(String(20), nullable=False)
    node_b_id = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    room = relationship("Room", back_populates="connections")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    user_name = Column(String(100), nullable=True)
    action = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(Integer, nullable=True)
    entity_label = Column(String(255), nullable=True)
    client_id = Column(Integer, ForeignKey("clients.id", ondelete="SET NULL"), nullable=True, index=True)
    old_values = Column(JSON, nullable=True)
    new_values = Column(JSON, nullable=True)
    ip_address = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    notes = Column(Text, nullable=True)

    user = relationship("User", back_populates="audit_logs", foreign_keys=[user_id])
    client = relationship("Client", back_populates="audit_logs", foreign_keys=[client_id])


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(20), default="activo", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    client = relationship("Client", back_populates="projects")
    logs = relationship("ProjectLog", back_populates="project", cascade="all, delete-orphan")


class ProjectLog(Base):
    __tablename__ = "project_logs"

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    entry = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    project = relationship("Project", back_populates="logs")
