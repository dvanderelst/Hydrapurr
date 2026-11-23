# HydraPurr lick-sensor — circuit investigation notes

Investigation of why the Board 2 lick detector sometimes registers a "lick"
when the cat touches only the metal plate (not the water bowl), and what to
change. Simulated in LTspice (`MyLickSensor.asc`) and cross-checked with
ngspice. The detector is the 2-transistor front end on Schematic 2.

## How the detector works (one line)
The cat completes a circuit from the **water bowl (V_BATT)** to the **metal
plate (FLOOR)**. FLOOR feeds the base of a **Darlington pair** (Q1→Q2, gain
≈ β₁·β₂ ≈ tens of thousands) through R6 (10 MΩ). When enough current flows in,
the Darlington turns on, lights the opto LED, and the optocoupler pulls the
main-board line low. So it's really a *single-ended, ultra-high-gain current
amplifier* — electrically the classic hobby "touch switch" — not a true
bowl-to-plate conductivity bridge.

## Model component glossary (LTspice: MyLickSensor.asc)
- **Mains** — current source modelling mains hum picked up *through the cat's
  body* and injected at the plate. `SINE(0 amp 60)`: 0 offset, `amp` peak
  current, 60 Hz (use 50 in Europe). ~4.5 µA is a realistic body-coupling
  estimate (≈100 pF × 170 V × 2π·60). Set `amp=0` to turn it off.
- **RCat** — the cat's resistance. Open (≈1 G) when not licking; drops to
  ~300 k during a lick. Model a lick dynamically as a time-varying resistor,
  e.g. `R=if((time>1)&(time<1.5),300k,1G)` (one lick) or
  `R=if(sin(2*pi*5*time)>0,300k,1G)` (5 Hz train). A 1 G "off" value matters —
  anything ≤ ~20 MΩ already trips the detector.
- **detection** — the voltage the Feather reads on its **ADC** pin (A1).
  Active-LOW: firmware treats `< lick_threshold` (2.0 V) as contact. ~3 V idle,
  ~0 V during a lick.
- **OPT (sensor board, Schematic 2 OPT1)** — 0.1 µF cap from FLOOR to GND. The
  one I did **not** populate ("optional"). Model its absence with ~0.1 pF.
  **This is the component that matters** (see findings).
- **Pulse** — a one-shot current pulse at the plate, meant to model a brief
  static-discharge / momentary-contact transient. Currently amplitude 0 (off);
  it was a what-if probe and isn't needed for the main results.
- **C1 (main board, Schematic 1 OPT1)** — 0.1 µF on the ADC line, with R7 = 1 kΩ
  pull-up. Different cap from the sensor-board OPT1 (same designator on a
  different sheet — easy to confuse).

### Supply-coupling additions (model the isolated-island problem, finding 7)
The sensor is a **floating, battery-powered island** isolated from the main
board by the optocoupler `U1`. Two separate ground nets capture this:
- **`gbat`** — the sensor-board ground (9 V battery negative). The whole
  detector front-end (R6/R2/Q1/Q2/OPT, the `Mains`/`Pulse` sources) references
  this. It is *floating* — only the opto LED and the coupling cap touch it.
- **`0`** — the stable earth/room reference. The cat couples to this.
- **`main_ground`** — the main (Feather) board ground, which the cheap supply
  wobbles relative to earth.

New parts:
- **V2** — the supply wobble. `SINE(0 170 60)` from `0` to `main_ground`. 170 =
  peak of 120 V RMS (US); use `SINE(0 325 50)` for 230 V Europe. It is the *full
  mains voltage* behind the (folded-in) Y-cap — an ideal source whose current is
  throttled entirely by `C2`. Set amp=0 for a battery/grounded supply (quiet).
- **C2 (`Cbar`)** — cross-barrier coupling, `gbat`↔`main_ground`. ~3 pF nominal
  (10 cm jumpers + opto input-output C + 2 cm board gap). Swept 1–20 pF via
  `.step param Cbar`. This single cap is the bottleneck that limits the
  supply-injected current; it's the knob the real layout must keep small.
