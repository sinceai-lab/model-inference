# Can a map be the demo's "wow" moment?

**Verdict: it can be the visual moment, but the insight in it isn't geographic.** The data has almost no spatial pattern, so a map can't tell advisors where the risk is. A map works here as a way into a farm: it shows one big scenario effect and leads to a field and a draft action. The useful part is the ranked farm list beside it.

All figures are from synthetic data. Reproduce them with `cd src && python build_map_data.py`, which writes `outputs/map_*.csv`. The land checks also need `--natural-earth DIR` with Natural Earth 10m files.

## What the geography is

| Layer | Finding |
|---|---|
| Parcels | 14,213 real polygons, but every one is a synthetic four-corner shape. Area is within 1% of `area_ha` and centroids within 41 m of `lat`/`lon`. 3,027 parcels overlap another by over 10%, and 943 by over 50%. |
| Catchments | 42 Voronoi polygons (the package says so). Every parcel sits in its stated catchment, but polygon area differs from stated area by 0.3 to 22 times. |
| Climate grid | 84 cells at 0.25° (about 15 × 28 km). 70 hold parcels. 10 Swedish cell centres are offshore, and 206 parcels use such cells. |
| Farm registry | 3 farms (F0028, F0180, F0223) have swapped coordinates. Once unswapped, farms are on average 0.4 km from their parcels. The map uses parcel centroids instead. |
| Against real land | No parcel falls in the wrong country. 95 Swedish parcel centres are offshore, by up to about 5 km, and 274 Finnish ones are in lakes. |

So a real basemap would show fields in lakes and the sea, and imply real places. **The map uses only a simplified coastline, with no tiles, roads or towns.** It also needs no API key or internet.

## Does anything vary by place?

| Measure | Result | Reading |
|---|---|---|
| Yield change between grid cells | Spread 0.3–1.8 points. Weather-resampling noise 0.4–1.3 points. At best about half is signal, and for some crops none. Neighbouring cells are no more alike than others (similarity −0.14 to +0.11). | Mostly noise from one simulated weather run. **Not drawn.** A map of it would look striking and be false. |
| Maturity shift | 15.4–16.3 days earlier under Hothouse in every pea cell | One colour. A single number. |
| Farm soil mix | Neighbour similarity 0.00 (Finland) and −0.04 (Sweden), inside chance. Farms explain about 40% of field soil differences, catchments 2–3%. | Sandy soil follows the farm, not the area. Dots look scattered because they are. |
| Soil, by climate story | Sand against clay under Hothouse: −0.9 to −2.4 points, and the 90% weather range excludes zero for all 6 crop and region pairs. Under Below 2 °C it's smaller and includes zero for 3 of 6. | The one robust difference within a crop. Hothouse widens the gap. |
| Scenario | Finnish turnip rape: all 230 farms within ±2% under Below 2 °C, all 230 below −4% under Hothouse. | The visible switch, and it's real. Spinach and Swedish peas move too. Finnish peas, potato and carrot barely move, which is also the finding. |

The soil finding rests on our assumed soil water capacities, and the weather range ignores soil-map error (about 88% accurate) and model error.

## What holds at which scale

| Level | Defensible | Not defensible |
|---|---|---|
| Region and crop | Yield change, bad-year chance, draft actions, with their confidence labels | Combining Finland and Sweden, which are separate operations |
| Soil within a region and crop | Pooled yield change and estimated drought stress per soil | Precise figures: the soil effect comes from assumptions |
| Farm | Soil mix, hectares on sand or fine sand, planned hectares | "This farm is riskier because of where it is" |
| Field | Soil-map class, area and crop plan as a discussion starter | A field-specific climate forecast: models train on farm averages |
| Grid cell | Showing where weather resolution stops | Local climate risk |
| Catchment | Nothing for yield risk; catchments matter for the nutrient track | Yield risk by catchment, which is an arbitrary average |

## Ideas compared

| Idea | Advisor decision it helps | Decision |
|---|---|---|
| Grid-cell yield change, or a heat map | None honest: it maps noise | Rejected |
| Season-shift animation through decades | None: weather features exist only for 2027–31 and 2041–60, with one run per scenario, and the shift is nearly uniform | Rejected |
| Catchment shading | Water protection, not yield | Rejected for this track |
| 14k field polygons with one colour per field | Looks detailed, but values come from cell and soil only, for example 82 distinct values across 2,147 Finnish pea fields | Rejected as false precision |
| **Farm dots coloured by soil mix and story, with a ranked list and drill-down** | Who to contact first, and which planned fields to discuss | **Built** |
| No map: ranked list plus a soil-by-story chart | Same decision, clearer | Strong alternative, see below |

## What we built, and how honest it is

Farm colour is the area-weighted average of a pooled figure per region, crop and soil. Grid-cell differences and irrigation are deliberately left out. Bands are ±2, ±4 and ±6%, coarse enough not to imply precision. Drill-down reuses `field_table()` and `advice()`. The field panel also shows that field's grid-cell figure and says it's mostly noise.

The draft actions are region and crop rules, so they're the same for every farm of a crop. What changes by farm is the soil exposure and the crop plan.

## If only one thing could be shown

Lead with **the ranked farm list and the soil-by-story result**, which is where the advisor's decision and the only robust within-crop difference sit. Use the map for 30 seconds as the way in: flip Below 2 °C to Hothouse, click a top-listed farm, and land on its fields and actions. If it's presented as "where the risk is", it misleads.
