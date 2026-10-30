import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.warehouse import OUTBOUND_CAPACITY, TOTE_CAPACITY, DomainError, Warehouse

client = TestClient(app)


def setup_function():
    client.post("/api/reset")


# ---------- helpers ----------
def first(items, **match):
    return next(i for i in items if all(i[k] == v for k, v in match.items()))


def unload_first_truck(wh: Warehouse):
    truck = next(t for t in wh.trucks.values() if t.status == "at_door")
    wh.unload(truck.id)
    return truck


def open_one_box(wh: Warehouse):
    unload_first_truck(wh)
    wh.distribute_all()
    box = next(b for b in wh.boxes.values() if b.status == "at_station")
    wh.open_box(box.id)
    return box


# ---------- API ----------
def test_root_and_health():
    assert client.get("/").json()["message"] == "Welcome to StockFlow API"
    assert client.get("/health").json() == {"status": "ok"}


def test_state_starts_with_one_truck_at_a_door():
    state = client.get("/api/state").json()
    assert state["summary"]["trucks_at_door"] == 1
    assert state["summary"]["trucks_in_transit"] == 2
    assert state["player"]["level"]["name"] == "Rookie"
    assert state["events"][0]["kind"] == "shift_started"


def test_unload_stages_boxes_and_frees_the_door():
    state = client.get("/api/state").json()
    truck = first(state["trucks"], status="at_door")
    state = client.post(f"/api/trucks/{truck['id']}/unload").json()
    assert first(state["trucks"], id=truck["id"])["status"] == "unloaded"
    assert state["summary"]["boxes_staged"] == len(truck["box_ids"])
    assert state["summary"]["trucks_at_door"] == 0
    assert state["events"][-1]["kind"] == "truck_unloaded"


def test_cannot_unload_a_truck_still_in_transit():
    state = client.get("/api/state").json()
    truck = first(state["trucks"], status="in_transit")
    response = client.post(f"/api/trucks/{truck['id']}/unload")
    assert response.status_code == 409


def test_damaged_item_cannot_go_into_a_yellow_tote_over_http():
    state = client.get("/api/state").json()
    truck = first(state["trucks"], status="at_door")
    client.post(f"/api/trucks/{truck['id']}/unload")
    state = client.post("/api/boxes/distribute-all").json()
    damaged = next(i for i in state["items"] if i["condition"] == "damaged" and i["box_id"] in truck["box_ids"])
    client.post(f"/api/boxes/{damaged['box_id']}/open")
    response = client.post(f"/api/items/{damaged['id']}/route", json={"destination": "yellow_tote"})
    assert response.status_code == 422
    ok = client.post(f"/api/items/{damaged['id']}/route", json={"destination": "liquidation"})
    assert ok.status_code == 200
    assert ok.json()["summary"]["liquidation_units"] == 1


def test_unknown_ids_are_404():
    assert client.post("/api/trucks/TRK-0/unload").status_code == 404
    assert client.post("/api/items/IT-0/route", json={"destination": "liquidation"}).status_code == 404


def test_invalid_destination_is_rejected():
    assert client.post("/api/items/IT-1001/route", json={"destination": "trash"}).status_code == 422


# ---------- domain ----------
def test_check_in_uses_free_doors_and_respects_capacity():
    wh = Warehouse.seeded(seed=1)
    for _ in range(3):
        wh.schedule_truck()
    in_transit = [t for t in wh.trucks.values() if t.status == "in_transit"]
    doors = [wh.check_in(t.id).door for t in in_transit[:3]]
    assert doors == [2, 3, 4]
    with pytest.raises(DomainError) as err:
        wh.check_in(in_transit[3].id)
    assert err.value.status == 409


def test_distribute_all_balances_stations():
    wh = Warehouse.seeded(seed=2)
    unload_first_truck(wh)
    count = wh.distribute_all()
    per_station = [sum(b.station == s for b in wh.boxes.values() if b.status == "at_station") for s in range(1, 5)]
    assert sum(per_station) == count
    assert max(per_station) - min(per_station) <= 1


