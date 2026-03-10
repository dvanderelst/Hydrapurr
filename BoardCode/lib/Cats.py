# Module for handling cat information

import Settings

def get_name(tag_key):
    cats = Settings.cats
    if tag_key not in cats: return 'unknown'
    return cats[tag_key].get('name', 'unknown')

def get_age(tag_key):
    cats = Settings.cats
    if tag_key not in cats: return None
    return cats[tag_key].get('age')

def get_all_names():
    cats = Settings.cats
    all_names = []
    for tag_key in cats:
        name = cats[tag_key].get('name')
        if name: all_names.append(name)
    return all_names