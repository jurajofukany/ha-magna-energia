# Ikona integrácie

Zdroj: [`icon.svg`](icon.svg) – kruhový terč so 4 výsečami (4 pásma tarify
4T Univerzál: Noc / Ráno-Večer / Dopoludnie / Popoludnie), tmavomodrý disk,
biele „M" a jantárový blesk.

Vygenerované PNG (z `icon.svg` cez `@resvg/resvg-js`):

- `custom_integrations/magna/icon.png` – 256×256
- `custom_integrations/magna/icon@2x.png` – 512×512

## Ako sa ikona dostane do Home Assistantu

HA berie ikonu integrácie výhradne z repozitára
[home-assistant/brands](https://github.com/home-assistant/brands), nie z
`custom_components/`. Postup:

1. Fork `home-assistant/brands`.
2. Skopíruj priečinok `custom_integrations/magna/` (s oboma PNG) do forku.
3. PNG musia byť orezané na obsah, štvorcové, s priehľadným pozadím – toto
   generované PNG to spĺňa.
4. Otvor PR; po zlúčení sa ikona zobrazí pri „Magna Energia iPortal"
   v Nastavenia → Zariadenia a služby.

## Regenerovanie PNG

```bash
npm install @resvg/resvg-js
node gen.js   # skript v scratchpade, alebo pozri icon.svg a vyrenderuj ľubovoľným nástrojom
```
