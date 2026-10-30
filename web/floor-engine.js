/* StockFlow floor engine for the browser: a port of app/warehouse.py and the /api routes in app/main.py.
   Used by the static build (public/index.html) so the app runs on static hosting such as Vercel.
   Same rules and responses as the server; state lives in the page and resets on reload. */
(() => {
  const DOORS = 4, STATIONS = 4, TOTE_CAPACITY = 8, OUTBOUND_CAPACITY = 10, MAX_IN_TRANSIT = 6;
  const ORGS = ["Northgate Retail", "Bluepeak Outlet", "Harbor Supply Co.", "Summit Home Goods", "Riverside Electronics"];
  const CATALOG = [["Wireless Mouse", "Electronics"], ["Bluetooth Headphones", "Electronics"], ["USB-C Cable", "Electronics"], ["Smart Watch", "Electronics"], ["Coffee Maker", "Kitchen"], ["Cookware Set", "Kitchen"], ["Desk Lamp", "Home"], ["Throw Pillow", "Home"], ["Yoga Mat", "Sports"], ["Water Bottle", "Sports"], ["Phone Case", "Accessories"], ["Kids' Sneakers", "Apparel"]];
  const CLEAN = ["Sealed in original packaging", "Opened, like new", "Minor box wear, item perfect", "Tested and working"];
  const DAMAGE = { Electronics: ["Cracked casing", "Won't power on", "Water damage", "Frayed cable"], Kitchen: ["Cracked glass", "Dented body", "Missing parts"], Home: ["Broken base", "Torn fabric", "Stained"], Sports: ["Torn surface", "Punctured", "Dented"], Accessories: ["Cracked", "Scratched and scuffed"], Apparel: ["Torn fabric", "Stained", "Missing one shoe"] };
  const XP = { check_in: 5, unload: 20, distribute: 5, open_box: 5, route_correct: 10, route_clean_to_liquidation: 2, box_done: 5, tote_full: 15, load_tote: 5, ship_outbound: 50, ship_liquidation: 30 };
  const LEVELS = [[0, "Rookie"], [150, "Sorter"], [400, "Processor"], [800, "Problem Solver"], [1400, "Storm Chaser"], [2200, "Thunder Legend"]];

  class DomainError extends Error { constructor(status, message) { super(message); this.status = status; } }
  const now = () => new Date().toISOString();
  const clone = o => JSON.parse(JSON.stringify(o));

  class Warehouse {
    constructor(seed = 8) {
      let s = seed >>> 0;
      this.random = () => { s += 0x6D2B79F5; let t = s; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
      this.trucks = {}; this.boxes = {}; this.items = {}; this.totes = {}; this.outbound = {}; this.pallets = {}; this.events = [];
      this.seq = { truck: 1000, box: 20000, item: 1000, tote: 100, out: 500, pallet: 300, event: 0 };
      this.openTote = this.newTote(); this.openOutbound = this.newOutbound(); this.openPallet = this.newPallet();
    }
    static seeded(seed = 8) {
      const wh = new Warehouse(seed);
      wh.log("shift", "shift_started", "Shift started at IND8. Home of the Thunder.");
      const first = wh.newTruck(); first.status = "at_door"; first.door = 1; first.arrived_at = now();
      wh.newTruck(); wh.newTruck();
      return wh;
    }
    next(k) { return ++this.seq[k]; }
    int(a, b) { return a + Math.floor(this.random() * (b - a + 1)); }
    pick(arr) { return arr[Math.floor(this.random() * arr.length)]; }
    newTruck() {
      const t = { id: `TRK-${this.next("truck")}`, origin: this.pick(ORGS), status: "in_transit", eta_minutes: this.int(10, 45), box_ids: [], door: null, arrived_at: null, unloaded_at: null };
      const nb = this.int(3, 6);
      for (let b = 0; b < nb; b++) {
        const box = { id: `BX-${this.next("box")}`, truck_id: t.id, origin: t.origin, status: "on_truck", item_ids: [], station: null };
        const ni = this.int(2, 5);
        for (let i = 0; i < ni; i++) {
          const [name, category] = this.pick(CATALOG), damaged = this.random() < 0.25;
          const item = { id: `IT-${this.next("item")}`, box_id: box.id, name, category, condition: damaged ? "damaged" : "clean", note: this.pick(damaged ? DAMAGE[category] : CLEAN), status: "in_box", tote_id: null, pallet_id: null };
          this.items[item.id] = item; box.item_ids.push(item.id);
        }
        this.boxes[box.id] = box; t.box_ids.push(box.id);
      }
      this.trucks[t.id] = t; return t;
    }
    newTote() { const t = { id: `YT-${this.next("tote")}`, status: "open", item_ids: [], outbound_id: null }; this.totes[t.id] = t; return t; }
    newOutbound() { const o = { id: `OUT-${this.next("out")}`, destination: "Resale marketplace", status: "loading", tote_ids: [], shipped_at: null }; this.outbound[o.id] = o; return o; }
    newPallet() { const p = { id: `LQ-${this.next("pallet")}`, partner: "Liquidation partner", status: "open", item_ids: [], shipped_at: null }; this.pallets[p.id] = p; return p; }
    log(area, kind, message, xp = 0, data = {}) { this.events.push({ id: this.next("event"), at: now(), area, kind, message, xp, data }); }
    get(col, key, label) { const v = this[col][key]; if (!v) throw new DomainError(404, `${label} ${key} not found`); return v; }

    scheduleTruck() {
      const n = Object.values(this.trucks).filter(t => t.status === "in_transit").length;
      if (n >= MAX_IN_TRANSIT) throw new DomainError(409, `${MAX_IN_TRANSIT} trucks are already on the way.`);
      const t = this.newTruck(), items = t.box_ids.reduce((s, b) => s + this.boxes[b].item_ids.length, 0);
      this.log("unload", "truck_scheduled", `${t.id} from ${t.origin} is on the way with ${t.box_ids.length} boxes (${items} items).`, 0, { truck: t.id });
    }
    checkIn(id) {
      const t = this.get("trucks", id, "Truck");
      if (t.status !== "in_transit") throw new DomainError(409, `${t.id} has already arrived.`);
      const busy = new Set(Object.values(this.trucks).filter(x => x.status === "at_door").map(x => x.door));
      const free = [1, 2, 3, 4].filter(d => !busy.has(d));
      if (!free.length) throw new DomainError(409, `All ${DOORS} doors are busy. Unload a truck first.`);
      t.status = "at_door"; t.door = free[0]; t.arrived_at = now();
      this.log("unload", "truck_checked_in", `${t.id} checked in at door ${t.door}.`, XP.check_in, { truck: t.id });
    }
    unload(id) {
      const t = this.get("trucks", id, "Truck");
      if (t.status !== "at_door") throw new DomainError(409, `${t.id} must be at a door before it can be unloaded.`);
      t.box_ids.forEach(b => this.boxes[b].status = "staged");
      const door = t.door; t.status = "unloaded"; t.door = null; t.unloaded_at = now();
      this.log("unload", "truck_unloaded", `Unloaded ${t.box_ids.length} boxes from ${t.id} at door ${door}.`, XP.unload, { truck: t.id, boxes: t.box_ids.length });
    }
    distribute(id, station) {
      const b = this.get("boxes", id, "Box");
      if (b.status !== "staged") throw new DomainError(409, `${b.id} is not waiting in staging.`);
      if (!(station >= 1 && station <= STATIONS)) throw new DomainError(422, `Choose a station from 1 to ${STATIONS}.`);
      b.status = "at_station"; b.station = station;
      this.log("unload", "box_distributed", `${b.id} sent to process station ${station}.`, XP.distribute, { box: b.id, station });
    }
    distributeAll() {
      const staged = Object.values(this.boxes).filter(b => b.status === "staged");
      if (!staged.length) throw new DomainError(409, "No boxes are waiting in staging.");
      for (const box of staged) {
        const load = { 1: 0, 2: 0, 3: 0, 4: 0 };
        Object.values(this.boxes).forEach(b => { if ((b.status === "at_station" || b.status === "open") && b.station) load[b.station]++; });
        const st = [1, 2, 3, 4].sort((a, c) => load[a] - load[c] || a - c)[0];
        this.distribute(box.id, st);
      }
    }
    openBox(id) {
      const b = this.get("boxes", id, "Box");
      if (b.status !== "at_station") throw new DomainError(409, `${b.id} is not waiting at a station.`);
      if (Object.values(this.boxes).some(x => x.status === "open" && x.station === b.station)) throw new DomainError(409, `Finish the open box at station ${b.station} first.`);
      b.status = "open";
      this.log("process", "box_opened", `Opened ${b.id} at station ${b.station}: ${b.item_ids.length} items inside.`, XP.open_box, { box: b.id, station: b.station });
    }
    routeItem(id, dest) {
      const item = this.get("items", id, "Item");
      if (item.status !== "in_box") throw new DomainError(409, `${item.name} has already been processed.`);
      const box = this.boxes[item.box_id];
      if (box.status !== "open") throw new DomainError(409, `Open ${box.id} before processing its items.`);
      if (dest === "yellow_tote") {
        if (item.condition === "damaged") throw new DomainError(422, `${item.name} is damaged (${item.note.toLowerCase()}). Send it to liquidation.`);
        const tote = this.openTote; tote.item_ids.push(item.id); item.status = "yellow_tote"; item.tote_id = tote.id;
        this.log("process", "item_to_tote", `${item.name} is clean and went into yellow tote ${tote.id}.`, XP.route_correct, { item: item.id, destination: "yellow_tote" });
        if (tote.item_ids.length >= TOTE_CAPACITY) this.finishTote(tote, "is full");
      } else if (dest === "liquidation") {
        const p = this.openPallet; p.item_ids.push(item.id); item.status = "liquidation"; item.pallet_id = p.id;
        const xp = item.condition === "damaged" ? XP.route_correct : XP.route_clean_to_liquidation;
        const reason = item.condition === "damaged" ? item.note.toLowerCase() : "clean item, sent by choice";
        this.log("liquidation", "item_to_liquidation", `${item.name} (${reason}) went to pallet ${p.id}.`, xp, { item: item.id, destination: "liquidation" });
      } else throw new DomainError(422, "Destination must be yellow_tote or liquidation.");
      if (box.item_ids.every(i => this.items[i].status !== "in_box")) {
        box.status = "done";
        this.log("process", "box_done", `${box.id} is empty. Station ${box.station} is free.`, XP.box_done, { box: box.id });
      }
    }
    finishTote(tote, reason) {
      tote.status = "full";
      this.log("tranship", "tote_full", `Yellow tote ${tote.id} ${reason} (${tote.item_ids.length} items) and is staged for tranship.`, XP.tote_full, { tote: tote.id });
      this.openTote = this.newTote();
    }
    closeTote() { if (!this.openTote.item_ids.length) throw new DomainError(409, "The yellow tote is empty."); this.finishTote(this.openTote, "was closed early"); }
    loadTote(id) {
      const tote = this.get("totes", id, "Tote");
      if (tote.status !== "full") throw new DomainError(409, `Tote ${tote.id} is not staged for tranship.`);
      const t = this.openOutbound;
      if (t.tote_ids.length >= OUTBOUND_CAPACITY) throw new DomainError(409, `${t.id} is full. Ship it first.`);
      t.tote_ids.push(tote.id); tote.status = "loaded"; tote.outbound_id = t.id;
      this.log("tranship", "tote_loaded", `Loaded yellow tote ${tote.id} onto ${t.id}.`, XP.load_tote, { tote: tote.id, truck: t.id });
    }
    loadAll() {
      const staged = Object.values(this.totes).filter(t => t.status === "full");
      if (!staged.length) throw new DomainError(409, "No full totes are waiting.");
      const room = OUTBOUND_CAPACITY - this.openOutbound.tote_ids.length;
      if (room <= 0) throw new DomainError(409, `${this.openOutbound.id} is full. Ship it first.`);
      staged.slice(0, room).forEach(t => this.loadTote(t.id));
    }
    shipOutbound() {
      const t = this.openOutbound;
      if (!t.tote_ids.length) throw new DomainError(409, "Load at least one tote before shipping.");
      const units = t.tote_ids.reduce((s, id) => s + this.totes[id].item_ids.length, 0);
      t.tote_ids.forEach(id => this.totes[id].status = "shipped");
      t.status = "shipped"; t.shipped_at = now();
      this.log("tranship", "outbound_shipped", `${t.id} shipped ${t.tote_ids.length} totes (${units} units) to be sold.`, XP.ship_outbound, { truck: t.id, units });
      this.openOutbound = this.newOutbound();
    }
    shipLiquidation() {
      const p = this.openPallet;
      if (!p.item_ids.length) throw new DomainError(409, "The liquidation pallet is empty.");
      p.status = "shipped"; p.shipped_at = now();
      this.log("liquidation", "pallet_shipped", `Pallet ${p.id} with ${p.item_ids.length} items sent to liquidation.`, XP.ship_liquidation, { pallet: p.id, units: p.item_ids.length });
      this.openPallet = this.newPallet();
    }
    get xp() { return this.events.reduce((s, e) => s + e.xp, 0); }
    level() {
      const xp = this.xp; let idx = 0; LEVELS.forEach(([f], i) => { if (xp >= f) idx = i; });
      const nx = LEVELS[idx + 1];
      return { number: idx + 1, name: LEVELS[idx][1], floor_xp: LEVELS[idx][0], next_xp: nx ? nx[0] : null, next_name: nx ? nx[1] : null };
    }
    summary() {
      const T = Object.values(this.trucks), B = Object.values(this.boxes), I = Object.values(this.items), TT = Object.values(this.totes);
      const inb = B.filter(b => b.status === "on_truck"), len = a => a.item_ids.length;
      return {
        trucks_in_transit: T.filter(t => t.status === "in_transit").length,
        trucks_at_door: T.filter(t => t.status === "at_door").length,
        boxes_inbound: inb.length, items_inbound: inb.reduce((s, b) => s + len(b), 0),
        boxes_staged: B.filter(b => b.status === "staged").length,
        boxes_at_stations: B.filter(b => b.status === "at_station" || b.status === "open").length,
        items_processed: I.filter(i => i.status !== "in_box").length,
        sellable_units: TT.filter(t => ["open", "full", "loaded"].includes(t.status)).reduce((s, t) => s + len(t), 0),
        totes_staged: TT.filter(t => t.status === "full").length,
        liquidation_units: len(this.openPallet),
        units_shipped: TT.filter(t => t.status === "shipped").reduce((s, t) => s + len(t), 0),
        units_liquidated: Object.values(this.pallets).filter(p => p.status === "shipped").reduce((s, p) => s + len(p), 0),
      };
    }
    snapshot() {
      return clone({
        config: { doors: DOORS, stations: STATIONS, tote_capacity: TOTE_CAPACITY, outbound_capacity: OUTBOUND_CAPACITY },
        trucks: Object.values(this.trucks), boxes: Object.values(this.boxes), items: Object.values(this.items),
        totes: Object.values(this.totes), outbound: Object.values(this.outbound), pallets: Object.values(this.pallets),
        open_tote: this.openTote.id, open_outbound: this.openOutbound.id, open_pallet: this.openPallet.id,
        events: this.events.slice(-500), summary: this.summary(), player: { xp: this.xp, level: this.level() },
      });
    }
  }

  let wh = Warehouse.seeded(Date.now() % 100000);
  const res = (status, body) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  const routes = [
    ["GET", /^\/api\/state$/, () => null],
    ["POST", /^\/api\/trucks$/, () => wh.scheduleTruck()],
    ["POST", /^\/api\/trucks\/([^/]+)\/check-in$/, m => wh.checkIn(m[1])],
    ["POST", /^\/api\/trucks\/([^/]+)\/unload$/, m => wh.unload(m[1])],
    ["POST", /^\/api\/boxes\/distribute-all$/, () => wh.distributeAll()],
    ["POST", /^\/api\/boxes\/([^/]+)\/distribute$/, (m, b) => wh.distribute(m[1], Number(b.station))],
    ["POST", /^\/api\/boxes\/([^/]+)\/open$/, m => wh.openBox(m[1])],
    ["POST", /^\/api\/items\/([^/]+)\/route$/, (m, b) => wh.routeItem(m[1], b.destination)],
    ["POST", /^\/api\/totes\/close$/, () => wh.closeTote()],
    ["POST", /^\/api\/totes\/load-all$/, () => wh.loadAll()],
    ["POST", /^\/api\/totes\/([^/]+)\/load$/, m => wh.loadTote(m[1])],
    ["POST", /^\/api\/outbound\/ship$/, () => wh.shipOutbound()],
    ["POST", /^\/api\/liquidation\/ship$/, () => wh.shipLiquidation()],
    ["POST", /^\/api\/reset$/, () => { wh = Warehouse.seeded(Date.now() % 100000); }],
  ];
  window.fetch = async (path, opts = {}) => {
    const method = (opts.method || "GET").toUpperCase(), body = opts.body ? JSON.parse(opts.body) : {};
    for (const [mth, re, fn] of routes) {
      const m = path.match(re);
      if (m && mth === method) {
        try { fn(m, body); return res(200, wh.snapshot()); }
        catch (e) { if (e instanceof DomainError) return res(e.status, { detail: e.message }); throw e; }
      }
    }
    return res(404, { detail: "Not found" });
  };
})();
