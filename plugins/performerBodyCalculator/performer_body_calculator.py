import sys, json
import logging as log
from collections import defaultdict 

import config
from performer_calculator import *
from body_tags import *

try:
    from stashapi.log import StashLogHandler
    from stashapi.stashapp import StashInterface
    from stashapi.stash_types import OnMultipleMatch
except ModuleNotFoundError:
    print("You need to install stashapp-tools. (https://pypi.org/project/stashapp-tools/)", file=sys.stderr)
    print("If you have pip (normally installed with python), run this command in a terminal (cmd): 'pip install stashapp-tools'", file=sys.stderr)
    sys.exit()
log.basicConfig(format="%(message)s", handlers=[StashLogHandler()], level=config.log_level)

def main(stash_in=None, mode_in=None):
    global stash

    if stash_in:
        stash = stash_in
        mode = mode_in
    else:
        fragment = json.loads(sys.stdin.read())
        stash = StashInterface(fragment["server_connection"])
        mode = fragment['args']['mode']

    if mode == "run_calculator":
        run_calculator()
    if mode == "destroy_managed_tags":
        destroy_managed_tags()

def destroy_managed_tags():
    tags = stash.find_tags(f={"description":{"value": "^\\[Managed By: PBC Plugin\\]","modifier": "MATCHES_REGEX"}}, fragment="id")
    log.info(f"Deleting {len(tags)} tags...")
    stash.destroy_tags([t["id"] for t in tags])

def run_calculator():

    all_tag_ids = []
    tag_updates = defaultdict(list)

    log.info("Finding Tags in Stash...")
    for enum_class in get_tag_classes():
        enumtag_stash_init(enum_class, all_tag_ids)

    # get performers with measurements
    performers = stash.find_performers(fragment=PERFORMER_FRAGMENT)
    
    log.info("Removing existing plugin tags...")
    stash.update_performers({
        "ids": [p["id"] for p in performers],
        "tag_ids":{
            "ids": all_tag_ids,
            "mode": "REMOVE"
        }
    })

    log.info("Parsing Performers...")
    for p in performers:
        if p.get("gender") != 'FEMALE':
            continue

        p_id = f"{p['name']} ({p['id']})"
        try:
            p = StashPerformer(p)
            p.get_tag_updates(tag_updates)
        except DebugException as e:
            log.debug(f"{p_id}: {e}")
        except WarningException as e:
            log.warning(f"{p_id}: {e}")
        except Exception as e:
            log.error(f"{p_id}: {e}")

    for enum, performer_ids in tag_updates.items():
        if not isinstance(enum, config.TAGS_TO_USE):
            log.debug(f"{enum} not in config skipping")
            continue
        if not performer_ids:
            continue
        log.info(f"Adding {enum} tag to {len(performer_ids)} performer(s)...")
        stash.update_performers({
            "ids": performer_ids,
            "tag_ids":{
                "ids": [enum.tag_id],
                "mode": "ADD"
            }
        })

def enumtag_stash_init(enum_class, tag_id_list=[]):
    for enum in enum_class:
        if not isinstance(enum, config.TAGS_TO_USE):
            continue
        tag_alias_id = f"PBC:{enum}"
        stash_tag = stash.find_tag(tag_alias_id, on_multiple=OnMultipleMatch.RETURN_NONE)
        if stash_tag:
            enum.tag_id = stash_tag["id"]
        else:
            tag_create_input = enum.value.tag_create_input(str(enum), tag_alias_id)
            enum.tag_id = stash.find_tag(tag_create_input, create=True)["id"]
        tag_id_list.append(enum.tag_id)
    return tag_id_list


if __name__ == '__main__':
    main()
