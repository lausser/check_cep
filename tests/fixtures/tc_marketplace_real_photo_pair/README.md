# tc_marketplace_real_photo_pair

Marketplace-style fixture built from bundled real photo assets. Two hair dryer tiles come from separate Wikimedia Commons photos and are visually similar enough that a small preview crop is ambiguous without region guidance.

## What it proves

- The regression path can stay fully local while using real photographic imagery.
- A small real-photo preview crop is ambiguous globally across the dryer pair.
- Region guidance resolves the ambiguity and opens only the intended tile.
- Other real-photo categories keep the page visually busy without relying on network content.

## Fixture strategy

- The page mixes local photos for dryers, a smartwatch, a handbag, a drill, and a dress.
- The target and distractor dryer previews are both derived from separate real photos.
- The committed template is a smaller crop from the target dryer photo chosen specifically because it remains ambiguous across the dryer pair.
- The test first proves global ambiguity, then scopes matching to the target card region.

## Photo sources

Bundled local assets were derived from these Wikimedia Commons files and resized/cropped for deterministic fixture use:

- `Haardroger_1.JPG` by Silver Spoon, own work, CC BY-SA 3.0/2.5/2.0/1.0
- `Haardroger_2.JPG` by Silver Spoon, own work, CC BY-SA 3.0/2.5/2.0/1.0
- `Google Pixel Watch - 1 (cropped).jpg` by KKPCW (Kyu3), own work, CC BY-SA 4.0
- `Black handbag.jpg` by Tahrirchiqiz, own work, CC BY 4.0
- `Milwaukee Magnum Holeshooter.png` by Jonathan Mauer, own work, CC BY-SA 4.0
- `A BEAUTIFUL Ankara dress.jpg` by ItunuIjila, own work, CC BY-SA 4.0

## Re-capturing templates

```bash
podman run --rm \
  --volume ./tests/fixtures/tc_marketplace_real_photo_pair:/home/pwuser/tests:rw,z \
  check_cep:test \
  node /home/pwuser/tests/capture-templates.mjs
```
