"""Viewer translations. English text is the key, so a string missing from FI simply shows in English."""
import streamlit as st

LANGUAGES = {"en": "English", "fi": "Suomi"}

FI = {
    # Page and tabs
    "Apetit yield model viewer": "Apetit-satomallin näkymä",
    "Loading the trained models": "Ladataan opetettuja malleja",
    "Baseline vs our model": "Vertailutaso vs. oma malli",
    "Season by season": "Kausi kerrallaan",
    "Try the model": "Kokeile mallia",
    "Future risk": "Tulevaisuuden riski",
    # Shared terms
    "Actual": "Toteutunut",
    "Baseline": "Vertailutaso",
    "Our model": "Oma malli",
    "Finland": "Suomi",
    "Sweden": "Ruotsi",
    "Pea": "Herne",
    "Turnip rape": "Rypsi",
    "Potato": "Peruna",
    "Carrot": "Porkkana",
    "Spinach": "Pinaatti",
    "Region": "Alue",
    "Crop": "Kasvi",
    "Farm": "Tila",
    "Field": "Lohko",
    "Season": "Kausi",
    "Seasons": "Kaudet",
    "Weather": "Sää",
    "Irrigation": "Kastelu",
    "Region and crop": "Alue ja kasvi",
    "Yield (t/ha)": "Sato (t/ha)",
    # Baseline vs our model
    "Does weather make yield forecasts better?": "Parantaako säätieto satoennusteita?",
    "Both methods predict the yield of a contract crop on a farm for a season **they did not see in training**. The data is synthetic, so these results say nothing about real Apetit farms.":
        "Molemmat menetelmät ennustavat sopimuskasvin sadon tilakohtaisesti kaudelle, **jota ne eivät nähneet opetuksessa**. Aineisto on synteettistä, joten tulokset eivät kerro mitään Apetitin todellisista tiloista.",
    "Baseline: farm average": "Vertailutaso: tilan keskiarvo",
    "The farm's average yield for that crop across the training seasons. It knows the farm but **ignores weather**, so it predicts about the same number every season.":
        "Tilan kyseisen kasvin keskimääräinen sato opetuskausilta. Se tuntee tilan, mutta **ei huomioi säätä**, joten se ennustaa joka kaudelle suunnilleen saman luvun.",
    "Our model: weather-aware regression": "Oma malli: säätiedot huomioiva regressio",
    "Farm effect + technology trend + soil + irrigation + crop-stage weather (drought, heat, rain at sowing and harvest). It uses **no same-season farm inputs**, because those aren't known in advance.":
        "Tilavaikutus + teknologiatrendi + maaperä + kastelu + kasvuvaiheen sää (kuivuus, helle, sade kylvön ja korjuun aikaan). Malli **ei käytä saman kauden tilakohtaisia panostietoja**, koska niitä ei tiedetä etukäteen.",
    "How to test": "Testaustapa",
    "Leave one season out uses later seasons to predict earlier ones. Predicting forward only uses the past, so it's closer to real forecasting.":
        "Yhden kauden jättäminen pois käyttää myös myöhempiä kausia aiempien ennustamiseen. Eteenpäin ennustaminen käyttää vain menneitä kausia, joten se on lähempänä todellista ennustamista.",
    "Leave one season out": "Yksi kausi jätetään pois",
    "Predict 2022–2026 from earlier seasons": "Vuosien 2022–2026 ennuste aiemmista kausista",
    "Regional production error": "Alueellisen tuotannon virhe",
    "Farm-level yield error (nRMSE)": "Tilatason satovirhe (nRMSE)",
    "Scorer-style C1 score": "C1-pisteet virallisella kaavalla",
    "{delta} vs baseline {base}": "{delta} vs. vertailutaso {base}",
    "**Don't read the score as our real C1 result.** It applies the official formula to farm-level rows, while the hidden answers are per parcel and noisier. Model settings were also tuned on these seasons, so expect the real score to be lower.":
        "**Älä tulkitse pisteitä todelliseksi C1-tulokseksemme.** Niissä virallista kaavaa sovelletaan tilatason riveihin, kun taas piilotetut vastaukset ovat lohkokohtaisia ja kohinaisempia. Mallin asetukset on lisäksi viritetty näillä samoilla kausilla, joten todellisen tuloksen voi odottaa olevan heikompi.",
    "Regional production error, by crop": "Alueellisen tuotannon virhe kasveittain",
    "Average gap between predicted and actual total production per season. Shorter is better.":
        "Ennustetun ja toteutuneen kokonaistuotannon keskimääräinen ero kausittain. Lyhyempi on parempi.",
    "Baseline production error": "Vertailutason tuotantovirhe",
    "Our model production error": "Oman mallin tuotantovirhe",
    "Baseline yield error": "Vertailutason satovirhe",
    "Our model yield error": "Oman mallin satovirhe",
    "Improvement": "Parannus",
    "Production error": "Tuotantovirhe",
    "Method": "Menetelmä",
    "Error": "Virhe",
    "How the yield data was cleaned": "Miten satoaineisto puhdistettiin",
    "{fixed} survey yields were corrected as ×10 slips and {excluded} delivery-based yields were excluded as implausible. Every change is listed with its rule.":
        "{fixed} kyselyn satolukemaa korjattiin kymmenkertaisina desimaalivirheinä, ja {excluded} toimituksiin perustuvaa satolukemaa jätettiin pois epäuskottavina. Jokainen muutos on listattu sääntöineen.",
    "Record": "Tietue",
    "Data field": "Tietokenttä",
    "Old value": "Vanha arvo",
    "New value": "Uusi arvo",
    "Rule": "Sääntö",
    "Source": "Lähde",
    "above 3x crop median; treated as a x10 decimal slip": "yli 3 x kasvin mediaani; käsitelty kymmenkertaisena desimaalivirheenä",
    "ERP-derived yield outside 0.35-2.2x crop-year median; excluded": "ERP-pohjainen sato kasvin vuosimediaanin 0,35–2,2-kertaisen välin ulkopuolella; jätetty pois",
    # Season by season
    "The **baseline stays nearly flat**. The test of our model is whether it follows the good and bad seasons. Every point below is a prediction for a season held out of training.":
        "**Vertailutaso pysyy lähes tasaisena.** Oman mallin testi on se, seuraako se hyviä ja huonoja kausia. Jokainen alla oleva piste on ennuste kaudelle, joka jätettiin pois opetuksesta.",
    "Test": "Testi",
    "{name}: area-weighted average yield": "{name}: pinta-alalla painotettu keskisato",
    "Baseline miss": "Vertailutason poikkeama",
    "Our model miss": "Oman mallin poikkeama",
    "Check a single farm": "Tarkastele yksittäistä tilaa",
    "Farm ({n} with data)": "Tila ({n} tilalta on tietoja)",
    "This farm has only one held-out season in this test. Pick another farm or the other test to see a line.":
        "Tällä tilalla on tässä testissä vain yksi opetuksesta pois jätetty kausi. Valitse toinen tila tai toinen testi, niin näet viivan.",
    "A single farm has more random variation than a regional average, and some seasons are missing where the farm didn't report.":
        "Yksittäisellä tilalla on enemmän satunnaisvaihtelua kuin alueen keskiarvossa, ja joitakin kausia puuttuu, koska tila ei raportoinut niitä.",
    # Try the model
    "Pick a field, a crop and a season's weather. This runs the **final trained model live**, and shows why it landed on that number.":
        "Valitse lohko, kasvi ja kauden sää. Tämä ajaa **lopullisen opetetun mallin suoraan** ja näyttää, miksi se päätyi kyseiseen lukuun.",
    "Historical weather (1991–2026)": "Historiallinen sää (1991–2026)",
    "SSP2-4.5, the C1 forecast seasons (2027–2031)": "SSP2-4.5, C1-ennustekaudet (2027–2031)",
    "SSP1-2.6, low emissions (2041–2060)": "SSP1-2.6, matalat päästöt (2041–2060)",
    "SSP2-4.5, middle emissions (2041–2060)": "SSP2-4.5, keskitason päästöt (2041–2060)",
    "SSP5-8.5, high emissions (2041–2060)": "SSP5-8.5, korkeat päästöt (2041–2060)",
    "Farm's usual practice": "Tilan tavanomainen käytäntö",
    "Irrigated": "Kasteltu",
    "Not irrigated": "Kastelematon",
    "Only available for Sweden, where 167 farms switch practice. No Finnish farm does, so the effect can't be measured there.":
        "Käytettävissä vain Ruotsissa, jossa 167 tilaa vaihtaa käytäntöä. Yksikään suomalainen tila ei vaihda, joten vaikutusta ei voi mitata Suomessa.",
    "{pct} against the baseline": "{pct} vertailutasoon nähden",
    "The same for any weather": "Sama säästä riippumatta",
    "Actual for this farm": "Tilan toteutunut sato",
    "Held-out model prediction: {model} t/ha; held-out baseline: {base} t/ha":
        "Oman mallin ennuste, kun kausi on jätetty pois opetuksesta: {model} t/ha; vertailutaso samoin: {base} t/ha",
    "Not available": "Ei saatavilla",
    "Future season, or the farm didn't report": "Tuleva kausi, tai tila ei raportoinut",
    "clay": "savi",
    "silt": "hiesu",
    "fine sand": "hieta",
    "sand": "hiekka",
    "organic": "eloperäinen maa",
    "Soil-map class: {soil}, {area} ha. The soil map is only about 88% accurate.":
        "Maaperäkartan luokka: {soil}, {area} ha. Maaperäkartta on vain noin 88-prosenttisesti tarkka.",
    "This farm's usual irrigated share for this crop: {share}.": "Tilan tavanomainen kastellun alan osuus tällä kasvilla: {share}.",
    "Technology is held at 2025, so this shows the effect of weather only.": "Teknologia on pidetty vuoden 2025 tasolla, joten tämä näyttää vain sään vaikutuksen.",
    "The farm-level comparison uses a season the model did not train on. The main figure comes from the final model, which did see this season, so use the Season by season tab to judge accuracy.":
        "Tilatason vertailu käyttää kautta, jolla mallia ei opetettu. Päälukema tulee lopullisesta mallista, joka on nähnyt tämän kauden, joten arvioi tarkkuutta Kausi kerrallaan -välilehdeltä.",
    "The modelled irrigation effect is an estimate. It averages about the measured +6% for Sweden, but misses individual seasons and can turn slightly negative in very wet seasons, which is an artifact.":
        "Mallinnettu kastelun vaikutus on arvio. Se on keskimäärin lähellä Ruotsissa mitattua +6 %:a, mutta ei tavoita yksittäisiä kausia ja voi hyvin sateisina kausina kääntyä hieman negatiiviseksi, mikä on mallin harha.",
    "Why this number": "Miksi tämä luku",
    "Each bar is that driver's percentage effect, starting from {base} t/ha for an average field and season. The effects multiply to give the model's result.":
        "Jokainen palkki on kyseisen tekijän prosentuaalinen vaikutus, lähtien keskimääräisen lohkon ja kauden sadosta {base} t/ha. Vaikutukset kerrotaan keskenään, jolloin saadaan mallin tulos.",
    "Effect on yield": "Vaikutus satoon",
    "Driver": "Tekijä",
    "Effect": "Vaikutus",
    "Drought stress": "Kuivuusstressi",
    "Heat": "Helle",
    "Rain after sowing": "Sade kylvön jälkeen",
    "Rain before harvest": "Sade ennen korjuuta",
    "Season rain and evaporation": "Kauden sade ja haihdunta",
    "Season timing": "Kauden ajoitus",
    "Warm, wet days": "Lämpimät ja märät päivät",
    "May temperature": "Toukokuun lämpötila",
    "Soil": "Maaperä",
    "Technology trend": "Teknologiatrendi",
    "This farm": "Tämä tila",
    "Weather values used": "Käytetyt sääarvot",
    "Measure": "Mittari",
    "Value": "Arvo",
    "Sowing day of year": "Kylvöpäivä (vuoden päivä)",
    "Maturity day of year": "Kypsymispäivä (vuoden päivä)",
    "Drought stress, sensitive stage (0–1)": "Kuivuusstressi, herkkä kasvuvaihe (0–1)",
    "Heat days at 27 °C or above, sensitive stage": "Hellepäivät, vähintään 27 °C, herkkä kasvuvaihe",
    "Rain in 14 days after sowing (mm)": "Sade 14 päivän aikana kylvön jälkeen (mm)",
    "Rain in 10 days before harvest (mm)": "Sade 10 päivän aikana ennen korjuuta (mm)",
    "Warm, wet days, July–August": "Lämpimät ja märät päivät, heinä–elokuu",
    "May mean temperature (°C)": "Toukokuun keskilämpötila (°C)",
    "Self-check: live predictions differ from the submitted C1 file by at most {diff} t/ha on a sample of 60 rows (the file is rounded to 3 decimals).":
        "Omavalvonta: suorat ennusteet poikkeavat palautetusta C1-tiedostosta enintään {diff} t/ha 60 rivin otoksessa (tiedosto on pyöristetty kolmeen desimaaliin).",
    # Future risk
    "**No answers are public for these tasks, so neither method can be scored here.** The first two tabs show how far the model can be trusted on past seasons. These charts are the model's estimates, not measured accuracy.":
        "**Näihin tehtäviin ei ole julkisia vastauksia, joten kumpaakaan menetelmää ei voi pisteyttää tässä.** Kaksi ensimmäistä välilehteä näyttävät, kuinka pitkälle mallin tuloksiin voi luottaa menneillä kausilla. Nämä kaaviot ovat mallin arvioita, eivät mitattua tarkkuutta.",
    "Forecast 2027–2031, against the package's reference baseline": "Ennuste 2027–2031 verrattuna aineistopaketin vertailutasoon",
    "Baseline here is the package's reference method: the farm's survey average since 2016, or a fixed 3.4 t/ha for Swedish peas. It varies slightly between years only because the planted fields change. Our model reacts to one supplied weather realisation for 2027–2031.":
        "Vertailutaso on tässä aineistopaketin vertailumenetelmä: tilan kyselyn keskiarvo vuodesta 2016 alkaen tai kiinteä 3,4 t/ha Ruotsin herneelle. Se vaihtelee vuosien välillä hieman vain siksi, että kylvetyt lohkot vaihtuvat. Oma malli reagoi yhteen annettuun säätoteutumaan vuosille 2027–2031.",
    "Yield change by 2041–2060, against 1991–2020": "Sadon muutos vuosina 2041–2060 verrattuna vuosiin 1991–2020",
    "Climate scenario": "Ilmastoskenaario",
    "SSP1-2.6, low emissions": "SSP1-2.6, matalat päästöt",
    "SSP2-4.5, middle emissions": "SSP2-4.5, keskitason päästöt",
    "SSP5-8.5, high emissions": "SSP5-8.5, korkeat päästöt",
    "Change in mean yield (%). Zero is the package's “no change” baseline": "Keskisadon muutos (%). Nolla on aineistopaketin vertailutaso ”ei muutosta”",
    "Change %": "Muutos %",
    "Low %": "Alaraja %",
    "High %": "Yläraja %",
    "Bad-year chance": "Huonon vuoden todennäköisyys",
    "Dot: our estimate. Line: the range when each training season is left out in turn, which is not total uncertainty. Orange: the baseline of no change. Swedish peas (9 seasons) and Finnish peas are low confidence.":
        "Piste: oma arviomme. Viiva: vaihteluväli, kun kukin opetuskausi jätetään vuorollaan pois; se ei kuvaa koko epävarmuutta. Oranssi: vertailutaso eli ei muutosta. Ruotsin herneen (9 kautta) ja Suomen herneen tulokset ovat epävarmoja.",
    "Our change %": "Oma muutos %",
    "Our bad-year chance": "Oma huonon vuoden todennäköisyys",
    "Baseline change %": "Vertailutason muutos %",
    "Baseline bad-year chance": "Vertailutason huonon vuoden todennäköisyys",
    "Cost of replacing shortfalls with imports": "Satovajeen korvaaminen tuonnilla: kustannus",
    "Today's climate": "Nykyilmasto",
    "Expected € a year: shortfall against today's average × 2025 contract price × replacement premium. It counts only the premium, and excludes import emissions, lost margin and price shocks. The Swedish figures are low confidence.":
        "Odotettu kustannus, € vuodessa: vaje nykyiseen keskiarvoon verrattuna × vuoden 2025 sopimushinta × korvaushinnan lisä. Mukana on vain hintalisä; tuonnin päästöt, menetetty kate ja hintašokit eivät sisälly siihen. Ruotsin luvut ovat epävarmoja.",
    "By crop": "Kasveittain",
    "Scenario": "Skenaario",
    "Area (ha)": "Pinta-ala (ha)",
    "Contract price (€/t)": "Sopimushinta (€/t)",
    "Replacement premium": "Korvaushinnan lisä",
    "Baseline production (t)": "Vertailutuotanto (t)",
    "Average shortfall (t)": "Keskimääräinen vaje (t)",
    "Expected cost (€/year)": "Odotettu kustannus (€/vuosi)",
    "Bad-year cost, 90th percentile (€)": "Huonon vuoden kustannus, 90. persentiili (€)",
    "Added against today's climate (€/year)": "Lisäys nykyilmastoon verrattuna (€/vuosi)",
}

# Number formats for the charts. Vega keeps the last locale it was given, so English has to be set explicitly too.
CHART_LOCALE = {"en": {"decimal": ".", "thousands": ",", "grouping": [3], "currency": ["€", ""]},
                "fi": {"decimal": ",", "thousands": " ", "grouping": [3], "currency": ["", " €"], "percent": " %"}}


def lang():
    return st.session_state.get("lang", "en")


def t(text, **values):
    text = FI.get(text, text) if lang() == "fi" else text
    return text.format(**values) if values else text


def num(value, spec=".2f"):
    """Format a number for the reader. Keeps the ASCII minus, because st.metric reads it to pick the arrow direction."""
    text = format(value, spec)
    if lang() == "fi":
        text = text.replace(",", " ").replace(".", ",").replace("%", " %")
    return text


def eur(value):
    return num(value, ",.0f") + " €" if lang() == "fi" else f"€{value:,.0f}"