def test_one_open_box_per_station():
    wh = Warehouse.seeded(seed=3)
    unload_first_truck(wh)
    staged = [b for b in wh.boxes.values() if b.status == "staged"]
    wh.distribute(staged[0].id, 1)
    wh.distribute(staged[1].id, 1)
    wh.open_box(staged[0].id)
    with pytest.raises(DomainError):
        wh.open_box(staged[1].id)


def test_items_must_be_in_an_open_box():
    wh = Warehouse.seeded(seed=4)
    unload_first_truck(wh)
    item = next(iter(wh.items.values()))
    with pytest.raises(DomainError) as err:
        wh.route_item(item.id, "liquidation")
    assert err.value.status == 409


def test_processing_every_item_empties_the_box():
    wh = Warehouse.seeded(seed=5)
    box = open_one_box(wh)
    for item_id in box.item_ids:
        item = wh.items[item_id]
        wh.route_item(item_id, "yellow_tote" if item.condition == "clean" else "liquidation")
    assert box.status == "done"
    assert wh.summary()["items_processed"] == len(box.item_ids)


def test_tote_fills_at_capacity_and_a_new_one_opens():
    wh = Warehouse.seeded(seed=6)
    first_tote = wh.open_tote
    clean_routed = 0
    while first_tote.status == "open":
        wh.schedule_truck()
        for truck in [t for t in wh.trucks.values() if t.status == "in_transit"]:
            try:
                wh.check_in(truck.id)
            except DomainError:
                break
        for truck in [t for t in wh.trucks.values() if t.status == "at_door"]:
            wh.unload(truck.id)
        wh.distribute_all()
        for box in [b for b in wh.boxes.values() if b.status == "at_station"]:
            try:
                wh.open_box(box.id)
            except DomainError:
                continue
            for item_id in box.item_ids:
                if wh.items[item_id].condition == "clean" and first_tote.status == "open":
                    wh.route_item(item_id, "yellow_tote")
                    clean_routed += 1
                else:
                    wh.route_item(item_id, "liquidation")
    assert clean_routed == TOTE_CAPACITY
    assert first_tote.status == "full"
    assert wh.open_tote is not first_tote and wh.open_tote.status == "open"
    assert any(e.kind == "tote_full" for e in wh.events)


def test_tranship_load_and_ship():
    wh = Warehouse.seeded(seed=7)
    box = open_one_box(wh)
    clean = next(i for i in box.item_ids if wh.items[i].condition == "clean")
    wh.route_item(clean, "yellow_tote")
    tote = wh.close_tote()
    with pytest.raises(DomainError):
        wh.ship_outbound()  # nothing loaded yet
    wh.load_tote(tote.id)
    truck = wh.ship_outbound()
    assert truck.status == "shipped" and tote.status == "shipped"
    assert wh.summary()["units_shipped"] == 1
    assert wh.open_outbound.status == "loading" and not wh.open_outbound.tote_ids


def test_outbound_truck_has_a_tote_limit():
    wh = Warehouse(seed=9)
    for n in range(OUTBOUND_CAPACITY + 1):
        tote = wh.open_tote
        tote.item_ids.append(f"fake-{n}")
        wh.close_tote()
    loaded = wh.load_all_totes()
    assert loaded == OUTBOUND_CAPACITY
    with pytest.raises(DomainError):
        wh.load_all_totes()


def test_liquidation_ships_and_starts_a_new_pallet():
    wh = Warehouse.seeded(seed=8)
    box = open_one_box(wh)
    wh.route_item(box.item_ids[0], "liquidation")
    pallet = wh.ship_liquidation()
    assert pallet.status == "shipped"
    assert wh.open_pallet is not pallet
    with pytest.raises(DomainError):
        wh.ship_liquidation()


def test_xp_and_levels_follow_events():
    wh = Warehouse.seeded(seed=10)
    assert wh.xp == 0
    unload_first_truck(wh)
    assert wh.xp == 20
    wh.events.append(wh.events[-1].__class__(id=999, at="", area="shift", kind="bonus", message="", xp=200))
    assert wh.level()["name"] == "Sorter"
