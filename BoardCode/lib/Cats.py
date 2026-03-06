# Module for handling cat information

import Settings

def get_name(tag_key):
    cats = Settings.cats
    if tag_key not in cats: return 'unknown'
    return cats[tag_key]['name']

def get_age(tag_key):
    cats = Settings.cats
    return cats[tag_key]['age']

def get_all_names():
    cats = Settings.cats
    all_names = []
    for tag_key in cats: all_names.append(cats[tag_key]['name'])
    return all_names