# Magna Energia iPortal – Home Assistant integrácia

Custom_component pre Home Assistant, ktorý sa prihlási do zákazníckeho portálu
dodávateľa elektriny [Magna Energia](https://iportal.magna-energia.sk/) a
vystaví dennú/mesačnú spotrebu a prebytky výroby (rozdelené do 4 pásiem tarify
4T Univerzál), špičkový výkon a odhadované náklady ako HA senzory.

Portál nemá captchu, takže sa prihlasuje priamo cez `aiohttp` – žiadny
prehliadač, žiadna externe zachytávaná session. Prihlásenie beží nanovo pri
každom pravidelnom stiahnutí dát (raz za 4 hodiny).

## Inštalácia

### Ručne

1. Skopíruj `custom_components/magna/` do `/config/custom_components/magna/`.
2. Reštartuj Home Assistant.
3. Nastavenia → Zariadenia a služby → Pridať integráciu → **Magna Energia iPortal**.
4. Zadaj login a heslo z `iportal.magna-energia.sk`.

### Cez HACS (custom repository)

1. HACS → tri bodky vpravo hore → Custom repositories.
2. Pridaj URL tohto repozitára, kategória **Integration**.
3. Nainštaluj "Magna Energia iPortal", reštartuj HA, pridaj integráciu ako vyššie.

## Senzory

Pre každý z 3 odberných bodov (spotreba, prebytok výroby, požičovňa):

- denná a mesačná spotreba/výroba spolu aj rozdelená do 4 pásiem (Noc,
  Ráno/Večer, Dopoludnie, Popoludnie) – okrem požičovne, tá má len súčty
- špičkový výkon a čas jeho výskytu (okrem požičovne)
- odhadované náklady v EUR podľa portálu (len pre spotrebu)

Senzor „Spolu (deň)" je takmer vždy 0 – portál dopĺňa dáta spätne a konkrétny
deň má reálne hodnoty až o niekoľko dní neskôr. Na históriu po dňoch slúžia
dlhodobé štatistiky nižšie, nie tento senzor.

## Dlhodobé štatistiky (celý mesiac po dňoch)

Pri každom stiahnutí dát integrácia navyše naimportuje **celý aktuálny aj
predošlý mesiac po dňoch** do dlhodobých štatistík Home Assistantu, každý deň so
svojím skutočným dátumom. Keďže sa mesiac reimportuje pri každom cykle, spätne
doúčtované dni sa automaticky opravia.

Štatistiky (jednotka kWh, typ „súčet"):

- `magna:spotreba_total`, `magna:spotreba_noc`, `magna:spotreba_rano_vecer`,
  `magna:spotreba_dopoludnie`, `magna:spotreba_popoludnie`
- to isté pre `magna:vyroba_*`
- `magna:pozicovna_total`

Nájdeš ich v **Nastavenia → Vývojárske nástroje → Štatistiky**, v karte
*Statistics graph* a dajú sa pridať do panela **Energie**. `*_total` je súčet
štyroch pásiem, takže oproti mesačnému číslu na portáli môže mať drobnú
zaokrúhľovaciu odchýlku (rádovo stotiny kWh za mesiac).

## Bezpečnosť

Prihlasovacie údaje sa zadávajú výlučne cez formulár config flow v HA UI a HA
ich ukladá vo vlastnom šifrovanom úložisku config entry – nikde v kóde nie sú
natvrdo a do logu/diagnostiky sa nikdy nezapíšu (`diagnostics.py` ich redaguje).
