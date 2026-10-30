"""IND8 returns floor: the domain model behind StockFlow.

Flow:
    inbound truck (from another organization)
      -> check in at a dock door -> unload boxes to staging
      -> distribute boxes to process stations -> open box
      -> route each item: clean -> yellow tote (sellable), damaged -> liquidation pallet
      -> full yellow totes -> tranship -> load outbound truck -> ship to be sold
      -> liquidation pallet -> ship to liquidation

Everything is kept in memory and every state change is recorded as an event.
This module has no web dependencies, so it can be tested on its own.
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

DOORS = 4
STATIONS = 4
TOTE_CAPACITY = 8
OUTBOUND_CAPACITY = 10  # yellow totes per outbound truck
MAX_IN_TRANSIT = 6

ORGANIZATIONS = [
    "Northgate Retail",
    "Bluepeak Outlet",
    "Harbor Supply Co.",
    "Summit Home Goods",
    "Riverside Electronics",
]
CATALOG = [
    ("Wireless Mouse", "Electronics"),
    ("Bluetooth Headphones", "Electronics"),
    ("USB-C Cable", "Electronics"),
    ("Smart Watch", "Electronics"),
    ("Coffee Maker", "Kitchen"),
    ("Cookware Set", "Kitchen"),
    ("Desk Lamp", "Home"),
    ("Throw Pillow", "Home"),
    ("Yoga Mat", "Sports"),
    ("Water Bottle", "Sports"),
    ("Phone Case", "Accessories"),
    ("Kids' Sneakers", "Apparel"),
]
CLEAN_NOTES = [
    "Sealed in original packaging",
    "Opened, like new",
    "Minor box wear, item perfect",
    "Tested and working",
]
DAMAGE_NOTES = {
    "Electronics": ["Cracked casing", "Won't power on", "Water damage", "Frayed cable"],
    "Kitchen": ["Cracked glass", "Dented body", "Missing parts"],
    "Home": ["Broken base", "Torn fabric", "Stained"],
    "Sports": ["Torn surface", "Punctured", "Dented"],
    "Accessories": ["Cracked", "Scratched and scuffed"],
    "Apparel": ["Torn fabric", "Stained", "Missing one shoe"],
}

# XP awarded per action
XP = {
    "check_in": 5,
    "unload": 20,
    "distribute": 5,
    "open_box": 5,
    "route_correct": 10,
    "route_clean_to_liquidation": 2,
    "box_done": 5,
    "tote_full": 15,
    "load_tote": 5,
    "ship_outbound": 50,
    "ship_liquidation": 30,
}
LEVELS = [
    (0, "Rookie"),
    (150, "Sorter"),
    (400, "Processor"),
    (800, "Problem Solver"),
    (1400, "Storm Chaser"),
    (2200, "Thunder Legend"),
]


class DomainError(Exception):
    """A rule of the floor was broken. `status` maps to an HTTP status code."""

    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Truck:
    id: str
    origin: str
    status: str  # in_transit | at_door | unloaded
    eta_minutes: int
    box_ids: list[str] = field(default_factory=list)
    door: int | None = None
    arrived_at: str | None = None
    unloaded_at: str | None = None


@dataclass
class Box:
    id: str
    truck_id: str
    origin: str
    status: str  # on_truck | staged | at_station | open | done
    item_ids: list[str] = field(default_factory=list)
    station: int | None = None


@dataclass
class Item:
    id: str
    box_id: str
    name: str
    category: str
    condition: str  # clean | damaged
    note: str
    status: str = "in_box"  # in_box | yellow_tote | liquidation
    tote_id: str | None = None
    pallet_id: str | None = None


@dataclass
class Tote:
    id: str
    status: str = "open"  # open | full | loaded | shipped
    item_ids: list[str] = field(default_factory=list)
    outbound_id: str | None = None


@dataclass
class OutboundTruck:
    id: str
    destination: str = "Resale marketplace"
    status: str = "loading"  # loading | shipped
    tote_ids: list[str] = field(default_factory=list)
    shipped_at: str | None = None


@dataclass
class Pallet:
    id: str
    partner: str = "Liquidation partner"
    status: str = "open"  # open | shipped
    item_ids: list[str] = field(default_factory=list)
    shipped_at: str | None = None


@dataclass
class Event:
    id: int
    at: str
    area: str  # shift | unload | process | tranship | liquidation
    kind: str
    message: str
    xp: int = 0
    data: dict = field(default_factory=dict)


class Warehouse:
    def __init__(self, seed: int | None = 8):
        self.rng = random.Random(seed)
        self.trucks: dict[str, Truck] = {}
        self.boxes: dict[str, Box] = {}
        self.items: dict[str, Item] = {}
        self.totes: dict[str, Tote] = {}
        self.outbound: dict[str, OutboundTruck] = {}
        self.pallets: dict[str, Pallet] = {}
        self.events: list[Event] = []
        self._seq = {"truck": 1000, "box": 20000, "item": 1000, "tote": 100, "out": 500, "pallet": 300, "event": 0}
        self.open_tote = self._new_tote()
        self.open_outbound = self._new_outbound()
        self.open_pallet = self._new_pallet()

    # ---------- setup ----------
    @classmethod
    def seeded(cls, seed: int | None = 8) -> "Warehouse":
        wh = cls(seed)
        wh._log("shift", "shift_started", "Shift started at IND8. Home of the Thunder.")
        first = wh._new_truck()
        first.status, first.door, first.arrived_at = "at_door", 1, now()
        wh._new_truck()
        wh._new_truck()
        return wh

    def _next(self, key: str) -> int:
        self._seq[key] += 1
        return self._seq[key]

    def _new_truck(self) -> Truck:
        truck = Truck(
            id=f"TRK-{self._next('truck')}",
            origin=self.rng.choice(ORGANIZATIONS),
            status="in_transit",
            eta_minutes=self.rng.randint(10, 45),
        )
        for _ in range(self.rng.randint(3, 6)):
            box = Box(id=f"BX-{self._next('box')}", truck_id=truck.id, origin=truck.origin, status="on_truck")
            for _ in range(self.rng.randint(2, 5)):
                name, category = self.rng.choice(CATALOG)
                damaged = self.rng.random() < 0.25
                item = Item(
                    id=f"IT-{self._next('item')}",
                    box_id=box.id,
                    name=name,
                    category=category,
                    condition="damaged" if damaged else "clean",
                    note=self.rng.choice(DAMAGE_NOTES[category] if damaged else CLEAN_NOTES),
                )
                self.items[item.id] = item
                box.item_ids.append(item.id)
            self.boxes[box.id] = box
            truck.box_ids.append(box.id)
        self.trucks[truck.id] = truck
        return truck

    def _new_tote(self) -> Tote:
        tote = Tote(id=f"YT-{self._next('tote')}")
        self.totes[tote.id] = tote
        return tote

    def _new_outbound(self) -> OutboundTruck:
        truck = OutboundTruck(id=f"OUT-{self._next('out')}")
        self.outbound[truck.id] = truck
        return truck

    def _new_pallet(self) -> Pallet:
        pallet = Pallet(id=f"LQ-{self._next('pallet')}")
        self.pallets[pallet.id] = pallet
        return pallet

    def _log(self, area: str, kind: str, message: str, xp: int = 0, **data) -> Event:
        event = Event(id=self._next("event"), at=now(), area=area, kind=kind, message=message, xp=xp, data=data)
        self.events.append(event)
        return event

    @staticmethod
    def _get(collection: dict, key: str, label: str):
        value = collection.get(key)
        if value is None:
            raise DomainError(404, f"{label} {key} not found")
        return value

    # ---------- unload ----------
    def schedule_truck(self) -> Truck:
        in_transit = sum(1 for t in self.trucks.values() if t.status == "in_transit")
        if in_transit >= MAX_IN_TRANSIT:
            raise DomainError(409, f"{MAX_IN_TRANSIT} trucks are already on the way.")
        truck = self._new_truck()
        items = sum(len(self.boxes[b].item_ids) for b in truck.box_ids)
        self._log("unload", "truck_scheduled",
                  f"{truck.id} from {truck.origin} is on the way with {len(truck.box_ids)} boxes ({items} items).",
                  truck=truck.id)
        return truck

    def check_in(self, truck_id: str) -> Truck:
        truck = self._get(self.trucks, truck_id, "Truck")
        if truck.status != "in_transit":
            raise DomainError(409, f"{truck.id} has already arrived.")
        busy = {t.door for t in self.trucks.values() if t.status == "at_door"}
        free = [d for d in range(1, DOORS + 1) if d not in busy]
        if not free:
            raise DomainError(409, f"All {DOORS} doors are busy. Unload a truck first.")
        truck.status, truck.door, truck.arrived_at = "at_door", free[0], now()
        self._log("unload", "truck_checked_in", f"{truck.id} checked in at door {truck.door}.",
                  XP["check_in"], truck=truck.id)
        return truck

    def unload(self, truck_id: str) -> Truck:
        truck = self._get(self.trucks, truck_id, "Truck")
        if truck.status != "at_door":
            raise DomainError(409, f"{truck.id} must be at a door before it can be unloaded.")
        for box_id in truck.box_ids:
            self.boxes[box_id].status = "staged"
        door = truck.door
        truck.status, truck.door, truck.unloaded_at = "unloaded", None, now()
        self._log("unload", "truck_unloaded",
                  f"Unloaded {len(truck.box_ids)} boxes from {truck.id} at door {door}.",
                  XP["unload"], truck=truck.id, boxes=len(truck.box_ids))
        return truck

    def distribute(self, box_id: str, station: int) -> Box:
        box = self._get(self.boxes, box_id, "Box")
        if box.status != "staged":
            raise DomainError(409, f"{box.id} is not waiting in staging.")
        if not 1 <= station <= STATIONS:
            raise DomainError(422, f"Choose a station from 1 to {STATIONS}.")
        box.status, box.station = "at_station", station
        self._log("unload", "box_distributed", f"{box.id} sent to process station {station}.",
                  XP["distribute"], box=box.id, station=station)
        return box

    def distribute_all(self) -> int:
        staged = [b for b in self.boxes.values() if b.status == "staged"]
        if not staged:
            raise DomainError(409, "No boxes are waiting in staging.")
        for box in staged:
            load = {s: 0 for s in range(1, STATIONS + 1)}
            for b in self.boxes.values():
                if b.status in ("at_station", "open") and b.station:
                    load[b.station] += 1
            self.distribute(box.id, min(load, key=lambda s: (load[s], s)))
        return len(staged)

    # ---------- process ----------
    def open_box(self, box_id: str) -> Box:
        box = self._get(self.boxes, box_id, "Box")
        if box.status != "at_station":
            raise DomainError(409, f"{box.id} is not waiting at a station.")
        busy = any(b.status == "open" and b.station == box.station for b in self.boxes.values())
        if busy:
            raise DomainError(409, f"Finish the open box at station {box.station} first.")
        box.status = "open"
        self._log("process", "box_opened",
                  f"Opened {box.id} at station {box.station}: {len(box.item_ids)} items inside.",
                  XP["open_box"], box=box.id, station=box.station)
        return box

    def route_item(self, item_id: str, destination: str) -> Item:
        item = self._get(self.items, item_id, "Item")
        if item.status != "in_box":
            raise DomainError(409, f"{item.name} has already been processed.")
        box = self.boxes[item.box_id]
        if box.status != "open":
            raise DomainError(409, f"Open {box.id} before processing its items.")

        if destination == "yellow_tote":
            if item.condition == "damaged":
                raise DomainError(422, f"{item.name} is damaged ({item.note.lower()}). Send it to liquidation.")
            tote = self.open_tote
            tote.item_ids.append(item.id)
            item.status, item.tote_id = "yellow_tote", tote.id
            self._log("process", "item_to_tote", f"{item.name} is clean and went into yellow tote {tote.id}.",
                      XP["route_correct"], item=item.id, destination="yellow_tote")
            if len(tote.item_ids) >= TOTE_CAPACITY:
                self._finish_tote(tote, "is full")
        elif destination == "liquidation":
            pallet = self.open_pallet
            pallet.item_ids.append(item.id)
            item.status, item.pallet_id = "liquidation", pallet.id
            xp = XP["route_correct"] if item.condition == "damaged" else XP["route_clean_to_liquidation"]
            reason = item.note.lower() if item.condition == "damaged" else "clean item, sent by choice"
            self._log("liquidation", "item_to_liquidation", f"{item.name} ({reason}) went to pallet {pallet.id}.",
                      xp, item=item.id, destination="liquidation")
        else:
            raise DomainError(422, "Destination must be yellow_tote or liquidation.")

        if all(self.items[i].status != "in_box" for i in box.item_ids):
            box.status = "done"
            self._log("process", "box_done", f"{box.id} is empty. Station {box.station} is free.",
                      XP["box_done"], box=box.id)
        return item

    def _finish_tote(self, tote: Tote, reason: str) -> None:
        tote.status = "full"
        self._log("tranship", "tote_full",
                  f"Yellow tote {tote.id} {reason} ({len(tote.item_ids)} items) and is staged for tranship.",
                  XP["tote_full"], tote=tote.id)
        self.open_tote = self._new_tote()

    def close_tote(self) -> Tote:
        tote = self.open_tote
        if not tote.item_ids:
            raise DomainError(409, "The yellow tote is empty.")
        self._finish_tote(tote, "was closed early")
        return tote

    # ---------- tranship ----------
    def load_tote(self, tote_id: str) -> Tote:
        tote = self._get(self.totes, tote_id, "Tote")
        if tote.status != "full":
            raise DomainError(409, f"Tote {tote.id} is not staged for tranship.")
        truck = self.open_outbound
        if len(truck.tote_ids) >= OUTBOUND_CAPACITY:
            raise DomainError(409, f"{truck.id} is full. Ship it first.")
        truck.tote_ids.append(tote.id)
        tote.status, tote.outbound_id = "loaded", truck.id
        self._log("tranship", "tote_loaded", f"Loaded yellow tote {tote.id} onto {truck.id}.",
                  XP["load_tote"], tote=tote.id, truck=truck.id)
        return tote

    def load_all_totes(self) -> int:
        staged = [t for t in self.totes.values() if t.status == "full"]
        if not staged:
            raise DomainError(409, "No full totes are waiting.")
        room = OUTBOUND_CAPACITY - len(self.open_outbound.tote_ids)
        if room <= 0:
            raise DomainError(409, f"{self.open_outbound.id} is full. Ship it first.")
        for tote in staged[:room]:
            self.load_tote(tote.id)
        return min(room, len(staged))

    def ship_outbound(self) -> OutboundTruck:
        truck = self.open_outbound
        if not truck.tote_ids:
            raise DomainError(409, "Load at least one tote before shipping.")
        units = sum(len(self.totes[t].item_ids) for t in truck.tote_ids)
        for tote_id in truck.tote_ids:
            self.totes[tote_id].status = "shipped"
        truck.status, truck.shipped_at = "shipped", now()
        self._log("tranship", "outbound_shipped",
                  f"{truck.id} shipped {len(truck.tote_ids)} totes ({units} units) to be sold.",
                  XP["ship_outbound"], truck=truck.id, units=units)
        self.open_outbound = self._new_outbound()
        return truck

    # ---------- liquidation ----------
    def ship_liquidation(self) -> Pallet:
        pallet = self.open_pallet
        if not pallet.item_ids:
            raise DomainError(409, "The liquidation pallet is empty.")
        pallet.status, pallet.shipped_at = "shipped", now()
        self._log("liquidation", "pallet_shipped",
                  f"Pallet {pallet.id} with {len(pallet.item_ids)} items sent to liquidation.",
                  XP["ship_liquidation"], pallet=pallet.id, units=len(pallet.item_ids))
        self.open_pallet = self._new_pallet()
        return pallet

    # ---------- read model ----------
    @property
    def xp(self) -> int:
        return sum(e.xp for e in self.events)

    def level(self) -> dict:
        xp = self.xp
        index = max(i for i, (floor, _) in enumerate(LEVELS) if xp >= floor)
        nxt = LEVELS[index + 1] if index + 1 < len(LEVELS) else None
        return {
            "number": index + 1,
            "name": LEVELS[index][1],
            "floor_xp": LEVELS[index][0],
            "next_xp": nxt[0] if nxt else None,
            "next_name": nxt[1] if nxt else None,
        }

    def summary(self) -> dict:
        trucks, boxes, items, totes = (list(c.values()) for c in (self.trucks, self.boxes, self.items, self.totes))
        inbound_boxes = [b for b in boxes if b.status == "on_truck"]
        return {
            "trucks_in_transit": sum(t.status == "in_transit" for t in trucks),
            "trucks_at_door": sum(t.status == "at_door" for t in trucks),
            "boxes_inbound": len(inbound_boxes),
            "items_inbound": sum(len(b.item_ids) for b in inbound_boxes),
            "boxes_staged": sum(b.status == "staged" for b in boxes),
            "boxes_at_stations": sum(b.status in ("at_station", "open") for b in boxes),
            "items_processed": sum(i.status != "in_box" for i in items),
            "sellable_units": sum(len(t.item_ids) for t in totes if t.status in ("open", "full", "loaded")),
            "totes_staged": sum(t.status == "full" for t in totes),
            "liquidation_units": len(self.open_pallet.item_ids),
            "units_shipped": sum(len(t.item_ids) for t in totes if t.status == "shipped"),
            "units_liquidated": sum(len(p.item_ids) for p in self.pallets.values() if p.status == "shipped"),
        }

    def snapshot(self) -> dict:
        return {
            "config": {"doors": DOORS, "stations": STATIONS, "tote_capacity": TOTE_CAPACITY,
                       "outbound_capacity": OUTBOUND_CAPACITY},
            "trucks": [asdict(t) for t in self.trucks.values()],
            "boxes": [asdict(b) for b in self.boxes.values()],
            "items": [asdict(i) for i in self.items.values()],
            "totes": [asdict(t) for t in self.totes.values()],
            "outbound": [asdict(o) for o in self.outbound.values()],
            "pallets": [asdict(p) for p in self.pallets.values()],
            "open_tote": self.open_tote.id,
            "open_outbound": self.open_outbound.id,
            "open_pallet": self.open_pallet.id,
            "events": [asdict(e) for e in self.events[-500:]],
            "summary": self.summary(),
            "player": {"xp": self.xp, "level": self.level()},
        }
