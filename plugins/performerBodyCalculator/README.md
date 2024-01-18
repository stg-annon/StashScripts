# Stash Plugin: Performer Body Calculator 

This plugin will tag performers based on existing metadata within Stash.

If the `Measurements` attribute is present, it will be used to calculate the performer's body part sizes and body shape. The following formats are supported:
- `32D-28-34` (Bra Size, Waist, Hips)
- `36-28-34` (Bust, Waist, Hips)
- `32D` (Bra Size)
- `32D (70D)` (Bra Size with Alternate Units)

If the `Height` and `Weight` attributes are both present, they will be used to calculate the performer's body type.

### Tags
The tags will be generated or will use existing tags, the plugin looks for tags based of its alias so you can rename or merge a tag into whatever you like as long as the generated alias is present in the tag, the alias the plugin will look for starts with `PDT:`

### Config
rename `example_config.py` to `config.py`
if you den't want specific tags you can comment them out in the config