import re, sys, json
import datetime as dt
from pathlib import Path
from string import Template
from inspect import getmembers, isfunction

try:
	import stashapi.log as log
	from stashapi.tools import human_bytes
	from stashapi.stash_types import PhashDistance
	from stashapi.stashapp import StashInterface
except ModuleNotFoundError:
	print("You need to install the stashapi module. (pip install stashapp-tools)", file=sys.stderr)

try:
	import config
except ModuleNotFoundError:
	log.exit(err="could not import config, have you renamed config_example.py to config.py?")

FRAGMENT = json.loads(sys.stdin.read())
stash = StashInterface(FRAGMENT["server_connection"])

SLIM_SCENE_FRAGMENT = """
id
title
date
tags { id }
galleries { id }
files {
	size
	path
	width
	height
	bit_rate
	created_at
	duration
	frame_rate
	video_codec
}
"""

def plugin_main():
	MODE = FRAGMENT["args"]["mode"]
	
	if MODE == "remove":
		clean_scenes()
		for tag in get_managed_tags():
			stash.destroy_tag(tag["id"])

	if MODE == "tag_exact":
		process_duplicates(PhashDistance.EXACT)
	if MODE == "tag_high":
		process_duplicates(PhashDistance.HIGH)
	if MODE == "tag_medium":
		process_duplicates(PhashDistance.MEDIUM)

	if MODE == "split_merged_oshash":
		split_out_oshash_matches()

	if MODE == "clean_scenes":
		clean_scenes()
	if MODE == "generate_phash":
		stash.metadata_generate({"phashes": True})

	log.exit("Plugin exited normally.")

def hooks_main():
	hook_context = FRAGMENT["args"]["hookContext"]
	if hook_context["input"]["delete_file"] == False:
		return # skip hook if file is not actually being deleted
	scene_ids = hook_context["input"]["ids"]
	# need pre hook to work, need to preemptively grab title and work backwards to auto clean remaining scenes

def format_title(group_size, scene_id, flag, title):
	user_template = TITLE_TEMPLATE.substitute({
		"group_size":group_size,
		"scene_id":scene_id,
		"flag":flag
	})
	return f"[PDT: {user_template}] {title}"

def parse_timestamp(ts, format="%Y-%m-%dT%H:%M:%S%z"):
	ts = re.sub(r"\.\d+", "", ts)  # remove fractional seconds
	return dt.datetime.strptime(ts, format)


class StashScene:

	def __init__(self, scene=None) -> None:
		if len(scene["files"]) != 1:
			raise Exception(f"Scene has {len(scene['files'])} file(s), must have one file for comparing")
		file = scene["files"][0]

		self.id = int(scene["id"])
		self.created_at = parse_timestamp(file["created_at"])
		if scene.get("date"):
			self.date = parse_timestamp(scene["date"], format="%Y-%m-%d")
		else:
			self.date = None
		self.path = scene.get("path")
		self.width = file["width"]
		self.height = file["height"]
		# File size in # of BYTES
		self.size = int(file["size"])
		self.frame_rate = int(file["frame_rate"])
		self.bitrate = int(file["bit_rate"])
		self.duration = float(file["duration"])
		# replace any existing tagged title
		self.title = re.sub(r"^\[Dupe: \d+[KR]\]\s+", "", scene["title"])
		self.path = file["path"]
		self.tag_ids = [t["id"] for t in scene["tags"]]
		self.gallery_ids = [g["id"] for g in scene["galleries"]]

		self.remove_reason = None

		self.codec = file["video_codec"].upper()
		if self.codec in config.CODEC_PRIORITY:
			self.codec_priority = config.CODEC_PRIORITY[self.codec]
		else:
			self.codec_priority = None
			log.warning(f"could not find codec {self.codec} used in SceneID:{self.id}")

	def __repr__(self) -> str:
		return f"<StashScene ({self.id})>"

	def __str__(self) -> str:
		return f"id:{self.id}, height:{self.height}, size:{human_bytes(self.size)}, file_created_at:{self.created_at}, title:{self.title}"

	def compare(self, other):
		if not (isinstance(other, StashScene)):
			raise Exception(f"can only compare to <StashScene> not <{type(other)}>")

		if self.id == other.id:
			return None, f"Matching IDs {self.id}=={other.id}"

		def compare_not_found(*args, **kwargs):
			raise Exception("comparison not found")
		for type in config.PRIORITY:
			try:
				compare_function = getattr(self, f"compare_{type}", compare_not_found)
				result = compare_function(other)
				if result and len(result) == 2:
					best, msg = result
					return best, msg
			except Exception as e:
				log.error(f"Issue Comparing {self.id} {other.id} using <{type}> {e}")
		return None, f"{self.id} worse than {other.id}"

def process_duplicates(distance:PhashDistance=PhashDistance.EXACT):

	clean_scenes()  # clean old results

	ignore_tag_id = stash.find_tag(config.IGNORE_TAG_NAME, create=True).get("id")
	duplicate_list = stash.find_duplicate_scenes(distance, fragment=SLIM_SCENE_FRAGMENT)

	total = len(duplicate_list)
	log.info(f"Found {total} sets of duplicates.")

	for i, group in enumerate(duplicate_list):
		scene_group = []
		for s in group:
			try:
				scene_group.append(StashScene(s))
			except Exception as e:
				log.warning(f"Issue parsing SceneID:{s['id']} - {e}")
		filtered_group = []
		for scene in scene_group:
			if ignore_tag_id in scene.tag_ids:
				log.debug(f"Ignore from Tag {scene.id} {scene.title}")
			elif any([Path(ignore_path) in Path(scene.path).parents for ignore_path in config.IGNORE_PATHS]):
				log.warning(f"Ignore from Path {scene.id} {scene.path}")
			else:
				filtered_group.append(scene)

		if len(filtered_group) > 1:
			tag_files(filtered_group)

		log.progress(i / total)