- **Rleak** — 1 G, `gbat`↔`main_ground`. Physically the isolation/leakage
  resistance; in the model its real job is to give the floating island a **DC
  path** (without it: "node gbat has no DC path to ground"). Negligible at 60 Hz.
- **Rpaw / ccat / catbody** — plate-only-touch model. `Rpaw` (~1 MΩ) ties the
  cat body (`catbody`) to the plate (`floor`); `ccat` (~100 pF) ties `catbody`
  to earth (`0`). This is what pins `floor` toward earth while `C2` drags `gbat`
  toward the wobbling `main_ground` — the differential that trips the detector.
  (Note: `Rpaw` sits in series *before* `floor`, so a real lick via `RCat` flows
  through `Rpaw`+`RCat` — fine for the false-trigger study, watch it for
  real-lick sensitivity.)

## Key findings

### 1. The detector is wildly over-sensitive
It trips at only **~0.28 µA** of DC current into the plate ≈ a **~20 MΩ**
bowl-to-plate leak (at the current R6=R2=10 MΩ). A real lick is ~100 k–1 MΩ, so
there is **no threshold separating a real drink from faint leakage** (moisture
film, condensation, a damp paw, partial contact). That's the root cause of
plate-only false triggers.

### 2. It's the plate side that misfires, and that's expected
FLOOR is the high-impedance amplifier input; V_BATT is a low-impedance supply.
Touching the plate injects stray current straight into the ultra-high-gain
node; touching the bowl alone does nothing. Matches the observed symptom.

### 3. The "optional" sensor cap (OPT1) is the dominant knob — but it's a trap
- **OPT1 absent (~0.1 pF):** the plate is a bare 10 MΩ antenna → mains hum and
  static swing `detection` full-rail at 50/60 Hz → **false licks**. (This is the
  state the board has been running in.)
- **OPT1 = 0.1 µF:** mains is shunted (no false trigger), BUT `detection` now
  **latches low for ~2 s after every lick** (recovery time
  `τ = C·(R6+R2) = 0.1 µF·20 MΩ ≈ 2 s`), and it even *misses* a weak (1 MΩ)
  lick because the cap can't charge through it in a short lick.

So neither populated nor unpopulated 0.1 µF is acceptable.

### 4. Why the ~2 s latch breaks lick counting (firmware link)
Firmware reads the ADC, calls a contact `< 2.0 V`, and counts a **valid lick
only if the contact lasts 50–250 ms** (`min_lick_ms`/`max_lick_ms`), needing
**≥3 licks** for a bout (`BoutDetection.py`, `Settings.py`). A 2 s latch looks
like **one contact > 250 ms → rejected → no bout ever forms**. So the board can
only count licks with OPT1 *unpopulated* — exactly the state that lets mains
hum through. The firmware's 50–250 ms window throws out clean 8 ms (60 Hz)
ripple, but it **cannot** distinguish a cat's paw resting on the plate for
50–250 ms from a real lick.

### 5. The main-board cap can't help
Main-board OPT1/C1 (0.1 µF) with the R7 = 1 kΩ pull-up gives
`τ = 1 kΩ·0.1 µF = 0.1 ms` → corner ≈ 1.6 kHz, far above 60 Hz. Even populated
it does **not** filter the mains oscillation. (To filter 60 Hz there you'd need
~2.6 µF.)

### 6. Swapping the bowl/plate leads doesn't fix it
Putting FLOOR on the bowl and V_BATT on the plate is electrically equivalent
for real licks (the trigger current flows in the same direction, same
magnitude; gain/threshold/dynamics unchanged). The water's series resistance is
negligible (~kΩ vs the 10 MΩ input). The *only* real effect is that the
noise-sensitive "antenna" is whichever electrode is on FLOOR — so swapping moves
false-triggering from "touch the plate" to "touch the water". Likely a net
negative: the water is a large, environment-coupled conductor, a messier place
for the high-Z node than a clean isolated plate. Doesn't address the root
over-sensitivity.

### 7. Supply-dependent false triggers — but the sensor is *isolated*, so the path is subtle
**Observation:** the false-trigger rate depends on **which supply powers the
Feather** — cheap mains→5 V wall-warts misfire where a laptop/battery is quiet.
That smells like a *conducted* (not radiated) mechanism tied to the supply.

