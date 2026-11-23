# Module for handling cat information.
#
# 'unknown' is the sentinel name used by the attribution layer
# (BoutManager) for RFID misses. get_name returns 'unknown' whenever a
# tag is missing or its name is empty/whitespace-only, so callers can
# rely on a usable string in all cases.

import Settings

def get_name(tag_key):
    cats = Settings.cats
    if tag_key not in cats:
        return 'unknown'
    name = cats[tag_key].get('name')
    if not name or not str(name).strip():
        return 'unknown'
    return name

def get_all_names():
    names = []
    for tag_key in Settings.cats:
        name = Settings.cats[tag_key].get('name')
        if name and str(name).strip():
            names.append(name)
    return names