def tag_files(group):
	
	keep_scene = group[0]
	total_size = group[0].size
	for scene in group[1:]:
		total_size += scene.size
		better, msg = scene.compare(keep_scene)
		if better:
			keep_scene = better
			log.debug(f"{better.id} better than {keep_scene.id} - {msg}")

	reason_tags = [s.remove_reason for s in group if s.remove_reason]
	total_size = human_bytes(total_size, round=2, prefix="G")
	reason_tag_ids = [stash.find_tag(f"[Reason: {t}]", fragment="id", create=True)["id"]  for t in reason_tags]

	if not keep_scene:
		log.info(f"could not determine better scene from {group}")
		if config.UNKNOWN_TAG_NAME:
			group_id = group[0].id
			for scene in group:
				tag_ids = [stash.find_tag(config.UNKNOWN_TAG_NAME, create=True).get("id")]
				stash.update_scenes({
					"ids": [scene.id],
					"title": format_title(total_size, group_id, "U", scene.title),
					"tag_ids": {"mode": "ADD", "ids": tag_ids},
				})
		return

	log.info(f"{keep_scene.id} best of:{[s.id for s in group]} {reason_tags}")

	for scene in group:
		if scene.id == keep_scene.id:
			tag_ids = [stash.find_tag(config.KEEP_TAG_NAME, create=True).get("id")]
			tag_ids.extend(reason_tag_ids)
			stash.update_scenes({
				"ids": [scene.id],
				"title": format_title(total_size, keep_scene.id,"K", scene.title),
				"tag_ids": {"mode": "ADD", "ids": tag_ids},
			})
		else:
			tag_ids = []
			tag_ids.append(
				stash.find_tag(config.REMOVE_TAG_NAME, create=True).get("id")
			)
			if scene.remove_reason:
				tag_ids.append(stash.find_tag(f"[Reason: {scene.remove_reason}]", create=True).get("id"))
			stash.update_scenes({
				"ids": [scene.id],
				"title": format_title(total_size, keep_scene.id, "R", scene.title),
				"tag_ids": {"mode": "ADD", "ids": tag_ids},
			})


def clean_scenes():
	scene_count, scenes = stash.find_scenes(
		f={"title": {"modifier": "MATCHES_REGEX", "value": "^\\[PDT: .+?\\]"}},
		fragment="id title",
		get_count=True,
	)

	log.info(f"Cleaning Titles/Tags of {scene_count} Scenes ")

	# Clean scene Title
	for i, scene in enumerate(scenes):
		title = re.sub(r"\[PDT: .+?\]\s+", "", scene["title"])
		stash.update_scenes({"ids": [scene["id"]], "title": title})
		log.progress(i / scene_count)

	# Remove Tags
	for tag in get_managed_tags():
		scene_count, scenes = stash.find_scenes(
			f={"tags": {"value": [tag["id"]], "modifier": "INCLUDES", "depth": 0}},
			fragment="id",
			get_count=True,
		)
		if not scene_count > 0:
			continue
		log.info(f'removing tag {tag["name"]} from {scene_count} scenes')
		stash.update_scenes({
			"ids": [s["id"] for s in scenes],
			"tag_ids": {"mode": "REMOVE", "ids": [tag["id"]]},
		})

def get_managed_tags(fragment="id name"):
	tags = stash.find_tags(
		f={"name": {"value": "^\\[Reason", "modifier": "MATCHES_REGEX"}},
		fragment=fragment,
	)
	tag_name_list = [
		config.REMOVE_TAG_NAME,
		config.KEEP_TAG_NAME,
		config.UNKNOWN_TAG_NAME,
		# config.IGNORE_TAG_NAME,
	]
	for tag_name in tag_name_list:
		if tag := stash.find_tag(tag_name):
			tags.append(tag)
	return tags

def split_out_oshash_matches():

	dupe_oshash_rows = stash.sql_query('SELECT fingerprint, COUNT(*) c FROM files_fingerprints WHERE type is "oshash" GROUP BY fingerprint HAVING c > 1;').get("rows", [])

	ignore_tag_id = stash.find_tag(config.IGNORE_TAG_NAME, create=True).get("id")

	for i, row in enumerate(dupe_oshash_rows):
		oshash, _ = row
		scenes = stash.find_scenes({
			"oshash":{"value": oshash, "modifier": "EQUALS"},
			"file_count":{"modifier": "GREATER_THAN","value": 1 },
			"tags":{"excludes": [ignore_tag_id], "modifier": "INCLUDES_ALL"},
		}, fragment="id title files {id fingerprints  { type value } }")

		for s in scenes:
			for f in s["files"][1:]:
				for fingerprint in f["fingerprints"]:
					if fingerprint["value"] == oshash:
						stash.create_scene({
							"title": s["title"],
							"file_ids":[f["id"]]
						})
		log.progress(i/len(dupe_oshash_rows))

if __name__ == "__main__":
	if FRAGMENT["args"].get("hookContext"):
		hooks_main()

	try:
		TITLE_TEMPLATE = Template(config.SCENE_TITLE_TEMPLATE)
	except Exception as e:
		log.warning(f"Issue using config.SCENE_TITLE_TEMPLATE {e}, using default template instead")
		TITLE_TEMPLATE = Template("$group_size|$scene_id$flag")\

	for name, func in getmembers(config, isfunction):
		if re.match(r"^compare_", name):
			setattr(StashScene, name, func)
	plugin_main()