**The key correction (from reading the real schematic, EasyEDA Schematic 2):**
the sensor front-end is on a **floating, battery-powered island** (its own 9 V
`BAT1` → `GND_BATT`), galvanically **isolated from the Feather by the
optocoupler `U1`**. The detector's reference is the *battery*, not the
Feather/main-board ground. So an earlier idea — "the supply wobbles the
detector's ground" — is **wrong**: the opto breaks exactly that path. The two
grounds are not connected.

**Why a supply can still matter (it has to cross the isolation barrier):**
- The supply mechanism is real: a cheap 2-prong SMPS has a **Y-capacitor**
  bridging mains to its DC output, so the *Feather* ground floats at ~mains
  voltage, 50/60 Hz, relative to earth ("tingle off a 2-prong charger").
- But that wobble can only reach the floating sensor island through **stray
  capacitance across the barrier**: opto input-output C (~0.5–1 pF) + the 10 cm
  jumper cable + the 2 cm board-to-board gap → call it **`Cbar` ≈ 1–5 pF**.
- Loop: `mains → Y-cap → main_ground (wobbles) → Cbar → gbat → R6/R2 → floor →
  (cat paw) → catbody → Ccat → earth`. The cat touching *only the plate* still
  closes it (pins `floor` to earth while `Cbar` drags `gbat`).

**The quantitative result — from the simulated `Cbar` sweep (ngspice, Mains=0 to
isolate the supply path, plate-only touch):** the trip boundary on `Cbar` is

| Mains | `V(detection)` drops <2 V at |
|-------|------------------------------|
| 120 V US (170 V pk) | **`Cbar ≈ 3.5 pF`** |
| 230 V EU (325 V pk) | **`Cbar < 2 pF`** |

A realistic layout `Cbar` (10 cm jumpers + opto input-output C + 2 cm board gap)
is **~1–5 pF** — i.e. *in or above* the trip range, **especially on European
230 V where even 2 pF fires.** So the battery isolation does **not** protect the
sensor: a few pF of stray cross-barrier coupling is enough for a cheap 2-prong
supply to false-trigger it.

(Note: this is ~3× *more* sensitive than the back-of-envelope estimate, which had
guessed ~12 pF. The hand calc under-counted because the half-wave detector
responds to the mains *peak*, and the real base-current sensitivity is higher
than the "0.28 µA into the plate" DC figure. Trust the sim: ~3.5 pF / <2 pF.)

**Three live hypotheses — the model + a capacitance measurement can decide:**
1. **`Cbar` is bigger than budgeted** (tightly bundled / long wiring, lick cable
   alongside the FLOOR wire) → supply-dependence is real; fix = **route/shield
   the lick cable**, not the RC values.
2. **The isolation isn't intact** (e.g. a shared ground/3V on the lick header
   ties `GND_BATT` to the Feather) → the simple "supply wobbles the reference"
   path returns. **Trace the real board to rule this out.**
3. **It's really mechanism A (radiated antenna)** and the supply correlation was
   a confound (rig moved, cable re-dressed) → supply-independent; passive RC on
   the sensor is the lever.

**Model status:** `MyLickSensor.asc` represents this with `gbat` (floating
island) / `main_ground` (wobbled by `V2`) / `0` (earth), coupled by `C2 = Cbar`,
with `Rleak` for the DC anchor and `Rpaw`/`ccat` for plate-only touch. The
`.step param Cbar` sweep finds the trip boundary directly. A ready-to-run ngspice
deck is `ngspice_run.cir` (LTspice `.net` won't run on Linux: `§` names + Windows
model libs); run `ngspice -b ngspice_run.cir`. **Set `Mains` amp = 0 when
studying the supply path** — at 4.5 µA the antenna source alone rails the
detector and masks the `Cbar` effect.

**Cheap things to test on the bench first:**
- Measure the actual **board-to-board + lick-cable capacitance** (`Cbar`) and the
  **Feather-ground-to-earth AC voltage** per supply (cheap → tens of V; laptop/
  battery → ~0).
