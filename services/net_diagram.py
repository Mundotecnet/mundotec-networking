"""
Generador de diagramas de red con ReportLab Drawing.
Sin dependencias externas adicionales.
"""
from collections import defaultdict, deque
from reportlab.graphics.shapes import (
    Drawing, Rect, Line, String, Group, Circle
)
from reportlab.lib.colors import HexColor, white, black

NODE_W, NODE_H = 80, 30
LEVEL_GAP = 80
MIN_WIDTH = 480

NODE_COLORS: dict = {
    "switch":          HexColor("#1a6fa8"),
    "router":          HexColor("#1a6fa8"),
    "firewall":        HexColor("#1a6fa8"),
    "ap":              HexColor("#1a6b3a"),
    "servidor":        HexColor("#424242"),
    "ups":             HexColor("#424242"),
    "pc":              HexColor("#1565c0"),
    "estacion":        HexColor("#1565c0"),
    "camara":          HexColor("#e65100"),
    "nvr":             HexColor("#e65100"),
    "dvr":             HexColor("#e65100"),
    "pbx":             HexColor("#880e4f"),
    "reloj_marcador":  HexColor("#880e4f"),
    "impresora":       HexColor("#880e4f"),
    "otro":            HexColor("#546e7a"),
}

VLAN_COLORS = [
    HexColor("#1565c0"), HexColor("#2e7d32"), HexColor("#f57f17"),
    HexColor("#6a1b9a"), HexColor("#00838f"), HexColor("#ad1457"),
    HexColor("#37474f"), HexColor("#4e342e"),
]


def _node_color(device_type: str) -> HexColor:
    return NODE_COLORS.get(device_type, NODE_COLORS["otro"])


def _make_node(x: float, y: float, label: str, color: HexColor) -> Group:
    g = Group()
    g.add(Rect(x, y, NODE_W, NODE_H, rx=4, ry=4,
               fillColor=color, strokeColor=white, strokeWidth=0.8))
    max_chars = 12
    display = label if len(label) <= max_chars else label[:max_chars - 1] + "…"
    g.add(String(x + NODE_W / 2, y + NODE_H / 2 - 4, display,
                 fontSize=7, fillColor=white,
                 textAnchor="middle"))
    return g


def _bfs_levels(root_id: int, adjacency: dict) -> dict:
    levels: dict[int, int] = {root_id: 0}
    q = deque([root_id])
    while q:
        nid = q.popleft()
        for nb in adjacency.get(nid, []):
            if nb not in levels:
                levels[nb] = levels[nid] + 1
                q.append(nb)
    return levels


def _layout(nodes: list[int], levels: dict, total_width: float) -> dict:
    by_level: dict[int, list] = defaultdict(list)
    for nid in nodes:
        by_level[levels.get(nid, 0)].append(nid)

    positions: dict[int, tuple] = {}
    for lv, nids in by_level.items():
        count = len(nids)
        spacing = total_width / (count + 1)
        for i, nid in enumerate(nids):
            x = spacing * (i + 1) - NODE_W / 2
            y_from_top = lv * LEVEL_GAP + 20
            positions[nid] = (x, y_from_top)
    return positions


def build_diagram_room(room, width: float = MIN_WIDTH) -> Drawing:
    """Build a ReportLab Drawing for a single room."""
    devices = list(room.devices)
    if not devices:
        d = Drawing(width, 80)
        d.add(String(width / 2, 40, f"[Sin dispositivos — {room.name}]",
                     fontSize=9, fillColor=HexColor("#546e7a"), textAnchor="middle"))
        return d

    # Build adjacency from device_ports
    adjacency: dict[int, list] = defaultdict(list)
    for dev in devices:
        for port in dev.ports:
            if port.end_device_id and port.end_device_id != dev.id:
                adjacency[dev.id].append(port.end_device_id)
                adjacency[port.end_device_id].append(dev.id)

    # Root = switch or first device
    root = next(
        (d.id for d in devices if d.device_type in ("switch", "router")),
        devices[0].id
    )
    device_ids = [d.id for d in devices]
    levels = _bfs_levels(root, adjacency)
    for nid in device_ids:
        if nid not in levels:
            levels[nid] = max(levels.values(), default=0) + 1

    positions = _layout(device_ids, levels, width)
    max_y = max(y for _, y in positions.values()) + NODE_H + 40

    drawing = Drawing(width, max(max_y, 120))

    dev_map = {d.id: d for d in devices}

    # Draw connections
    drawn_edges: set = set()
    for dev in devices:
        for port in dev.ports:
            if port.end_device_id and port.end_device_id in positions:
                edge = tuple(sorted((dev.id, port.end_device_id)))
                if edge in drawn_edges:
                    continue
                drawn_edges.add(edge)
                x1, y1 = positions[dev.id]
                x2, y2 = positions[port.end_device_id]
                vlan_idx = (port.vlan_id or 0) % len(VLAN_COLORS)
                color = VLAN_COLORS[vlan_idx]
                drawing.add(Line(x1 + NODE_W / 2, y1 + NODE_H / 2,
                                 x2 + NODE_W / 2, y2 + NODE_H / 2,
                                 strokeColor=color, strokeWidth=1.5))

    # Draw nodes
    for dev in devices:
        if dev.id not in positions:
            continue
        x, y = positions[dev.id]
        top_y = max_y - y - NODE_H  # flip: top-down in drawing coords
        color = _node_color(dev.device_type)
        drawing.add(_make_node(x, top_y, dev.name, color))

    # Title
    drawing.add(String(4, max(max_y, 120) - 12, room.name,
                       fontSize=8, fillColor=HexColor("#546e7a")))
    return drawing


def build_diagram_client(client, width: float = MIN_WIDTH) -> Drawing:
    """Stacked diagram of all rooms for a client."""
    parts = [build_diagram_room(r, width) for r in client.rooms if r.devices]
    if not parts:
        d = Drawing(width, 80)
        d.add(String(width / 2, 40, "Sin dispositivos registrados",
                     fontSize=9, fillColor=HexColor("#546e7a"), textAnchor="middle"))
        return d

    gap = 20
    total_h = sum(p.height for p in parts) + gap * (len(parts) - 1) + gap * 2
    master = Drawing(width, total_h)
    y_offset = gap
    for part in reversed(parts):
        for item in part.contents:
            item.y = item.y + y_offset if hasattr(item, "y") else item.y
            master.add(item)
        y_offset += part.height + gap
    return master