- Run `TestLickADC.py` with **no cat**, on each supply, and watch idle ADC ripple.
- Quick wins if it's hypothesis 1/2: grounded (3-prong) supply or battery for the
  Feather, and keep the lick cable short / away from Feather-ground wiring.

## Design sweep — R6/R2 × sensor-cap (from MyLickSensor.asc)
Goal: reject mains AND recover fast enough to count licks AND still fire on a
real lick. **These three fight each other — no passive RC wins all three:**
- mains rejection wants low node impedance at 60 Hz (big C / low R)
- fast recovery wants small `τ = C·(R6+R2)` (small C / low R)
- weak-lick sensitivity wants high node impedance (high R)

| R6=R2 | C(OPT1) | mains 4.5 µA | mains 22 µA | fires 300 k | fires 1 MΩ | recovery |
|-------|---------|--------------|-------------|-------------|------------|----------|
| 10 M  | 0.1 µF  | ok           | **ok**      | yes         | **no**     | **~2 s** |
| 1 M   | 10 nF   | ok           | fail        | yes         | yes        | **<30 ms** |
| 470 k | 22 nF   | ok           | fail        | yes         | yes        | <30 ms   |
| 100 k | 10 nF   | ok           | fail        | yes         | **no**     | <2 ms    |

## Recommendation
**R6 = R2 → 1 MΩ (from 10 MΩ), sensor OPT1 → 10 nF (from 0.1 µF).**
(Alt: 470 k / 22 nF — slightly better leak separation.)
- rejects realistic (4.5 µA) body-coupled mains
- fires on real licks incl. a weak 1 MΩ contact
- recovers in <30 ms → resolves individual licks to ~7 Hz (fixes the latch, so
  the firmware can actually count licks/bouts)
- bonus: dropping R 10 M→1 M raises the DC-leak trigger threshold ~20 MΩ→~5 MΩ
  (less twitchy to moisture films too)
- **caveat:** strong coupling (≥~22 µA, e.g. wiring near mains) still defeats
  any passive RC → then needs plate/cable shielding or guard ring, or active
  excitation + synchronous detection.

## To do
- [ ] Run `legacy/v1_firmware/TestLickADC.py` while a cat actually drinks to **measure the
      real lick voltage/resistance range** → sets `lick_threshold` and tells us
      where to put R6/R2 (trigger should sit *between* a real lick and a leak).
- [ ] Validate 1 M/10 nF with a 6 Hz lick train (clean countable edges, quiet
      under 4.5 µA mains).
- [ ] Decide if strong-mains hardening (shield/guard/active) is needed in the
      real environment.
- [x] Build the isolated-island supply model in LTspice (gbat/main_ground/0,
      V2 + C2=Cbar + Rleak + Rpaw/ccat). Done — see glossary + finding 7.
- [x] **Run the `.step param Cbar` sweep** — done (`ngspice_run.cir`). Trip
      boundary `Cbar ≈ 3.5 pF` at 120 V US, `< 2 pF` at 230 V EU. Within realistic
      layout coupling → isolation does not protect; strongly supports hypothesis 1.
- [ ] **Measure on the bench (finding 7):** (a) board-to-board + lick-cable
      capacitance `Cbar`; (b) Feather-ground-to-earth AC voltage per supply
      (cheap → tens of V, laptop/battery → ~0); (c) `TestLickADC.py` with **no
      cat** on each supply, watching idle ADC ripple.
- [ ] **Rule out hypothesis 2:** trace the real board to confirm the lick header
      doesn't tie `GND_BATT` to the Feather ground (which would defeat isolation).
- [ ] If hypothesis 1/2 confirmed: quick fixes = grounded/battery supply for the
      Feather + short/dressed-away lick cable, before any RC rework.

## Files
- `MyLickSensor.asc` — the working LTspice model (needs `lick_models.inc` +
  `PC817.asy` alongside it)
- `lick_models.inc` — device models + PC817 optocoupler subcircuit
- `PC817.asy` — optocoupler symbol
- `EasyEDA_exports/` — original schematic PDF + netlists
- `OLD/` — earlier drafts and superseded simulation decks
